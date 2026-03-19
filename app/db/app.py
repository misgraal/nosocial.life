from app.db.db import fetch_one, fetch_all, execute
from app.security.folderHashGenerator import generateRandomHash

async def get_user_username_by_id(id: int):
    res = await fetch_one("SELECT username FROM users WHERE userID=%s", (id,))
    return res["username"]

async def add_root_folder(userID, folderName, serverPath):
    res = await execute("insert into folders (userID, folderName, serverPath, createdAt, lastModified, publicID) values (%s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)", (userID, folderName, serverPath, generateRandomHash(),))
    return res

async def get_users_roots_child_folders(id: int):
    res = await fetch_all("SELECT folderID, folderName, lastModified from folders where userID=%s and parentFolderID in (select folderID from folders where userID=%s and parentFolderID is null)", (id, id,))
    return res

async def get_users_roots_child_files(id: int):
    res = await fetch_all("select fileID, fileName, sizeBytes, previewPath, lastModified from files where userID = %s and folderID is null", (id,))
    return res

async def get_users_folder_content(folderID):
    res = await fetch_all("SELECT folderID, folderName from folders where parentFolderID = %s", (folderID,))
    return res