from app.db.db import fetch_one, fetch_all, execute

async def get_user_username_by_id(id: int):
    res = await fetch_one("SELECT username FROM users WHERE userID=%s", (id,))
    return res["username"]

async def add_root_folder(userID, folderName, serverPath):
    res = await execute("insert into folders (userID, folderName, serverPath, createdAt, lastModified) values (%s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)", (userID, folderName, serverPath,))
    return res

async def get_users_roots_child_folders(id: int):
    res = await fetch_all("SELECT folderID, folderName from folders where userID=%s and parentFolderID=(SELECT folderID from folders where userID=%s and parentFolderID is null)", (id,))
    return res