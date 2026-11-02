# Configuración de la aplicación — lee TODO desde .env
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Aplicación -------------------------------------------------------
    app_name: str = "Reino Gamers"
    debug: bool = True
    app_secret_key: str = "dev-secret-cambiar-en-produccion"
    public_base_url: str = "http://localhost:5173"
    module_colors: str = ""  # placeholder no usado, evita warnings de env sobrante

    # --- Base de datos ----------------------------------------------------
    database_url: str = "postgresql://postgres:postgres@localhost:5432/reino_gamers"

    # --- Seguridad --------------------------------------------------------
    access_token_expire_minutes: int = 60 * 24  # 24h

    # --- Binance Pay (método principal de pago) ---------------------------
    binance_pay_api_key: str = ""          # API Key del merchant
    binance_pay_api_secret: str = ""       # API Secret del merchant
    binance_pay_base_url: str = "https://bpay.binanceapi.com"
    binance_pay_currency: str = "USDT"
    binance_pay_merchant_private_key: str = ""  # RSA privada opcional (webhook)
    binance_webhook_secret: str = ""            # firma del webhook (validación)
    binance_webhook_strict: bool = True

    # --- Correo (entrega de códigos) --------------------------------------
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "Reino Gamers <no-reply@reinogamers.com>"

    # --- Reglas de negocio ------------------------------------------------
    shop_currency: str = "USD"
    order_reservation_minutes: int = 15

    @property
    def binance_credentials_ready(self) -> bool:
        return bool(self.binance_pay_api_key and self.binance_pay_api_secret)

    @property
    def smtp_ready(self) -> bool:
        return bool(self.smtp_host and self.smtp_user)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
