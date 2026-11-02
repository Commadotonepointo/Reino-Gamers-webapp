# Esquemas Pydantic — catalogo
from pydantic import BaseModel


class VariantOut(BaseModel):
    id: int
    sku: str
    denomination: float
    currency: str
    region: str
    price_usd: float
    is_active: bool
    available_stock: int

    class Config:
        from_attributes = True


class ProductOut(BaseModel):
    id: int
    slug: str
    name: str
    category: str
    platform: str
    description: str
    image_url: str | None
    is_active: bool

    class Config:
        from_attributes = True


class ProductDetail(ProductOut):
    variants: list[VariantOut]
