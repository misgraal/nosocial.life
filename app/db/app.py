from app.db.db import fetch_one

async def get_user_username_by_id(id: int):
    res = await fetch_one("SELECT username FROM users WHERE userID=%s", (id,))
    return res["username"]