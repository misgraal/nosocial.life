from app.db.db import fetch_one
from app.db.db import fetch_all

async def get_user_role(user_id):
    res = await fetch_one("SELECT role FROM users WHERE userID = %s", (user_id,))
    return res["role"]

async def get_users():
    res = await fetch_all("SELECT username, role FROM users GROUP BY username")
    return res