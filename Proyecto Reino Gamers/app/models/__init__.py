# Importa TODOS los modelos para que create_all() los conozca
from app.db.base import Base
from app.models.user import User
from app.models.product import Product, ProductVariant
from app.models.order import GiftCardCode, Order, OrderItem
from app.models.payment import Payment, WebhookEvent, Setting

__all__ = [
    "Base",
    "User",
    "Product",
    "ProductVariant",
    "GiftCardCode",
    "Order",
    "OrderItem",
    "Payment",
    "WebhookEvent",
    "Setting",
]
