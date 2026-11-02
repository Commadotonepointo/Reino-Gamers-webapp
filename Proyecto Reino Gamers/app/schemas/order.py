# Esquemas Pydantic — pedidos y pagos
from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class OrderItemIn(BaseModel):
    variant_id: int
    quantity: int = Field(ge=1, le=20)


class OrderIn(BaseModel):
    items: list[OrderItemIn] = Field(min_length=1)
    delivery_email: EmailStr


class OrderItemOut(BaseModel):
    id: int
    product_name: str
    variant_sku: str
    quantity: int
    unit_price: float
    line_total: float
    code: str | None = None  # solo visible si el pedido está entregado

    class Config:
        from_attributes = True


class OrderOut(BaseModel):
    id: int
    order_number: str
    status: str
    delivery_email: str
    total_usd: float
    created_at: datetime
    expires_at: datetime | None
    items: list[OrderItemOut]

    class Config:
        from_attributes = True


class CreatePaymentOut(BaseModel):
    payment_id: int
    provider: str
    status: str
    checkout_url: str | None = None
    message: str | None = None


class PaymentOut(BaseModel):
    id: int
    order_id: int
    provider: str
    method: str
    status: str
    amount_usd: float
    currency: str
    checkout_url: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class WebhookEventOut(BaseModel):
    id: int
    provider: str
    status: str
    payload: dict[str, Any] | None
    received_at: datetime

    class Config:
        from_attributes = True
