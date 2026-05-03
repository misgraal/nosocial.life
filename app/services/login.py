from dataclasses import dataclass

from app.db.login import get_user_auth_record
from app.security.passwords import verify_password
from app.services.register import normalize_username


@dataclass
class LoginResult:
    success: bool
    error: int
    user_id: int | None = None
    username: str | None = None


async def login(username: str, password: str) -> LoginResult:
    normalized_username = normalize_username(username)
    if not normalized_username or not password:
        return LoginResult(False, 1)

    user = await get_user_auth_record(normalized_username)
    if not user:
        return LoginResult(False, 1)

    if user["blocked"]:
        return LoginResult(False, 3)

    try:
        password_matches = verify_password(password, user["password"])
    except Exception:
        return LoginResult(False, 2)

    if not password_matches:
        return LoginResult(False, 1)

    return LoginResult(True, 0, user_id=user["userID"], username=user["username"])
