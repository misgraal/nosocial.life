from dataclasses import dataclass
from app.db.admin import *

@dataclass
class AdminResult:
    success: bool
    error: int

@dataclass
class GetInfo:
    users: list
    error : int

async def admin(user_id) -> AdminResult:
    role = await get_user_role(user_id)
    if role != "admin":
        return AdminResult(False, 1) # user is not an admin
    else:
        return AdminResult(True, 0)
    
async def get_info() -> GetInfo:
    users = await get_users() # list with dicts [{'username': 'admin', 'role': 'admin'}, ...]
    return GetInfo(users, 0)

