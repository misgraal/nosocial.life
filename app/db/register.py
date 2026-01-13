from app.db.db import fetch_one
from app.db.db import execute

async def check_user(username):
    res = await fetch_one("SELECT * FROM users WHERE username=%s", (username))
    return res

async def add_user(username, password):
    res = await execute("INSERT INTO users (username, password) values (%s, %s)", (username, password))
    return res