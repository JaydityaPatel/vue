from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.config import settings

_passwords = CryptContext(schemes=["bcrypt"], deprecated="auto")
_ALGORITHM = "HS256"
_TOKEN_LIFETIME = timedelta(days=7)


def hash_password(password: str) -> str:
    """Return a bcrypt hash suitable for storing in the user record."""
    return _passwords.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Check a password, returning false for malformed stored hashes."""
    try:
        return _passwords.verify(plain, hashed)
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": subject, "iat": now, "exp": now + _TOKEN_LIFETIME},
        settings.jwt_secret,
        algorithm=_ALGORITHM,
    )


def decode_access_token(token: str) -> str:
    """Validate a signed, unexpired token and return its user id."""
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[_ALGORITHM],
        options={"require": ["exp", "sub"]},
    )
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise jwt.InvalidTokenError("Invalid token subject")
    return subject
