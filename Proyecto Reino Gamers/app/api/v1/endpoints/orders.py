# Pedidos: creación con reserva de inventario, listado y detalle seguro
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.order import GiftCardCode, Order, OrderItem
from app.models.product import Product, ProductVariant
from app.models.user import User
from app.schemas.order import OrderIn, OrderItemOut, OrderOut
from app.services.inventory import (
    generate_order_number, release_expired_reservations, reserve_codes,
)

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("", response_model=OrderOut, status_code=201)
def create_order(
    data: OrderIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    release_expired_reservations(db)

    variant_ids = list({item.variant_id for item in data.items})
    variants = db.execute(
        select(ProductVariant).join(Product).where(
            ProductVariant.id.in_(variant_ids), ProductVariant.is_active.is_(True)
        )
    ).scalars().all()
    by_id = {v.id: v for v in variants}
    missing = [i.variant_id for i in data.items if i.variant_id not in by_id]
    if missing:
        raise HTTPException(400, f"Variantes inexistentes o inactivas: {missing}")

    try:
        order = Order(
            order_number=generate_order_number(),
            user_id=user.id,
            status="pending",
            delivery_email=data.delivery_email,
            expires_at=reserved_until(),
        )
        db.add(order)
        db.flush()

        for item in data.items:
            variant = by_id[item.variant_id]
            line_total = float(variant.price_usd) * item.quantity
            order_item = OrderItem(
                order_id=order.id,
                variant_id=variant.id,
                product_name=variant.product.name,
                variant_sku=variant.sku,
                quantity=item.quantity,
                unit_price=float(variant.price_usd),
                line_total=line_total,
            )
            db.add(order_item)
            db.flush()
            reserve_codes(db, order, order_item)   # lanza ValueError si no hay stock
            order.subtotal_usd += line_total

        order.total_usd = order.subtotal_usd
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    except Exception:
        db.rollback()
        raise

    db.commit()
    db.refresh(order)
    return _to_out(order)


def reserved_until():
    from datetime import datetime, timedelta, timezone
    return datetime.now(timezone.utc) + timedelta(minutes=settings.order_reservation_minutes)


def _load_order(db: Session, order_id: int, user: User) -> Order:
    order = db.execute(
        select(Order)
        .options(joinedload(Order.items))
        .where(Order.id == order_id, Order.user_id == user.id)
    ).unique().scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Pedido no encontrado")
    return order


def _to_out(order: Order) -> OrderOut:
    delivered = order.status in ("paid", "delivered")
    items = [
        OrderItemOut(
            id=i.id,
            product_name=i.product_name,
            variant_sku=i.variant_sku,
            quantity=i.quantity,
            unit_price=float(i.unit_price),
            line_total=float(i.line_total),
            code=None,   # los códigos se listan aparte (seguridad)
        )
        for i in order.items
    ]
    return OrderOut(
        id=order.id,
        order_number=order.order_number,
        status=order.status,
        delivery_email=order.delivery_email,
        total_usd=float(order.total_usd),
        created_at=order.created_at,
        expires_at=order.expires_at,
        items=items,
    )


@router.get("", response_model=list[OrderOut])
def my_orders(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    release_expired_reservations(db)
    orders = db.execute(
        select(Order).options(joinedload(Order.items))
        .where(Order.user_id == user.id)
        .order_by(Order.id.desc())
    ).unique().scalars().all()
    return [_to_out(o) for o in orders]


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    release_expired_reservations(db)
    order = _load_order(db, order_id, user)
    return _to_out(order)


@router.get("/{order_id}/codes", response_model=list[OrderItemOut])
def get_order_codes(
    order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """
    Los códigos SOLO se entregan si el pedido está pagado/entregado
    y siempre al dueño. Aparecen descifrados aquí (y por correo).
    """
    release_expired_reservations(db)
    order = _load_order(db, order_id, user)
    if order.status not in ("paid", "delivered"):
        raise HTTPException(403, "Los códigos se entregan cuando el pago es confirmado")

    items = {i.variant_id: i for i in order.items}
    codes = db.execute(
        select(GiftCardCode).where(GiftCardCode.order_id == order.id)
    ).scalars().all()

    from app.core.crypto import decrypt_code
    out_by_item = []
    for code in codes:
        if code.status == "sold" and code.variant_id in items:
            item = items[code.variant_id]
            existing = next((o for o in out_by_item if o.id == item.id), None)
            if existing and existing.code is None:
                existing.code = decrypt_code(code.code_encrypted)
            elif existing is None:
                out_by_item.append(OrderItemOut(
                    id=item.id,
                    product_name=item.product_name,
                    variant_sku=item.variant_sku,
                    quantity=item.quantity,
                    unit_price=float(item.unit_price),
                    line_total=float(item.line_total),
                    code=decrypt_code(code.code_encrypted),
                ))
    return out_by_item
