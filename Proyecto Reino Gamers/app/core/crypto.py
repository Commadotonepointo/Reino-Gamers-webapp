# Cifrado de códigos de gift card en reposo (Fernet: AES-128-CBC + HMAC-SHA256)
# La clave se deriva de CODE_ENCRYPTION_KEY, o de APP_SECRET_KEY como respaldo.
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _key() -> bytes:
    raw = settings.app_secret_key.encode()
    digest = hashlib.sha256(raw).digest()
    return base64.urlsafe_b64encode(digest)


_fernet = Fernet(_key())


def encrypt_code(code: str) -> str:
    """Cifra un código antes de guardarlo en la base de datos."""
    return _fernet.encrypt(code.strip().encode()).decode()


def decrypt_code(token: str) -> str:
    """Descifra un código de la base de datos (solo para el dueño del pedido)."""
    try:
        return _fernet.decrypt(token.encode()).decode()
    except InvalidToken:  # clave cambió o dato corrupto
        return "[código no descifrable — revisar CODE_ENCRYPTION_KEY]"


def generate_fernet_key() -> str:
    """Utilidad: imprime una clave Fernet nueva para CODE_ENCRYPTION_KEY."""
    return base64.urlsafe_b64encode(Fernet.generate_key()).decode()
