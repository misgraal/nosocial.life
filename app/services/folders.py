from datetime import datetime

from app.db.app import get_user_username_by_id
from app.db.app import create_audit_log
from app.db.files import get_folders_child_files, get_shared_files_for_user, get_users_roots_child_files
from app.db.folders import (
    add_root_folder,
    create_folder_db,
    get_all_user_folders,
    get_folder_by_id,
    get_folder_by_public_id,
    get_folder_id_by_public_id,
    get_folders_child_folders,
    get_folders_names_in_folder,
    get_folder_shared_users,
    get_parent_folder,
    get_shared_root_folders_for_user,
    is_folder_shared_with_user,
    replace_folder_shared_users,
    update_folder_share_settings_db,
    update_folder_public_db,
    get_user_folder_by_id,
    get_user_folder_by_public_id,
    get_users_root_folder,
    get_users_roots_child_folders,
)
from app.security.passwords import hash_password
from app.services.app import (
    StartUpResult,
    build_folder_path,
    build_folder_tree_nodes,
    createFolder,
    folderContent,
    normalize_share_expires_at,
    parse_python_datetime,
    resolve_share_recipient_users,
)


async def home(user_id) -> StartUpResult:
    username = await get_user_username_by_id(user_id)

    rootFolder = await get_users_root_folder(user_id)
    if not rootFolder:
        await add_root_folder(user_id, username)
        rootFolder = await get_users_root_folder(user_id)

    inRootFolders = await get_users_roots_child_folders(user_id)
    inRootFiles = await get_users_roots_child_files(user_id)
    all_folders = await get_all_user_folders(user_id)

    root_folder = rootFolder[0]
    breadcrumbs = [{
        "label": root_folder["folderName"],
        "url": "/app/home",
        "current": True
    }]
    folder_tree = build_folder_tree_nodes(all_folders, root_folder["folderID"])

    return StartUpResult(inRootFolders, inRootFiles, breadcrumbs, folder_tree)


async def check_dublicate(userID, parentFolderID, newFolderName):
    folderNames = await get_folders_names_in_folder(userID, parentFolderID)
    for folderName in folderNames:
        if folderName["folderName"] == newFolderName:
            return 1
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
    await create_audit_log(
        userID,
        "folder.created",
        "folder",
        folder["publicID"],
        {"folderName": folderName, "parentFolderID": parentFolderID}
    )
    return createFolder(folder)


async def checkRoot(folderID) -> bool:
    res = await get_parent_folder(folderID)
    if res["parentFolderID"]:
        return False
    return True


async def build_breadcrumbs(user_id: int, folder: dict) -> list[dict]:
    ancestors = []
    current_folder = folder

    while current_folder:
        ancestors.append(current_folder)
        parent_folder_id = current_folder["parentFolderID"]
        if parent_folder_id is None:
            break
        current_folder = await get_user_folder_by_id(user_id, parent_folder_id)

    breadcrumbs = []
    for index, breadcrumb_folder in enumerate(reversed(ancestors)):
        is_root = breadcrumb_folder["parentFolderID"] is None
        is_current = index == len(ancestors) - 1
        breadcrumbs.append({
            "label": breadcrumb_folder["folderName"],
            "url": "/app/home" if is_root else f"/app/folders/{breadcrumb_folder['publicID']}",
            "current": is_current
        })

    return breadcrumbs


async def getFoldersContent(user_id: int, publicID: str) -> folderContent:
    folder = await get_user_folder_by_public_id(user_id, publicID)
    if not folder:
        raise ValueError("Folder was not found")

    rootFolder = await checkRoot(folder["folderID"])
    if rootFolder:
        return "root"

    childFolders = await get_folders_child_folders(folder["folderID"])
    childFiles = await get_folders_child_files(folder["folderID"])
    breadcrumbs = await build_breadcrumbs(user_id, folder)
    all_folders = await get_all_user_folders(user_id)
    folder_tree = build_folder_tree_nodes(all_folders, folder["folderID"])

    return folderContent(childFolders, childFiles, breadcrumbs, folder_tree)


async def get_folder_shared_usernames(folder_id: int) -> list[str]:
    shared_users = await get_folder_shared_users(folder_id)
    return [user["username"] for user in shared_users]


async def get_user_shared_root_ancestor(folder_id: int, user_id: int) -> dict | None:
    current_folder = await get_folder_by_id(folder_id)

    while current_folder:
        if await is_folder_shared_with_user(current_folder["folderID"], user_id):
            return current_folder

        parent_folder_id = current_folder["parentFolderID"]
        if parent_folder_id is None:
            return None
        current_folder = await get_folder_by_id(parent_folder_id)

    return None


async def can_user_access_shared_folder(user_id: int | None, folder: dict | None) -> bool:
    if not user_id or not folder:
        return False
    if folder["userID"] == user_id:
        return True
    return bool(await get_user_shared_root_ancestor(folder["folderID"], user_id))


def build_shared_tree_node(root_folder: dict, folders_by_id: dict[int, dict], active_folder_id: int | None) -> dict:
    children_by_parent = {}
    for folder in folders_by_id.values():
        children_by_parent.setdefault(folder["parentFolderID"], []).append(folder)

    for child_folders in children_by_parent.values():
        child_folders.sort(key=lambda folder: folder["folderName"].lower())

    active_folder_ids = set()
    current_active_id = active_folder_id
    while current_active_id is not None and current_active_id in folders_by_id:
        active_folder_ids.add(current_active_id)
        current_active_id = folders_by_id[current_active_id]["parentFolderID"]

    def build_node(folder: dict) -> dict:
        return {
            "folderID": folder["folderID"],
            "publicID": folder["publicID"],
            "folderName": folder["folderName"],
            "isRoot": False,
            "url": f"/app/folders/{folder['publicID']}",
            "active": folder["folderID"] == active_folder_id,
            "expanded": folder["folderID"] in active_folder_ids or folder["folderID"] == root_folder["folderID"],
            "children": [
                build_node(child_folder)
                for child_folder in children_by_parent.get(folder["folderID"], [])
            ]
        }

    return build_node(root_folder)


async def build_shared_folder_tree(user_id: int, active_folder_id: int | None) -> dict:
    shared_root_folders = await get_shared_root_folders_for_user(user_id)
    tree_children = []

    for shared_root in shared_root_folders:
        owner_folders = await get_all_user_folders(shared_root["userID"])
        owner_folders_by_id = {folder["folderID"]: folder for folder in owner_folders}
        if shared_root["folderID"] not in owner_folders_by_id:
            owner_folders_by_id[shared_root["folderID"]] = dict(shared_root)

        subtree_folder_ids = set()
        pending_folder_ids = [shared_root["folderID"]]
        while pending_folder_ids:
            current_folder_id = pending_folder_ids.pop()
            if current_folder_id in subtree_folder_ids:
                continue
            subtree_folder_ids.add(current_folder_id)

            current_folder = owner_folders_by_id.get(current_folder_id)
            if not current_folder:
                continue

            for folder in owner_folders:
                if folder["parentFolderID"] == current_folder["folderID"]:
                    pending_folder_ids.append(folder["folderID"])

        subtree_folders_by_id = {
            folder_id: dict(owner_folders_by_id[folder_id])
            for folder_id in subtree_folder_ids
            if folder_id in owner_folders_by_id
        }
        tree_children.append(build_shared_tree_node(shared_root, subtree_folders_by_id, active_folder_id))

    tree_children.sort(key=lambda folder: folder["folderName"].lower())
    return {
        "folderID": 0,
        "publicID": "shared-root",
        "folderName": "Shared with me",
        "isRoot": True,
        "url": "/app/shared",
        "active": active_folder_id is None,
        "expanded": True,
        "children": tree_children
    }


async def get_shared_root_content(user_id: int) -> folderContent:
    shared_folders = await get_shared_root_folders_for_user(user_id)
    shared_files = await get_shared_files_for_user(user_id)

    breadcrumbs = [{
        "label": "Shared with me",
        "url": "/app/shared",
        "current": True
    }]

    return folderContent(
        shared_folders,
        shared_files,
        breadcrumbs,
        await build_shared_folder_tree(user_id, None)
    )


async def build_shared_breadcrumbs(shared_root: dict, folder: dict, folders_by_id: dict[int, dict]) -> list[dict]:
    breadcrumbs = [{
        "label": "Shared with me",
        "url": "/app/shared",
        "current": False
    }]

    ancestors = []
    current_folder = folder
    while current_folder:
        ancestors.append(current_folder)
        if current_folder["folderID"] == shared_root["folderID"]:
            break

        parent_folder_id = current_folder["parentFolderID"]
        current_folder = folders_by_id.get(parent_folder_id)

    for index, breadcrumb_folder in enumerate(reversed(ancestors)):
        is_current = index == len(ancestors) - 1
        breadcrumbs.append({
            "label": breadcrumb_folder["folderName"],
            "url": f"/app/folders/{breadcrumb_folder['publicID']}",
            "current": is_current
        })

    return breadcrumbs


async def get_shared_folder_content(user_id: int, publicID: str) -> folderContent:
    folder = await get_folder_by_public_id(publicID)
    if not folder:
        raise ValueError("Folder was not found")

    shared_root = await get_user_shared_root_ancestor(folder["folderID"], user_id)
    if not shared_root:
        raise ValueError("Folder was not found")

    child_folders = await get_folders_child_folders(folder["folderID"])
    child_files = await get_folders_child_files(folder["folderID"])
    owner_folders = await get_all_user_folders(folder["userID"])
    folders_by_id = {owner_folder["folderID"]: owner_folder for owner_folder in owner_folders}
    breadcrumbs = await build_shared_breadcrumbs(shared_root, folder, folders_by_id)
    folder_tree = await build_shared_folder_tree(user_id, folder["folderID"])

    return folderContent(child_folders, child_files, breadcrumbs, folder_tree)


async def get_move_targets(user_id: int) -> dict:
    folders = await get_all_user_folders(user_id)
    if not folders:
        username = await get_user_username_by_id(user_id)
        await add_root_folder(user_id, username)
        folders = await get_all_user_folders(user_id)

    folders_by_id = {folder["folderID"]: folder for folder in folders}
    root_folder = next((folder for folder in folders if folder["parentFolderID"] is None), None)
    if not root_folder:
        raise ValueError("Root folder was not found")

    options = [{
        "publicID": root_folder["publicID"],
        "folderName": root_folder["folderName"],
        "path": root_folder["folderName"],
        "isRoot": True
    }]

    for folder in folders:
        if folder["folderID"] == root_folder["folderID"]:
            continue

        options.append({
            "publicID": folder["publicID"],
            "folderName": folder["folderName"],
            "path": build_folder_path(folder["folderID"], folders_by_id),
            "isRoot": False
        })

    return {
        "folders": options,
        "rootPublicID": root_folder["publicID"]
    }


def get_folder_share_access_cookie_name(folder_public_id: str) -> str:
    return f"share_folder_{folder_public_id}"


def is_public_folder_accessible(folder: dict) -> bool:
    if not folder or not folder.get("public"):
        return False

    expires_at = parse_python_datetime(folder.get("publicExpiresAt"))
    if not expires_at:
        return True

    return expires_at >= datetime.now()


def is_public_file_row_accessible(file_row: dict) -> bool:
    if not file_row or not file_row.get("public"):
        return False

    expires_at = parse_python_datetime(file_row.get("publicExpiresAt"))
    if not expires_at:
        return True

    return expires_at >= datetime.now()


async def set_folder_visibility(user_id: int, folder_public_id: str, is_public: bool) -> dict:
    folder = await get_user_folder_by_public_id(user_id, folder_public_id)
    if not folder:
        raise ValueError("Folder was not found")

    updated_folder = await update_folder_public_db(user_id, folder["folderID"], is_public)
    await create_audit_log(
        user_id,
        "folder.visibility.updated",
        "folder",
        updated_folder["publicID"],
        {"public": bool(updated_folder["public"])}
    )
    return {
        "folder": updated_folder,
        "publicUrl": f"/app/folders/{updated_folder['publicID']}"
    }


async def update_folder_share_settings(
    user_id: int,
    folder_public_id: str,
    is_public: bool,
    expires_at: str | None,
    password: str | None,
    clear_password: bool,
    shared_users: list[str] | None = None
) -> dict:
    folder = await get_user_folder_by_public_id(user_id, folder_public_id)
    if not folder:
        raise ValueError("Folder was not found")

    recipient_users = await resolve_share_recipient_users(user_id, shared_users)
    expires_at_value = normalize_share_expires_at(expires_at)
    password_hash = folder.get("publicPasswordHash")
    if clear_password:
        password_hash = None
    elif password and password.strip():
        password_hash = hash_password(password.strip())

    updated_folder = await update_folder_share_settings_db(
        user_id,
        folder["folderID"],
        is_public,
        expires_at_value,
        password_hash
    )
    await replace_folder_shared_users(
        folder["folderID"],
        [recipient_user["userID"] for recipient_user in recipient_users]
    )
    await create_audit_log(
        user_id,
        "folder.share.updated",
        "folder",
        updated_folder["publicID"],
        {
            "public": bool(updated_folder["public"]),
            "expiresAt": expires_at_value.isoformat() if expires_at_value else None,
            "passwordProtected": bool(updated_folder.get("publicPasswordHash")),
            "sharedUsers": [recipient_user["username"] for recipient_user in recipient_users]
        }
    )
    return {
        "folder": updated_folder,
        "publicUrl": f"/app/folders/{updated_folder['publicID']}",
        "sharedUsers": [recipient_user["username"] for recipient_user in recipient_users]
    }


async def get_folder_share_settings(user_id: int, folder_public_id: str) -> dict:
    folder = await get_user_folder_by_public_id(user_id, folder_public_id)
    if not folder:
        raise ValueError("Folder was not found")

    return {
        "folder": folder,
        "sharedUsers": await get_folder_shared_usernames(folder["folderID"])
    }


async def build_public_folder_tree_node(folder: dict, active_folder_id: int) -> dict:
    child_folders = await get_folders_child_folders(folder["folderID"])
    public_child_folders = [child_folder for child_folder in child_folders if is_public_folder_accessible(child_folder)]

    return {
        "folderID": folder["folderID"],
        "publicID": folder["publicID"],
        "folderName": folder["folderName"],
        "isRoot": folder["parentFolderID"] is None,
        "url": f"/app/folders/{folder['publicID']}",
        "active": folder["folderID"] == active_folder_id,
        "expanded": True,
        "children": [
            await build_public_folder_tree_node(child_folder, active_folder_id)
            for child_folder in public_child_folders
        ]
    }


async def get_public_folder_content(publicID: str) -> folderContent:
    folder = await get_folder_by_public_id(publicID)
    if not folder or not is_public_folder_accessible(folder):
        raise ValueError("Folder was not found")

    child_folders = [
        child_folder
        for child_folder in await get_folders_child_folders(folder["folderID"])
        if is_public_folder_accessible(child_folder)
    ]
    child_files = [
        child_file
        for child_file in await get_folders_child_files(folder["folderID"])
        if is_public_file_row_accessible(child_file)
    ]
    breadcrumbs = [{
        "label": folder["folderName"],
        "url": f"/app/folders/{folder['publicID']}",
        "current": True
    }]
    folder_tree = await build_public_folder_tree_node(folder, folder["folderID"])

    return folderContent(child_folders, child_files, breadcrumbs, folder_tree)
