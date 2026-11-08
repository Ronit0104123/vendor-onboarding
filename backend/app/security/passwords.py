from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

_hasher = PasswordHasher()  # argon2id with library defaults
_DUMMY = _hasher.hash("timing-equaliser")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        # Always run a hash so unknown emails take as long as wrong passwords (no user enumeration).
        return _hasher.verify(password_hash or _DUMMY, password) and password_hash is not None
    except VerificationError:
        return False
