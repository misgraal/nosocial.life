from dataclasses import dataclass
from app.db.app import *
from config import DISKS, system
import os

@dataclass
class StartUpResult:
    folders: list
    files: list

@dataclass
class folderContent:
    content: dict

async def home(user_id) -> StartUpResult:
    username = await get_user_username_by_id(user_id)

    rootFolder = await get_users_root_folder(user_id)
    if rootFolder == ():
        await add_root_folder(user_id, username)


    """    for disk in DISKS:
            if system == "darwin":
                if os.path.isdir(f"{disk}/{username}") == False:
                    os.makedirs(f"{disk}/{username}")
                    await add_root_folder(user_id, username, f"{disk}/{username}")
            if system == "win":
                if os.path.isdir(f"{disk}\\{username}") == False:
                    os.makedirs(f"{disk}\\{username}")
                    await add_root_folder(user_id, username, f"{disk}\\{username}")"""
        

    inRootFolders = await get_users_roots_child_folders(user_id)
    inRootFiles = await get_users_roots_child_files(user_id)
    
    return StartUpResult(inRootFolders, inRootFiles)

async def create_folder(folderName, userID):
    await create_folder_db(folderName, userID) # сделать учет текущей папки

async def getFoldersContent(folderID) -> folderContent:
    ...