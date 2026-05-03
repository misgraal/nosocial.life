import hashlib
import hmac
import secrets
from pathlib import Path

from config import RUNTIME_DIR


SECRET_FILE = RUNTIME_DIR / "share_cookie_secret"


def get_share_cookie_secret() -> str:
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    if SECRET_FILE.exists():
        secret = SECRET_FILE.read_text(encoding="utf-8").strip()
        if secret:
            return secret

    secret = secrets.token_urlsafe(48)
    SECRET_FILE.write_text(secret, encoding="utf-8")
    return secret


def create_share_access_token(item_type: str, public_id: str, password_hash: str | None) -> str:
    message = f"{item_type}:{public_id}:{password_hash or ''}".encode("utf-8")
    return hmac.new(
        get_share_cookie_secret().encode("utf-8"),
        message,
        hashlib.sha256
    ).hexdigest()


def verify_share_access_token(item_type: str, public_id: str, password_hash: str | None, token: str | None) -> bool:
    if not token:
        return False

    expected_token = create_share_access_token(item_type, public_id, password_hash)
    return hmac.compare_digest(str(token), expected_token)
