from app.db.db import fetch_one, fetch_all, execute
from app.security.folderHashGenerator import generateRandomHash

async def get_user_username_by_id(id: int):
    res = await fetch_one("SELECT username FROM users WHERE userID=%s", (id,))
    return res["username"]

async def get_users_root_folder(id: int):
    res = await fetch_all("select folderID from folders where userID=%s and parentFolderID is null", (id,))
    return res

async def add_root_folder(userID, folderName):
    res = await execute("insert into folders (userID, folderName, createdAt, lastModified, publicID) values (%s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, %s)", (userID, folderName, generateRandomHash(),))
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

async def create_folder_db(folderName, userID, parentFolderID):
    res = await execute("insert into folders (userID, folderName, parentFolderID, createdAt, lastModified, publicID) values (%s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, %s)", (userID, folderName, parentFolderID, generateRandomHash(),))
    return res