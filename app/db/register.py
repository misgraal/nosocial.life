from app.db.db import execute, fetch_one


async def check_user(username: str):
    return await fetch_one(
        "select userID, username from users where lower(username)=lower(%s)",
        (username,)
    )


async def add_user(username: str, password: str):
    role = "admin" if str(username or "").strip().casefold() == "admin" else "user"
    await execute(
        "insert into users (username, password, role) values (%s, %s, %s)",
        (username, password, role)
    )
    return await check_user(username)
