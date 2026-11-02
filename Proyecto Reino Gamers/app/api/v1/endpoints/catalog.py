# Catálogo público: productos y variantes (con stock real disponible)
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models.product import Product, ProductVariant
from app.schemas.catalog import ProductDetail, ProductOut, VariantOut
from app.services.inventory import available_stock

router = APIRouter(prefix="/catalog", tags=["catalog"])


def _variant_out(db: Session, variants: list[ProductVariant]) -> list[VariantOut]:
    stock = available_stock(db, [v.id for v in variants])
    out = []
    for v in variants:
        out.append(VariantOut(
            id=v.id,
            sku=v.sku,
            denomination=float(v.denomination),
            currency=v.currency,
            region=v.region,
            price_usd=float(v.price_usd),
            is_active=v.is_active,
            available_stock=stock.get(v.id, 0),
        ))
    return out


@router.get("/products", response_model=list[ProductOut])
def list_products(
    category: str | None = None,     # gaming | cloud_storage
    platform: str | None = None,     # steam, google_one, dropbox…
    db: Session = Depends(get_db),
):
    if category and category not in ("gaming", "cloud_storage"):
        raise HTTPException(400, "category debe ser 'gaming' o 'cloud_storage'")

    query = db.execute(
        select(Product).where(Product.is_active.is_(True))
    ).scalars().all()
    if category:
        query = [p for p in query if p.category == category]
    if platform:
        query = [p for p in query if p.platform == platform]
    return sorted(query, key=lambda p: (p.sort_order, p.id))


@router.get("/products/{slug}", response_model=ProductDetail)
def get_product(slug: str, db: Session = Depends(get_db)):
    product = db.execute(
        select(Product)
        .options(joinedload(Product.variants))
        .where(Product.slug == slug, Product.is_active.is_(True))
    ).unique().scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Producto no encontrado")

    active_variants = [v for v in product.variants if v.is_active]
    return ProductDetail(
        **ProductOut.model_validate(product).model_dump(),
        variants=_variant_out(db, active_variants),
    )
