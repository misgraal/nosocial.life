<<<<<<< Updated upstream
import hashlib
import hmac
import secrets
from pathlib import Path
=======
"""Signed, expiring share grants bound to the current share password."""
import hashlib
import hmac
import json
import os
import secrets
import time
import tempfile
>>>>>>> Stashed changes

from config import RUNTIME_DIR


<<<<<<< Updated upstream
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
=======
def _load_key() -> bytes:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    key_path = RUNTIME_DIR / "share-signing.key"
    if not key_path.exists():
        # Publish a complete key atomically, including when workers start together.
        fd, temporary = tempfile.mkstemp(dir=RUNTIME_DIR, prefix=".share-key-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(secrets.token_bytes(32))
            try:
                os.link(temporary, key_path)
            except FileExistsError:
                pass
        finally:
            os.unlink(temporary)
    key = key_path.read_bytes()
    if len(key) != 32:
        raise RuntimeError("Invalid share signing key")
    return key



_KEY = _load_key()


def _signature(kind: str, item: dict, expires: int) -> str:
    message = json.dumps([kind, item["publicID"], item.get("publicPasswordHash"), expires], separators=(",", ":"))
    return hmac.new(_KEY, message.encode(), hashlib.sha256).hexdigest()


def create_share_token(kind: str, item: dict) -> str:
    expires = int(time.time()) + 12 * 60 * 60
    return f"{expires}.{_signature(kind, item, expires)}"


def verify_share_token(token: str | None, kind: str, item: dict) -> bool:
    try:
        expiry, signature = (token or "").split(".", 1)
        expires = int(expiry)
        return time.time() < expires and hmac.compare_digest(signature, _signature(kind, item, expires))
    except (ValueError, TypeError):
        return False
>>>>>>> Stashed changes
