from datetime import datetime
import os
import tempfile
import zipfile
from urllib.parse import urlparse

from app.db.app import get_user_username_by_id
from app.db.app import create_audit_log
from pathlib import Path

from app.db.files import (
    get_folders_child_files,
    get_folders_child_files_for_download,
    get_shared_files_for_user,
    get_users_roots_child_files,
)
from app.db.folders import (
    add_root_folder,
    create_folder_db,
    create_public_folder_db,
    delete_folder_by_id,
    get_all_user_folders,
    get_folder_by_id,
    get_folder_by_public_id,
    get_folder_id_by_public_id,
    get_folders_by_name,
    get_folders_by_public_id,
    get_folders_child_folders,
    get_folders_names_in_folder,
    get_folder_shared_users,
    get_parent_folder,
    get_shared_root_folders_for_user,
    get_user_folder_by_name_in_parent,
    is_folder_shared_with_user,
    replace_folder_shared_users,
    update_folder_share_settings_db,
    update_folder_public_db,
    get_user_folder_by_id,
    get_user_folder_id_by_public_id,
    get_user_folder_by_public_id,
    get_users_root_folder,
    get_users_roots_child_folders,
    move_child_folders_to_folder,
    move_folder_files_to_folder,
    update_folder_identity_db,
    update_folder_public_id_db,
)
from config import DISKS, MEDIA_FOLDER_NAME, MEDIA_FOLDER_PUBLIC_ID
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
    sanitize_item_name,
)


async def home(user_id) -> StartUpResult:
    root_folder = await ensure_root_folder(user_id)
    media_folder = await ensure_media_folder(user_id, root_folder["folderID"])

    inRootFolders = await get_users_roots_child_folders(user_id)
    inRootFiles = await get_users_roots_child_files(user_id)
    shared_folders = mark_shared_items(await get_shared_root_folders_for_user(user_id))
    shared_files = mark_shared_items(await get_shared_files_for_user(user_id))
    all_folders = await get_all_user_folders(user_id)

    inRootFolders = add_media_folder_to_root_listing(inRootFolders, media_folder)
    inRootFolders.extend(shared_folders)
    inRootFiles.extend(shared_files)
    all_folders = add_media_folder_to_user_tree(all_folders, media_folder, root_folder["folderID"])
    breadcrumbs = [{
        "label": root_folder["folderName"],
        "url": "/app/home",
        "current": True
    }]
    folder_tree = build_folder_tree_nodes(all_folders, root_folder["folderID"])

    return StartUpResult(inRootFolders, inRootFiles, breadcrumbs, folder_tree)


def mark_shared_items(items: list[dict]) -> list[dict]:
    marked_items = []
    for item in items:
        marked_item = dict(item)
        marked_item["shared"] = True
        marked_items.append(marked_item)
    return marked_items


async def ensure_root_folder(user_id: int) -> dict:
    root_folders = await get_users_root_folder(user_id)
    if root_folders:
        return root_folders[0]

    username = await get_user_username_by_id(user_id)
    await add_root_folder(user_id, username)
    return (await get_users_root_folder(user_id))[0]


async def ensure_media_folder(user_id: int, root_folder_id: int) -> dict:
    return await ensure_shared_media_folder(user_id, root_folder_id)


async def ensure_shared_media_folder(user_id: int, root_folder_id: int) -> dict:
    candidates = await get_folders_by_public_id(MEDIA_FOLDER_PUBLIC_ID)
    name_matches = await get_folders_by_name(MEDIA_FOLDER_NAME)
    candidates_by_id = {folder["folderID"]: folder for folder in candidates}
    for folder in name_matches:
        candidates_by_id.setdefault(folder["folderID"], folder)

    if candidates_by_id:
        canonical = sorted(candidates_by_id.values(), key=lambda folder: folder["folderID"])[0]
        canonical = await update_folder_identity_db(
            canonical["folderID"],
            MEDIA_FOLDER_NAME,
            MEDIA_FOLDER_PUBLIC_ID,
            True
        )
        for duplicate in sorted(candidates_by_id.values(), key=lambda folder: folder["folderID"]):
            if duplicate["folderID"] == canonical["folderID"]:
                continue
            await move_folder_files_to_folder(duplicate["folderID"], canonical["folderID"])
            await move_child_folders_to_folder(duplicate["folderID"], canonical["folderID"])
            await delete_folder_by_id(duplicate["folderID"])
        return canonical

    created_folder = await create_public_folder_db(
        MEDIA_FOLDER_NAME,
        user_id,
        root_folder_id,
        MEDIA_FOLDER_PUBLIC_ID
    )
    created_folder_detail = await get_folder_by_public_id(MEDIA_FOLDER_PUBLIC_ID)
    await create_audit_log(
        user_id,
        "folder.created",
        "folder",
        MEDIA_FOLDER_PUBLIC_ID,
        {"folderName": MEDIA_FOLDER_NAME, "parentFolderID": root_folder_id, "public": True, "shared": True}
    )
    return created_folder_detail or created_folder


def media_folder_summary(folder: dict) -> dict:
    return {
        "publicID": MEDIA_FOLDER_PUBLIC_ID,
        "public": True,
        "publicExpiresAt": None,
        "folderName": MEDIA_FOLDER_NAME,
        "lastModified": folder.get("lastModified")
    }


def add_media_folder_to_root_listing(folders: list[dict], media_folder: dict) -> list[dict]:
    regular_folders = [
        folder for folder in folders
        if folder.get("publicID") != MEDIA_FOLDER_PUBLIC_ID
        and str(folder.get("folderName") or "").casefold() != MEDIA_FOLDER_NAME.casefold()
    ]
    return [media_folder_summary(media_folder), *regular_folders]


def add_media_folder_to_user_tree(folders: list[dict], media_folder: dict, root_folder_id: int) -> list[dict]:
    tree_folders = [
        folder for folder in folders
        if folder.get("folderID") != media_folder["folderID"]
        and folder.get("publicID") != MEDIA_FOLDER_PUBLIC_ID
    ]
    tree_folders.append({
        "folderID": media_folder["folderID"],
        "publicID": MEDIA_FOLDER_PUBLIC_ID,
        "public": True,
        "publicExpiresAt": None,
        "folderName": MEDIA_FOLDER_NAME,
        "parentFolderID": root_folder_id
    })
    return tree_folders


async def get_folder_path_parts(folder: dict) -> list[str]:
    parts = []
    current_folder = folder

    while current_folder:
        parts.append(current_folder["folderName"])
        parent_folder_id = current_folder["parentFolderID"]
        if parent_folder_id is None:
            break
        current_folder = await get_folder_by_id(parent_folder_id)

    return list(reversed(parts))


async def is_media_folder(folder: dict) -> bool:
    folder_parts = await get_folder_path_parts(folder)
    return len(folder_parts) == 2 and folder_parts[1] == MEDIA_FOLDER_NAME


def get_media_dirs() -> list[str]:
    return [str(Path(disk_path) / MEDIA_FOLDER_NAME) for disk_path in DISKS]


async def check_dublicate(userID, parentFolderID, newFolderName):
    folderNames = await get_folders_names_in_folder(userID, parentFolderID)
    for folderName in folderNames:
        if folderName["folderName"] == newFolderName:
            return 1
    return 0


async def create_folder(folderName, userID, url: str):
    folderName = sanitize_item_name(folderName)
    parentPublicID = urlparse(url or "").path.rstrip("/").split("/")[-1]
    if parentPublicID == "home":
        parentFolder = await get_users_root_folder(userID)
        if not parentFolder:
            raise ValueError("Root folder was not found")
        parentFolderID = parentFolder[0]["folderID"]
    elif parentPublicID == MEDIA_FOLDER_PUBLIC_ID:
        parentFolder = await get_folder_by_public_id(MEDIA_FOLDER_PUBLIC_ID)
        if not parentFolder:
            raise ValueError("Movies folder was not found")
        parentFolderID = parentFolder["folderID"]
    else:
        parentFolder = await get_user_folder_id_by_public_id(userID, parentPublicID)
        if not parentFolder:
            raise ValueError("Parent folder was not found")
        parentFolderID = parentFolder["folderID"]

    if await check_dublicate(userID, parentFolderID, folderName) == 1:
        return 1

    folder = await create_folder_db(folderName, userID, parentFolderID)
    parent_folder = await get_folder_by_id(parentFolderID)
    if parent_folder and parent_folder.get("public"):
        folder_row = await get_folder_id_by_public_id(folder["publicID"])
        folder = await update_folder_public_db(userID, folder_row["folderID"], True)

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
    if folder["publicID"] == MEDIA_FOLDER_PUBLIC_ID:
        root_folder = await ensure_root_folder(user_id)
        return [
            {
                "label": root_folder["folderName"],
                "url": "/app/home",
                "current": False
            },
            {
                "label": MEDIA_FOLDER_NAME,
                "url": f"/app/folders/{MEDIA_FOLDER_PUBLIC_ID}",
                "current": True
            }
        ]

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
    if publicID == MEDIA_FOLDER_PUBLIC_ID:
        root_folder = await ensure_root_folder(user_id)
        folder = await ensure_media_folder(user_id, root_folder["folderID"])
    else:
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
    if folder["publicID"] == MEDIA_FOLDER_PUBLIC_ID:
        root_folder = await ensure_root_folder(user_id)
        all_folders = add_media_folder_to_user_tree(all_folders, folder, root_folder["folderID"])
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
    root_folder = await ensure_root_folder(user_id)
    media_folder = await ensure_media_folder(user_id, root_folder["folderID"])
    folders = add_media_folder_to_user_tree(
        await get_all_user_folders(user_id),
        media_folder,
        root_folder["folderID"]
    )

    folders_by_id = {folder["folderID"]: folder for folder in folders}

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


def sanitize_zip_name(value: str, fallback: str = "item") -> str:
    name = str(value or "").replace("\\", "_").replace("/", "_").strip()
    name = "".join(
        character if ord(character) >= 32 else "_"
        for character in name
    )
    return name.strip(". ") or fallback


def get_unique_zip_path(path: str, used_paths: set[str]) -> str:
    normalized_path = path.strip("/")
    if normalized_path not in used_paths:
        used_paths.add(normalized_path)
        return normalized_path

    parent, name = normalized_path.rsplit("/", 1) if "/" in normalized_path else ("", normalized_path)
    stem, extension = os.path.splitext(name)
    index = 2
    while True:
        candidate_name = f"{stem} ({index}){extension}"
        candidate_path = f"{parent}/{candidate_name}" if parent else candidate_name
        if candidate_path not in used_paths:
            used_paths.add(candidate_path)
            return candidate_path
        index += 1


async def collect_folder_zip_entries(folder: dict, include_private: bool) -> tuple[str, list[str], list[dict]]:
    root_name = sanitize_zip_name(folder["folderName"], "folder")
    folder_entries = [root_name]
    file_entries = []
    used_paths = {root_name}

    async def collect(current_folder: dict, current_zip_path: str):
        child_folders = await get_folders_child_folders(current_folder["folderID"])
        for child_folder in child_folders:
            if not include_private and not is_public_folder_accessible(child_folder):
                continue

            folder_name = sanitize_zip_name(child_folder["folderName"], "folder")
            child_zip_path = get_unique_zip_path(f"{current_zip_path}/{folder_name}", used_paths)
            folder_entries.append(child_zip_path)
            await collect(child_folder, child_zip_path)

        child_files = await get_folders_child_files_for_download(current_folder["folderID"])
        for child_file in child_files:
            if not include_private and not is_public_file_row_accessible(child_file):
                continue
            if not include_private and not child_file.get("publicAllowDownload", True):
                continue

            file_name = sanitize_zip_name(child_file["fileName"], "file")
            archive_path = get_unique_zip_path(f"{current_zip_path}/{file_name}", used_paths)
            file_entries.append({
                "archivePath": archive_path,
                "serverPath": child_file["serverPath"]
            })

    await collect(folder, root_name)
    return root_name, folder_entries, file_entries


def create_folder_zip_file(root_name: str, folder_entries: list[str], file_entries: list[dict]) -> str:
    archive_handle = tempfile.NamedTemporaryFile(prefix="nosocial-folder-", suffix=".zip", delete=False)
    archive_path = archive_handle.name
    archive_handle.close()

    try:
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for folder_path in folder_entries:
                archive.writestr(f"{folder_path.rstrip('/')}/", "")

            for file_entry in file_entries:
                file_path = Path(file_entry["serverPath"])
                if not file_path.exists() or not file_path.is_file():
                    continue
                archive.write(file_path, file_entry["archivePath"])
    except Exception:
        Path(archive_path).unlink(missing_ok=True)
        raise

    return archive_path
