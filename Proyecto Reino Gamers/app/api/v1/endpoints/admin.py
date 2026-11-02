# Endpoints de ADMINISTRACIÓN (requieren rol admin):
# catálogo, carga de códigos al inventario, pedidos, pagos.
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_admin
from app.core.crypto import encrypt_code
from app.core.security import hash_password
from app.db.session import get_db
from app.models.order import GiftCardCode, Order
from app.models.payment import Payment
from app.models.product import Product, ProductVariant
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(get_current_admin)])


# ---------------------------------------------------------------- catálogo
class ProductIn(BaseModel):
    slug: str
    name: str
    category: str  # gaming | cloud_storage
    platform: str
    description: str = ""
    image_url: str | None = None


class VariantIn(BaseModel):
    product_id: int
    denomination: float
    region: str = "GLOBAL"
    price_usd: float
    sku: str | None = None
    currency: str = "USD"


class CodesIn(BaseModel):
    variant_id: int
    codes: list[str] = Field(min_length=1)   # claves una por línea


@router.post("/products", status_code=201)
def create_product(data: ProductIn, db: Session = Depends(get_db)):
    if data.category not in ("gaming", "cloud_storage"):
        raise HTTPException(400, "category debe ser 'gaming' o 'cloud_storage'")
    if db.execute(select(Product).where(Product.slug == data.slug)).scalar_one_or_none():
        raise HTTPException(409, "Ya existe un producto con ese slug")
    product = Product(**data.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return {"id": product.id, "slug": product.slug}


@router.post("/variants", status_code=201)
def create_variant(data: VariantIn, db: Session = Depends(get_db)):
    product = db.get(Product, data.product_id)
    if not product:
        raise HTTPException(404, "Producto no encontrado")
    if not data.sku:
        data.sku = f"SC-{product.platform.upper()}" \
                   f"-{data.currency}{data.denomination:g}-{data.region}"
    exists = db.execute(
        select(ProductVariant).where(ProductVariant.sku == data.sku)
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(409, f"SKU duplicado: {data.sku}")
    variant = ProductVariant(
        product_id=data.product_id,
        sku=data.sku,
        denomination=data.denomination,
        currency=data.currency,
        region=data.region,
        price_usd=data.price_usd,
    )
    db.add(variant)
    db.commit()
    return {"id": variant.id, "sku": variant.sku}


@router.post("/codes", status_code=201)
def upload_codes(data: CodesIn, db: Session = Depends(get_db)):
    """
    Carga del inventario: la lista de códigos reales de las gift cards.
    Cada código se guarda CIFRADO; solo se descifra al entregarse.
    """
    variant = db.get(ProductVariant, data.variant_id)
    if not variant:
        raise HTTPException(404, "Variante no encontrada")
    created = []
    for raw in data.codes:
        code = raw.strip()
        if not code:
            continue
        created.append(GiftCardCode(variant_id=data.variant_id, code_encrypted=encrypt_code(code)))
    db.add_all(created)
    db.commit()
    return {"uploaded": len(created), "sku": variant.sku}


@router.get("/stock", response_model=list[dict[str, Any]])
def stock_report(db: Session = Depends(get_db)):
    """Resumen de inventario por variante (disponible/reservado/vendido)."""
    variants = db.execute(select(ProductVariant)).scalars().all()
    out = []
    for v in variants:
        rows = db.execute(
            select(GiftCardCode.status, func.count(GiftCardCode.id))
            .where(GiftCardCode.variant_id == v.id)
            .group_by(GiftCardCode.status)
        ).all()
        counts = {s: n for s, n in rows}
        out.append({
            "variant_id": v.id,
            "sku": v.sku,
            "price_usd": float(v.price_usd),
            "available": counts.get("available", 0),
            "reserved": counts.get("reserved", 0),
            "sold": counts.get("sold", 0),
        })
    return out


# ---------------------------------------------------------------- pedidos/pagos
@router.get("/orders", response_model=list[dict[str, Any]])
def all_orders(status: str | None = None, db: Session = Depends(get_db)):
    query = select(Order).options(joinedload(Order.items)).order_by(Order.id.desc())
    if status:
        query = query.where(Order.status == status)
    orders = db.execute(query).unique().scalars().all()
    return [
        {
            "id": o.id,
            "order_number": o.order_number,
            "status": o.status,
            "user_email": getattr(o, "user", None) and o.user.email or o.delivery_email,
            "total_usd": float(o.total_usd),
            "created_at": o.created_at,
        }
        for o in orders
    ]


@router.get("/orders/{order_id}", response_model=dict[str, Any])
def admin_order_detail(order_id: int, db: Session = Depends(get_db)):
    order = db.execute(
        select(Order).options(joinedload(Order.items)).where(Order.id == order_id)
    ).unique().scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Pedido no encontrado")
    return {
        "id": order.id,
        "order_number": order.order_number,
        "status": order.status,
        "user_id": order.user_id,
        "delivery_email": order.delivery_email,
        "subtotal_usd": float(order.subtotal_usd),
        "total_usd": float(order.total_usd),
        "items": [
            {"sku": i.variant_sku, "quantity": i.quantity, "line_total": float(i.line_total)}
            for i in order.items
        ],
        "created_at": order.created_at,
        "paid_at": order.paid_at,
    }


@router.post("/orders/{order_id}/cancel")
def cancel_order(order_id: int, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Pedido no encontrado")
    if order.status in ("paid", "delivered"):
        raise HTTPException(409, "No se cancela un pedido ya entregado")
    order.status = "cancelled"
    for code in db.execute(
        select(GiftCardCode).where(GiftCardCode.order_id == order.id)
    ).scalars().all():
        if code.status == "reserved":
            code.status = "available"
            code.order_id = None
            code.reserved_until = None
    db.commit()
    return {"id": order.id, "status": "cancelled"}


@router.get("/payments", response_model=list[dict[str, Any]])
def all_payments(db: Session = Depends(get_db)):
    payments = db.execute(select(Payment).order_by(Payment.id.desc())).scalars().all()
    return [
        {
            "id": p.id,
            "order_id": p.order_id,
            "provider": p.provider,
            "method": p.method,
            "status": p.status,
            "amount_usd": float(p.amount_usd),
            "merchant_trade_no": p.merchant_trade_no,
            "created_at": p.created_at,
            "confirmed_at": p.confirmed_at,
        }
        for p in payments
    ]


# ---------------------------------------------------------------- usuarios
class AdminUserIn(BaseModel):
    email: str
    password: str
    full_name: str = ""


@router.post("/users/admin", status_code=201)
def create_admin_user(data: AdminUserIn, db: Session = Depends(get_db)):
    """Alta de cuentas administradoras de la tienda."""
    from app.schemas.user import UserCreate  # valida formato del correo
    UserCreate(email=data.email, password=data.password)

    exists = db.execute(select(User).where(User.email == data.email.lower())).scalar_one_or_none()
    if exists:
        raise HTTPException(409, "Correo ya registrado")
    user = User(
        email=data.email.lower(),
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role="admin",
    )
    db.add(user)
    db.commit()
    return {"id": user.id, "email": user.email, "role": "admin"}
