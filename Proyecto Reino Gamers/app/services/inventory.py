# ------------------------------------------------------------
# Inventario: reserva y entrega ATÓMICA de códigos de gift card
# Uso bloqueo pesimista (SELECT … FOR UPDATE) para que dos compras
# concurrentes nunca obtengan el mismo código.
# ------------------------------------------------------------
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.crypto import decrypt_code
from app.models.order import GiftCardCode, Order, OrderItem
from app.models.product import Product, ProductVariant

logger = logging.getLogger(__name__)


def generate_order_number() -> str:
    """RG-20260102-K7F3A9"""
    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"RG-{date}-{secrets.token_hex(3).upper()}"


def available_stock(db: Session, variant_ids: list[int]) -> dict[int, int]:
    """Stock disponible por variante (para catálogo)."""
    rows = db.execute(
        select(GiftCardCode.variant_id, GiftCardCode.id)
        .where(
            GiftCardCode.variant_id.in_(variant_ids),
            GiftCardCode.status == "available",
        )
    ).all()
    counts: dict[int, int] = {}
    for variant_id, _ in rows:
        counts[variant_id] = counts.get(variant_id, 0) + 1
    return counts


def release_expired_reservations(db: Session) -> int:
    """
    Libera códigos reservados cuya reserva venció y marca sus pedidos
    como expired. Se llama al inicio de cada request de carrito/pedido.
    """
    now = datetime.now(timezone.utc)
    expired = db.execute(
        select(GiftCardCode).where(
            GiftCardCode.status == "reserved",
            GiftCardCode.reserved_until < now,
        )
    ).scalars().all()
    order_ids = {c.order_id for c in expired if c.order_id}
    for code in expired:
        code.status = "available"
        code.order_id = None
        code.reserved_until = None

    if order_ids:
        orders = db.execute(select(Order).where(Order.id.in_(order_ids))).scalars().all()
        for order in orders:
            if order.status in ("pending", "awaiting_payment"):
                order.status = "expired"

    db.commit()
    return len(expired)


def reserve_codes(db: Session, order: Order, item: OrderItem) -> None:
    """
    Reserva `quantity` códigos para un ítem de pedido.
    Debe llamarse DENTRO de la misma transacción/lock del pedido.
    Lanza ValueError si no hay stock suficiente.
    """
    qty = item.quantity
    codes = db.execute(
        select(GiftCardCode)
        .where(
            GiftCardCode.variant_id == item.variant_id,
            GiftCardCode.status == "available",
        )
        .with_for_update(skip_locked=False)   # bloqueo pesimista
        .limit(qty)
    ).scalars().all()

    if len(codes) < qty:
        raise ValueError(
            f"Stock insuficiente para {item.variant_sku}: quedan {len(codes)} de {qty}."
        )

    reserved_until = datetime.now(timezone.utc) + timedelta(
        minutes=settings.order_reservation_minutes
    )
    for code in codes:
        code.status = "reserved"
        code.order_id = order.id
        code.reserved_until = reserved_until


def confirm_order_codes(db: Session, order: Order, user_email_notify=None) -> list[dict]:
    """
    Al confirmar el pago: AVAILABLE→ no (están RESERVED) / RESERVED→SOLD,
    el pedido pasa a DELIVERED y se devuelven los datos para el correo.
    """
    sold: list[dict] = []
    now = datetime.now(timezone.utc)

    items = db.execute(
        select(OrderItem).where(OrderItem.order_id == order.id)
    ).scalars().all()
    item_by_variant = {i.variant_id: i for i in items}

    codes = db.execute(
        select(GiftCardCode).where(GiftCardCode.order_id == order.id)
    ).scalars().all()

    for code in codes:
        if code.status == "reserved":
            code.status = "sold"
            code.sold_at = now
            item = item_by_variant.get(code.variant_id)
            sold.append({
                "product_name": item.product_name if item else "",
                "variant_sku": item.variant_sku if item else "",
                "code": decrypt_code(code.code_encrypted),
            })

    if order.status != "delivered":
        order.status = "delivered"   # pago confirmado → pedido entregado
        order.delivered_at = now
    return sold


def load_product_catalog(db: Session, *, category: str | None = None,
                         platform: str | None = None, only_active: bool = True):
    query = select(Product).options(joinedload(Product.variants))
    if only_active:
        query = query.where(Product.is_active.is_(True))
    if category:
        query = query.where(Product.category == category)
    if platform:
        query = query.where(Product.platform == platform)
    return db.execute(query.order_by(Product.sort_order, Product.id)).unique().scalars().all()


def get_variant_with_product(db: Session, variant_ids: list[int]):
    return db.execute(
        select(ProductVariant)
        .join(Product)
        .where(ProductVariant.id.in_(variant_ids), ProductVariant.is_active.is_(True))
    ).scalars().all()


def scoped_session_wrapper(db: Session) -> Session:
    """Utilidad para inyectar sesiones en servicios puros."""
    return db
