from dataclasses import dataclass

from app.db.login import get_user_auth_record
from app.security.passwords import verify_password


@dataclass
class LoginResult:
    success: bool
    error: int
    user_id: int | None = None
    username: str | None = None


async def login(username: str, password: str) -> LoginResult:
    user = await get_user_auth_record(username)
    if not user:
        return LoginResult(False, 2)

    if user["blocked"]:
        return LoginResult(False, 3)

    try:
        password_matches = verify_password(password, user["password"])
    except Exception:
        return LoginResult(False, 2)

    if not password_matches:
        return LoginResult(False, 1)

    return LoginResult(True, 0, user_id=user["userID"], username=username)
