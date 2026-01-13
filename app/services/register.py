from dataclasses import dataclass
from app.db.register import *
from app.security.passwords import hash_password

@dataclass
class RegisterResult:
    success: bool
    error: int


async def register(username, password, confirm_password):
    if password != confirm_password:
        return RegisterResult(False, 1) # password and confirm_password do not match
    
    elif await check_user(username) != None:
        return RegisterResult(False, 2) # user already exists
    else: 
        await add_user(username, hash_password(password))
        return RegisterResult(True, 0)
    