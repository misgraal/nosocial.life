from app.db.db import fetch_one

async def get_user_username_by_id(id: int):
    res = await fetch_one("SELECT username FROM users WHERE userID=%s", (id,))
    return res["username"]


async def get_user_root_folder(id: int):
    res = await fetch_one("SELECT * FROM folders WHERE userID=%s AND parentFolderId IS NULL", (id,))
    return res