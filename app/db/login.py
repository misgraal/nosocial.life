from app.db.db import fetch_one


async def get_user_auth_record(username: str):
    return await fetch_one(
        """
        select userID, username, password, role, blocked, storageQuotaBytes
        from users
        where lower(username)=lower(%s)
        """,
        (username,)
    )


async def get_user_password(username: str):
    password = await fetch_one("select password from users where lower(username)=lower(%s)", (username,))
    return password


async def get_user_id(username: str):
    user = await fetch_one("select userID from users where lower(username)=lower(%s)", (username,))
    return user["userID"] if user else None
