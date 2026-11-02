# ------------------------------------------------------------
# Cliente Binance Pay (método principal de pago — USDT)
# Docs: https://developers.binance.com/docs/binance-pay
# ------------------------------------------------------------
import hashlib
import hmac
import json
import logging
import time
import uuid
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Endpoints oficiales del API de Binance Pay:
ORDER_CREATE_PATH = "/binancepay/openapi/v2/order"
ORDER_QUERY_PATH = "/binancepay/openapi/v2/order/query"


class BinancePayError(Exception):
    """Error controlado al hablar con Binance Pay."""
    def __init__(self, message: str, data: Any = None):
        super().__init__(message)
        self.data = data


class BinancePayClient:
    """
    Cliente de Binance Pay para pedidos de un merchant.

    Autenticación (modo firma con API Key):
        headers = {
            "BinancePay-Timestamp":      <epoch en ms>,
            "BinancePay-Nonce":          <uuid hex>,
            "BinancePay-Certificate-SN": API_KEY,
            "BinancePay-Signature":      HMAC-SHA512(payload, API_SECRET), en MAYÚSCULAS,
        }
        payload = f"{timestamp}\n{nonce}\n{body_json}\n"
    """

    def __init__(self):
        self.api_key = settings.binance_pay_api_key
        self.api_secret = settings.binance_pay_api_secret
        self.base_url = settings.binance_pay_base_url.rstrip("/")
        self.webhook_url = f"{settings.public_base_url}/api/v1/payments/webhook/binance"

    @property
    def ready(self) -> bool:
        return bool(self.api_key and self.api_secret)

    # ---------------- firmas -------------------------------------------
    def _signature(self, timestamp: str, nonce: str, body: str) -> str:
        payload = f"{timestamp}\n{nonce}\n{body}\n".encode()
        return hmac.new(
            self.api_secret.encode(), payload, hashlib.sha512
        ).hexdigest().upper()  # mayúsculas, como exige Binance Pay

    def _headers(self, body: str) -> dict[str, str]:
        timestamp = str(int(time.time() * 1000))
        nonce = uuid.uuid4().hex
        return {
            "BinancePay-Timestamp": timestamp,
            "BinancePay-Nonce": nonce,
            "BinancePay-Certificate-SN": self.api_key,
            "BinancePay-Signature": self._signature(timestamp, nonce, body),
            "Content-Type": "application/json",
        }

    # ---------------- API ----------------------------------------------
    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.ready:
            raise BinancePayError(
                "Binance Pay no está configurado: coloca BINANCE_PAY_API_KEY y "
                "BINANCE_PAY_API_SECRET en el archivo .env."
            )

        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        url = f"{self.base_url}{path}"

        with httpx.Client(timeout=30) as http:
            try:
                resp = http.post(url, content=body, headers=self._headers(body))
            except httpx.HTTPError as exc:
                raise BinancePayError(f"Sin conexión con Binance Pay: {exc}") from exc

        data = resp.json()
        logger.info("BinancePay %s → status=%s code=%s", path, resp.status_code, data.get("code"))
        # Respuesta estándar: {"code": "SUCCESS"/"000000", "errorMessage": ..., "data": {...}}
        if resp.status_code != 200 or str(data.get("code", "")).upper() not in ("SUCCESS", "000000"):
            raise BinancePayError(
                f"BinancePay respondió code={data.get('code')} "
                f"message={data.get('errorMessage') or data.get('errMsg')}",
                data=data,
            )
        return data.get("data", data)

    def create_order(
        self,
        *,
        merchant_trade_no: str,
        amount_usd: float,
        description: str,
        return_url: str,
        cancel_url: str,
        goods_reference: str = "",
        expire_ms: int | None = None,
    ) -> dict[str, Any]:
        """
        Crea un cobro en Binance Pay y devuelve {prepayId, checkoutUrl, universalUrl, ...}.
        Moneda de cobro principal: USDT.
        """
        payload = {
            "env": {"terminalType": "WEB"},
            "merchantTradeNo": merchant_trade_no,
            "orderAmount": float(f"{amount_usd:.2f}"),
            "currency": settings.binance_pay_currency,  # USDT por defecto
            "description": description[:250],
            "goodsDetails": [
                {
                    "goodsType": "02",              # 02 = bienes virtuales / digitales
                    "goodsCategory": "Digital",
                    "referenceGoodsId": goods_reference or merchant_trade_no,
                    "goodsName": f"Reino Gamers — {description}"[:250],
                }
            ],
            "webhookUrl": self.webhook_url,
            "returnUrl": return_url,
            "cancelUrl": cancel_url,
            "expireTime": expire_ms or settings.order_reservation_minutes * 60 * 1000,
        }
        return self._post(ORDER_CREATE_PATH, payload)

    def query_order(self, merchant_trade_no: str) -> dict[str, Any]:
        """Consulta el estado de un pago por merchantTradeNo."""
        return self._post(ORDER_QUERY_PATH, {"merchantTradeNo": merchant_trade_no})


client = BinancePayClient()  # instancia única


def is_webhook_signature_valid(*, timestamp: str, nonce: str, raw_body: str, signature: str) -> bool:
    # --------------------------------------------------------------------
    # TODO (Fase 4): verificación criptográfica completa de Binance Pay
    # (RSA + desencriptado AES-CBC del payload). Mientras BINANCE_WEBHOOK_SECRET
    # no esté en .env, devuelve False y el webhook se maneja en modo
    # "log + reproceso manual" o con la verificación activa /{id}/check.
    # --------------------------------------------------------------------
    secret = settings.binance_webhook_secret
    if not secret or not signature or not timestamp or not nonce:
        return False
    payload = f"{timestamp}\n{nonce}\n{raw_body}\n".encode()
    expected = hmac.new(secret.encode(), payload, hashlib.sha512).hexdigest().upper()
    return hmac.compare_digest(expected, signature.upper())

