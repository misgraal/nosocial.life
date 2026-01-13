from app.db.db import fetch_one

async def get_user_password(username: str):
    password = await fetch_one("SELECT password FROM users WHERE username=%s", (username,))
    return password