# ------------------------------------------------------------
# Entrega de códigos de gift card por correo (SMTP).
# Si SMTP no está configurado, solo registra en el log (dev).
# ------------------------------------------------------------
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)

RETRY_COUNT = 2


def _body(order_number: str, items: list[dict]) -> str:
    lines = [
        "🎮 ¡Gracias por tu compra en Reino Gamers!",
        "",
        f"Número de pedido: {order_number}",
        "Estos son tus códigos. Consérvalos en privado:",
        "",
    ]
    for item in items:
        lines.append(f"•  {item['product_name']} — {item['variant_sku']}")
        lines.append(f"   Código: {item['code']}")
        lines.append("")
    lines += [
        "Si algún código presenta problema, responde este correo con el número",
        "de pedido y lo revisaremos de inmediato.",
        "",
        f"— El equipo de {settings.app_name}",
    ]
    return "\n".join(lines)


def deliver_codes(order_number: str, to_email: str, items: list[dict]) -> bool:
    """
    Envía los códigos al cliente. items = [{'product_name':…, 'variant_sku':…, 'code':…}]
    Devuelve True si se envió (o está simulado con log), False si falló.
    """
    body = _body(order_number, items)
    subject = f"[{settings.app_name}] Tus códigos — Pedido {order_number}"

    if not settings.smtp_ready:
        logger.warning(
            "SMTP no configurado. Si estuviera listo se enviaría a %s:\n%s", to_email, body
        )
        return True  # modo desarrollo: se registra en log para probar

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from
    message["To"] = to_email
    message.set_content(body)

    from_address = settings.smtp_from
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
                server.starttls()
                server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(message)
            logger.info("Códigos del pedido %s enviados a %s", order_number, to_email)
            return True
        except Exception:
            logger.exception("Intento %d/%d de envío de %s falló", attempt, RETRY_COUNT, to_email)
    return False
