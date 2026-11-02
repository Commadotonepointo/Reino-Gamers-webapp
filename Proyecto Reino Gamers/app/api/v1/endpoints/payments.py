# Pagos — Binance Pay (USDT): crear cobro, webhook y verificación de estado
from datetime import datetime, timezone
from typing import Any
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.order import Order
from app.models.payment import Payment, WebhookEvent
from app.models.user import User
from app.schemas.order import CreatePaymentOut, PaymentOut
from app.services.binance_pay import BinancePayError, client as binance
from app.services.delivery import deliver_codes
from app.services.inventory import confirm_order_codes

router = APIRouter(prefix="/payments", tags=["payments"])

CONFIRMED_STATES = {"PAY_SUCCESS", "PAID", "SUCCESS"}


def _make_trade_no(order: Order) -> str:
    """Identificador único del pago ante Binance. Regenerable por cada intento."""
    return f"RG{order.id}-{uuid.uuid4().hex[:12].upper()}"


@router.post("/order/{order_id}", response_model=CreatePaymentOut)
def create_payment(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Crea el cobro de USDT en Binance Pay para un pedido pendiente.
    Devuelve `checkout_url` para llevar al cliente a pagar.
    """
    order = db.get(Order, order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(404, "Pedido no encontrado")

    if order.status in ("paid", "delivered", "cancelled"):
        raise HTTPException(409, f"El pedido no admite pago (estado: {order.status})")
    if order.expires_at and order.expires_at < datetime.now(timezone.utc):
        order.status = "expired"
        db.commit()
        raise HTTPException(409, "La reserva del pedido expiró; vuelve a crear el pedido")

    trade_no = _make_trade_no(order)
    payment = Payment(
        order_id=order.id,
        provider="binance_pay",
        method=settings.binance_pay_currency,
        status="created",
        amount_usd=float(order.total_usd),
        currency=settings.binance_pay_currency,
        merchant_trade_no=trade_no,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    try:
        data: dict[str, Any] = binance.create_order(
            merchant_trade_no=trade_no,
            amount_usd=float(order.total_usd),
            goods_reference=order.order_number,
            description=f"Gift cards Reino Gamers — pedido {order.order_number}",
            return_url=f"{settings.public_base_url}/compra/exito",
            cancel_url=f"{settings.public_base_url}/compra/cancelada",
        )
    except BinancePayError as exc:
        payment.status = "failed"
        payment.raw_response = {"error": str(exc)}
        db.commit()
        raise HTTPException(502, f"Error con Binance Pay: {exc}") from exc
    except Exception as exc:  # error inesperado: el pago registra el fallo
        payment.status = "failed"
        payment.raw_response = {"error": str(exc)}
        db.commit()
        raise HTTPException(502, f"Error creando el cobro: {exc}") from exc

    payment.prepay_id = str(data.get("prepayId") or "")
    payment.checkout_url = data.get("checkoutUrl") or data.get("universalUrl") or None
    payment.raw_request = {"merchantTradeNo": trade_no, "amount": float(order.total_usd)}
    payment.raw_response = data
    payment.status = "pending"
    order.status = "awaiting_payment"
    db.commit()
    db.refresh(payment)

    return CreatePaymentOut(
        payment_id=payment.id,
        provider="binance_pay",
        status="pending",
        checkout_url=payment.checkout_url,
        message="Redirige al cliente a checkout_url para pagar con USDT en Binance.",
    )


@router.post("/webhook/binance")
async def webhook_binance(request: Request, db: Session = Depends(get_db)):
    """
    Webhook de Binance Pay.
    1. Guarda el evento crudo (auditoría en webhook_events).
    2. Valida la firma si BINANCE_WEBHOOK_SECRET está definido.
    3. Localiza el pago por merchantTradeNo y lo confirma:
       códigos reserved → sold, pedido → delivered y correo con los códigos.
    """
    raw = await request.body()
    headers = dict(request.headers)
    try:
        payload: dict[str, Any] = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = {"raw": raw.decode(errors="replace")}

    event = WebhookEvent(
        provider="binance_pay",
        headers={k: v for k, v in headers.items() if k.startswith(("webhook", "content-"))},
        payload=payload,
        status="received",
    )
    db.add(event)
    db.commit()

    # --- validación de firma -------------------------------------------
    from app.services.binance_pay import is_webhook_signature_valid

    valid = is_webhook_signature_valid(
        timestamp=headers.get("webhook-timestamp", ""),
        nonce=headers.get("webhook-nonce", ""),
        raw_body=raw.decode(errors="replace"),
        signature=headers.get("webhook-signature", ""),
    )
    if not valid and settings.binance_webhook_strict and not settings.debug:
        event.status = "failed"
        db.commit()
        raise HTTPException(401, "Firma de webhook inválida")

    # --- localizar pago y confirmar -------------------------------------
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    biz_status = str(data.get("bizStatus", "")).upper()
    trade_no = data.get("merchantTradeNo")

    if trade_no:
        payment = db.execute(
            select(Payment).where(Payment.merchant_trade_no == str(trade_no))
        ).scalar_one_or_none()
        if payment:
            payment.raw_webhook = payload
            # Confirmación idempotente: si ya está confirmado, no re-procesa.
            if biz_status in CONFIRMED_STATES and payment.status != "confirmed":
                confirm_payment(db, payment)

    event.status = "processed"
    event.processed_at = datetime.now(timezone.utc)
    db.commit()
    return {"code": "SUCCESS", "message": "event processed"}


def confirm_payment(db: Session, payment: Payment) -> None:
    """Marca el pago confirmado, convierte los códigos reservados en vendidos y notifica."""
    payment.status = "confirmed"
    payment.confirmed_at = datetime.now(timezone.utc)
    order = payment.order
    if not order:
        return

    if order.status not in ("paid", "delivered"):
        order.status = "paid"
        order.paid_at = datetime.now(timezone.utc)
        sold = confirm_order_codes(db, order)   # reserved → sold; pedido → delivered
        db.commit()
        if sold:
            deliver_codes(order.order_number, order.delivery_email, sold)


@router.post("/{payment_id}/check", response_model=PaymentOut)
def check_payment_status(
    payment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Consulta activa del estado del pago contra Binance Pay
    (respaldo si el webhook no llegó).
    """
    payment = db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(404, "Pago no encontrado")
    order = payment.order
    if order is None or (order.user_id != user.id and user.role != "admin"):
        raise HTTPException(404, "Pago no encontrado")

    if payment.merchant_trade_no:
        try:
            result = binance.query_order(payment.merchant_trade_no)
        except BinancePayError as exc:
            raise HTTPException(502, f"No se pudo consultar Binance Pay: {exc}") from exc

        status_b = str(result.get("status", "")).upper()
        if payment.status != "confirmed" and status_b in CONFIRMED_STATES:
            confirm_payment(db, payment)
        payment.raw_response = result

    db.commit()
    db.refresh(payment)
    return payment


@router.get("/order/{order_id}", response_model=list[PaymentOut])
def order_payments(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    order = db.get(Order, order_id)
    if not order or (order.user_id != user.id and user.role != "admin"):
        raise HTTPException(404, "Pedido no encontrado")
    return order.payments
