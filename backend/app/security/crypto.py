"""Field-level encryption for PAN / bank account, plus keyed hashes for duplicate lookups."""
import hashlib
import hmac
import logging
import secrets

from cryptography.fernet import Fernet

from app.config import settings

log = logging.getLogger(__name__)

_DEV_FERNET = "x3E2p2yQe3Jc8q1k6m0Qm5bD0V6aVY8Q9a1B2c3D4e8="  # dev/test only; prod refuses to start without a real key
_DEV_HMAC = "dev-only-hmac-key-change-me"


def _fernet() -> Fernet:
    key = settings.fernet_key
    if not key:
        if settings.is_prod:
            raise RuntimeError("FERNET_KEY must be set in production")
        key = _DEV_FERNET
    return Fernet(key.encode())


def _hmac_key() -> bytes:
    key = settings.hmac_key
    if not key:
        if settings.is_prod:
            raise RuntimeError("HMAC_KEY must be set in production")
        key = _DEV_HMAC
    return key.encode()


def check_keys_configured() -> None:
    _fernet()
    _hmac_key()


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def lookup_hash(value: str) -> str:
    """Deterministic keyed hash: lets us find duplicates without storing the value in clear."""
    return hmac.new(_hmac_key(), value.strip().upper().encode(), hashlib.sha256).hexdigest()


def sha256_hex(value: str | bytes) -> str:
    data = value.encode() if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)  # 32 random bytes


def last4(value: str) -> str:
    return value[-4:] if value else ""


def mask(value_last4: str | None) -> str:
    return f"•••• {value_last4}" if value_last4 else "—"
