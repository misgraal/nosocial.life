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
    folders: list
    #files: list

@dataclass
class createFolder:
    folder: dict

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

async def check_dublicate(userID, parentFolderID, newFolderName):
    folderNames = await get_folders_names_in_folder(userID, parentFolderID)
    for folderName in folderNames:
        if folderName["folderName"] == newFolderName:
            return 1 # Folder already exists
    return 0

async def create_folder(folderName, userID, url: str):
    parentPublicID = url.split("/")[-1]
    if parentPublicID == "home":
        parentFolder = await get_users_root_folder(userID)
        parentFolderID = parentFolder[0]["folderID"]
    else:
        parentFolder = await get_folder_id_by_public_id(parentPublicID)
        parentFolderID = parentFolder["folderID"]
    if await check_dublicate(userID, parentFolderID, folderName) == 1:
        return 1

    folder = await create_folder_db(folderName, userID, parentFolderID)
    return createFolder(folder)

async def checkRoot(folderID) -> bool:
    res = await get_parent_folder(folderID)
    if res["parentFolderID"]:
        return False
    else: return True

async def getFoldersContent(publicID) -> folderContent:
    f = await get_folder_id_by_public_id(publicID)
    folderID = f["folderID"]
    rootFolder = await checkRoot(folderID)
    if rootFolder:
        return "root"
    else:
        childFolders = await get_folders_child_folders(folderID)
        childFiles = ...

        return folderContent(childFolders)

