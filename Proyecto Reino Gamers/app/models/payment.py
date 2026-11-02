# Pagos (multi-pasarela) + bitácora de webhooks + configuración del sitio
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sqlalchemy.types import TypeDecorator

from app.db.base import Base


class JSONFlexible(TypeDecorator):
    """JSONB en PostgreSQL, JSON genérico en otros motores."""
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


PAYMENT_PROVIDER = ("binance_pay", "manual", "other")
PAYMENT_STATUS = ("created", "pending", "confirmed", "failed", "expired")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(
        Enum(*PAYMENT_PROVIDER, name="payment_provider"), nullable=False
    )
    method: Mapped[str] = mapped_column(String(20), default="USDT")
    status: Mapped[str] = mapped_column(
        Enum(*PAYMENT_STATUS, name="payment_status"), default="created", index=True
    )
    amount_usd: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USDT")
    prepay_id: Mapped[str | None] = mapped_column(String(120), index=True)
    merchant_trade_no: Mapped[str | None] = mapped_column(String(120), unique=True, index=True)
    checkout_url: Mapped[str | None] = mapped_column(String(500))
    raw_request: Mapped[dict[str, Any] | None] = mapped_column(JSONFlexible)
    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSONFlexible)
    raw_webhook: Mapped[dict[str, Any] | None] = mapped_column(JSONFlexible)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )

    order: Mapped["Order"] = relationship(back_populates="payments")  # noqa: F821


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    headers: Mapped[dict[str, Any] | None] = mapped_column(JSONFlexible)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONFlexible)
    status: Mapped[str] = mapped_column(String(20), default="received")
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
