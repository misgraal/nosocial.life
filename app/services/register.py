from dataclasses import dataclass
import re

from app.db.register import add_user, check_user
from app.security.passwords import hash_password


MIN_USERNAME_LENGTH = 3
MAX_USERNAME_LENGTH = 64
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.@-]+$")


@dataclass
class RegisterResult:
    success: bool
    error: int
    user_id: int | None = None
    username: str | None = None


def normalize_username(username: str) -> str:
    return str(username or "").strip()


def validate_username(username: str) -> bool:
    return (
        MIN_USERNAME_LENGTH <= len(username) <= MAX_USERNAME_LENGTH
        and bool(USERNAME_PATTERN.fullmatch(username))
    )


def validate_password(password: str) -> bool:
    return bool(password)


async def register(username, password, confirm_password):
    normalized_username = normalize_username(username)

    if not validate_username(normalized_username):
        return RegisterResult(False, 3)

    if not validate_password(password):
        return RegisterResult(False, 4)

    if password != confirm_password:
        return RegisterResult(False, 1)

    if await check_user(normalized_username) is not None:
        return RegisterResult(False, 2)

    try:
        user = await add_user(normalized_username, hash_password(password))
    except Exception:
        if await check_user(normalized_username) is not None:
            return RegisterResult(False, 2)
        raise

    return RegisterResult(True, 0, user_id=user["userID"], username=user["username"])
