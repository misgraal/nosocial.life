from dataclasses import dataclass
from app.db.login import *
from app.security.passwords import verify_password

@dataclass
class LoginResult:
    success: bool
    error: int

async def login(username: str, password: str) -> LoginResult:
    password_hash = await get_user_password(username)
    res = verify_password(password, password_hash['password'])
    if password_hash:
        if res == True:
            return LoginResult(True, 0)
        else:
            return LoginResult(False, 1) # Incorect username or password
    else:
        return LoginResult(False, 2) # User does not exist