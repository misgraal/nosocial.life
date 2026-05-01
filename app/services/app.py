from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.db.admin import get_users_by_usernames
from app.db.app import create_audit_log
from app.db.files import (
    get_folders_child_files,
    get_user_file_by_name_in_folder,
    get_user_file_by_public_id,
    search_user_files_by_name,
    update_file_folder_db,
    update_file_name_db,
    update_file_public_db,
)
from app.db.folders import (
    get_all_user_folders,
    get_folders_child_folders,
    get_user_folder_by_name_in_parent,
    get_user_folder_by_public_id,
    search_user_folders_by_name,
    update_folder_name_db,
    update_folder_parent_db,
    update_folder_public_db,
)
from config import MEDIA_FOLDER_NAME

@dataclass
class StartUpResult:
    folders: list
    files: list
    breadcrumbs: list
    folder_tree: dict

@dataclass
class folderContent:
    folders: list
    files: list
    breadcrumbs: list
    folder_tree: dict

@dataclass
class createFolder:
    folder: dict

@dataclass
class UploadChunkPayload:
    upload_id: str
    file_name: str
    mime_type: str
    file_size: int
    chunk_index: int
    total_chunks: int
    chunk_size: int
    is_last_chunk: bool
    current_url: str
    folder_public_id: str | None = None
    relative_path: str | None = None
    chunk_start: int | None = None

@dataclass
class DeleteItemsPayload:
    folder_public_ids: list[str]
    file_public_ids: list[str]

@dataclass
class RenameItemPayload:
    folder_public_id: str | None = None
    file_public_id: str | None = None
    new_name: str = ""

@dataclass
class MoveItemsPayload:
    folder_public_ids: list[str]
    file_public_ids: list[str]
    destination_public_id: str | None = None

@dataclass
class UpdateFileVisibilityPayload:
    file_public_id: str
    is_public: bool

@dataclass
class UpdateFolderVisibilityPayload:
    folder_public_id: str
    is_public: bool


@dataclass
class UpdateFileShareSettingsPayload:
    file_public_id: str
    is_public: bool
    expires_at: str | None = None
    password: str | None = None
    clear_password: bool = False
    allow_download: bool = True
    shared_users: list[str] | None = None


@dataclass
class UpdateFolderShareSettingsPayload:
    folder_public_id: str
    is_public: bool
    expires_at: str | None = None
    password: str | None = None
    clear_password: bool = False
    shared_users: list[str] | None = None


def build_folder_tree_nodes(folders: list[dict], active_folder_id: int | None) -> dict:
    folders_by_id = {}
    children_by_parent = {}

    for folder in folders:
        folder_copy = dict(folder)
        folder_copy["children"] = []
        folders_by_id[folder_copy["folderID"]] = folder_copy
        children_by_parent.setdefault(folder_copy["parentFolderID"], []).append(folder_copy)

    for child_folders in children_by_parent.values():
        child_folders.sort(key=lambda folder: folder["folderName"].lower())

    active_folder_ids = set()
    current_active_id = active_folder_id
    while current_active_id is not None and current_active_id in folders_by_id:
        active_folder_ids.add(current_active_id)
        current_active_id = folders_by_id[current_active_id]["parentFolderID"]

    def attach_children(folder: dict) -> dict:
        children = [attach_children(child) for child in children_by_parent.get(folder["folderID"], [])]
        is_root = folder["parentFolderID"] is None

        return {
            "folderID": folder["folderID"],
            "publicID": folder["publicID"],
            "folderName": folder["folderName"],
            "isRoot": is_root,
            "url": "/app/home" if is_root else f"/app/folders/{folder['publicID']}",
            "active": folder["folderID"] == active_folder_id,
            "expanded": is_root or folder["folderID"] in active_folder_ids,
            "children": children
        }

    root_folder = next((folder for folder in folders if folder["parentFolderID"] is None), None)
    if not root_folder:
        raise ValueError("Root folder was not found")

    return attach_children(root_folder)

def sanitize_item_name(name: str) -> str:
    safe_name = Path(name or "").name.strip()
    if not safe_name or safe_name in {".", ".."}:
        raise ValueError("Name is required")

    return safe_name


def normalize_shared_usernames(shared_users: list[str] | None) -> list[str]:
    if not shared_users:
        return []

    normalized_usernames = []
    seen_usernames = set()

    for raw_username in shared_users:
        username = str(raw_username or "").strip()
        if not username:
            continue
        username_key = username.casefold()
        if username_key in seen_usernames:
            continue
        seen_usernames.add(username_key)
        normalized_usernames.append(username)

    return normalized_usernames


async def resolve_share_recipient_users(owner_user_id: int, shared_users: list[str] | None) -> list[dict]:
    normalized_usernames = normalize_shared_usernames(shared_users)
    if not normalized_usernames:
        return []

    users = await get_users_by_usernames(normalized_usernames)
    users_by_key = {
        str(user["username"]).casefold(): user
        for user in users
    }
    missing_usernames = [
        username
        for username in normalized_usernames
        if username.casefold() not in users_by_key
    ]
    if missing_usernames:
        raise ValueError(f"Users were not found: {', '.join(missing_usernames)}")

    resolved_users = []
    for username in normalized_usernames:
        user = users_by_key[username.casefold()]
        if user["userID"] == owner_user_id:
            raise ValueError("You cannot share items with yourself")
        resolved_users.append(user)

    return resolved_users


def build_folder_path(folder_id: int, folders_by_id: dict[int, dict]) -> str:
    parts = []
    current_id = folder_id

    while current_id is not None and current_id in folders_by_id:
        folder = folders_by_id[current_id]
        parts.append(folder["folderName"])
        current_id = folder["parentFolderID"]

    return " / ".join(reversed(parts))


def is_media_folder_name(folder_name: str) -> bool:
    return str(folder_name or "").casefold() == MEDIA_FOLDER_NAME.casefold()


def get_folder_path_parts_from_tree(folder_id: int | None, folders_by_id: dict[int, dict]) -> list[str]:
    if folder_id is None:
        return []

    parts = []
    current_id = folder_id
    while current_id is not None and current_id in folders_by_id:
        folder = folders_by_id[current_id]
        parts.append(folder["folderName"])
        current_id = folder["parentFolderID"]

    return list(reversed(parts))


def is_media_folder_tree(folder_id: int | None, folders_by_id: dict[int, dict]) -> bool:
    folder_parts = get_folder_path_parts_from_tree(folder_id, folders_by_id)
    return len(folder_parts) >= 2 and is_media_folder_name(folder_parts[1])


async def make_folder_tree_public(user_id: int, folder_id: int):
    await update_folder_public_db(user_id, folder_id, True)

    for file in await get_folders_child_files(folder_id):
        detailed_file = await get_user_file_by_public_id(user_id, file["publicID"])
        if detailed_file:
            await update_file_public_db(user_id, detailed_file["fileID"], True)

    for child_folder in await get_folders_child_folders(folder_id):
        await make_folder_tree_public(user_id, child_folder["folderID"])


def normalize_share_expires_at(expires_at: str | None) -> datetime | None:
    normalized_value = (expires_at or "").strip()
    if not normalized_value:
        return None

    for pattern in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(normalized_value, pattern)
        except ValueError:
            continue

    raise ValueError("Invalid expiration date")


def parse_python_datetime(value):
    if not value:
        return None

    if isinstance(value, datetime):
        return value

    normalized_value = str(value).strip()
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(normalized_value, pattern)
        except ValueError:
            continue

    return None


async def rename_item(user_id: int, payload: RenameItemPayload) -> dict:
    new_name = sanitize_item_name(payload.new_name)

    if payload.folder_public_id and payload.file_public_id:
        raise ValueError("Only one item can be renamed at a time")

    if payload.folder_public_id:
        folder = await get_user_folder_by_public_id(user_id, payload.folder_public_id)
        if not folder:
            raise ValueError("Folder was not found")

        duplicate_folder = await get_user_folder_by_name_in_parent(
            user_id,
            folder["parentFolderID"],
            new_name,
            excludeFolderID=folder["folderID"]
        )
        if duplicate_folder:
            raise ValueError("Folder with this name already exists")

        updated_folder = await update_folder_name_db(user_id, folder["folderID"], new_name)
        await create_audit_log(
            user_id,
            "folder.renamed",
            "folder",
            updated_folder["publicID"],
            {"newName": new_name}
        )
        return {
            "itemType": "folder",
            "folder": updated_folder
        }

    if payload.file_public_id:
        file = await get_user_file_by_public_id(user_id, payload.file_public_id)
        if not file:
            raise ValueError("File was not found")

        duplicate_file = await get_user_file_by_name_in_folder(
            user_id,
            file["folderID"],
            new_name,
            excludeFileID=file["fileID"]
        )
        if duplicate_file:
            raise ValueError("File with this name already exists")

        current_path = Path(file["serverPath"])
        new_path = current_path.with_name(new_name)

        if current_path != new_path:
            if new_path.exists():
                raise ValueError("File with this name already exists")

            preview_path = file["previewPath"]
            new_preview_path = str(new_path) if preview_path == file["serverPath"] else preview_path

            moved_on_disk = False
            try:
                if current_path.exists():
                    current_path.rename(new_path)
                    moved_on_disk = True

                updated_file = await update_file_name_db(
                    user_id,
                    file["fileID"],
                    new_name,
                    str(new_path),
                    new_preview_path
                )
            except Exception:
                if moved_on_disk and new_path.exists() and not current_path.exists():
                    new_path.rename(current_path)
                raise
        else:
            updated_file = await update_file_name_db(
                user_id,
                file["fileID"],
                new_name,
                file["serverPath"],
                file["previewPath"]
            )

        await create_audit_log(
            user_id,
            "file.renamed",
            "file",
            updated_file["publicID"],
            {"newName": new_name}
        )
        return {
            "itemType": "file",
            "file": updated_file
        }

    raise ValueError("Item to rename is required")


def is_folder_descendant(destination_folder_id: int, folder_id: int, folders_by_id: dict[int, dict]) -> bool:
    current_id = destination_folder_id
    while current_id is not None:
        if current_id == folder_id:
            return True
        current_folder = folders_by_id.get(current_id)
        if not current_folder:
            break
        current_id = current_folder["parentFolderID"]

    return False


async def move_items(user_id: int, payload: MoveItemsPayload) -> dict:
    folders = await get_all_user_folders(user_id)
    folders_by_public_id = {folder["publicID"]: folder for folder in folders}
    folders_by_id = {folder["folderID"]: folder for folder in folders}

    if payload.destination_public_id:
        destination_folder = folders_by_public_id.get(payload.destination_public_id)
    else:
        destination_folder = next((folder for folder in folders if folder["parentFolderID"] is None), None)

    if not destination_folder:
        raise ValueError("Destination folder was not found")

    moved_folder_public_ids = []
    moved_file_public_ids = []

    for folder_public_id in payload.folder_public_ids:
        folder = await get_user_folder_by_public_id(user_id, folder_public_id)
        if not folder:
            continue

        if folder["folderID"] == destination_folder["folderID"]:
            raise ValueError("Folder cannot be moved into itself")

        if is_folder_descendant(destination_folder["folderID"], folder["folderID"], folders_by_id):
            raise ValueError("Folder cannot be moved into itself or its child folder")

        duplicate_folder = await get_user_folder_by_name_in_parent(
            user_id,
            destination_folder["folderID"],
            folder["folderName"],
            excludeFolderID=folder["folderID"]
        )
        if duplicate_folder:
            raise ValueError(f"Folder '{folder['folderName']}' already exists in destination")

        if folder["parentFolderID"] == destination_folder["folderID"]:
            continue

        await update_folder_parent_db(user_id, folder["folderID"], destination_folder["folderID"])
        folders_by_id[folder["folderID"]] = {
            **folder,
            "parentFolderID": destination_folder["folderID"],
        }
        if is_media_folder_tree(folder["folderID"], folders_by_id):
            await make_folder_tree_public(user_id, folder["folderID"])

        await create_audit_log(
            user_id,
            "folder.moved",
            "folder",
            folder_public_id,
            {
                "destinationPublicID": destination_folder["publicID"],
                "autoPublic": is_media_folder_tree(folder["folderID"], folders_by_id)
            }
        )
        moved_folder_public_ids.append(folder_public_id)

    for file_public_id in payload.file_public_ids:
        file = await get_user_file_by_public_id(user_id, file_public_id)
        if not file:
            continue

        duplicate_file = await get_user_file_by_name_in_folder(
            user_id,
            destination_folder["folderID"],
            file["fileName"],
            excludeFileID=file["fileID"]
        )
        if duplicate_file:
            raise ValueError(f"File '{file['fileName']}' already exists in destination")

        if file["folderID"] == destination_folder["folderID"]:
            continue

        await update_file_folder_db(user_id, file["fileID"], destination_folder["folderID"])
        if is_media_folder_tree(destination_folder["folderID"], folders_by_id):
            await update_file_public_db(user_id, file["fileID"], True)

        await create_audit_log(
            user_id,
            "file.moved",
            "file",
            file_public_id,
            {
                "destinationPublicID": destination_folder["publicID"],
                "autoPublic": is_media_folder_tree(destination_folder["folderID"], folders_by_id)
            }
        )
        moved_file_public_ids.append(file_public_id)

    return {
        "destinationPublicID": destination_folder["publicID"],
        "movedFolderPublicIds": moved_folder_public_ids,
        "movedFilePublicIds": moved_file_public_ids
    }


async def search_drive(
    user_id: int,
    query: str,
    limit: int = 100,
    kind: str | None = None,
    min_size: int | None = None,
    max_size: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None
) -> dict:
    normalized_query = (query or "").strip()
    normalized_kind = (kind or "all").strip().lower()
    if (
        not normalized_query
        and normalized_kind in {"", "all"}
        and min_size is None
        and max_size is None
        and not date_from
        and not date_to
    ):
        raise ValueError("Search query or filters are required")

    folders = await get_all_user_folders(user_id)
    folders_by_id = {folder["folderID"]: folder for folder in folders}
    search_term = normalized_query or ""
    found_folders = await search_user_folders_by_name(user_id, search_term, limit=limit)
    found_files = await search_user_files_by_name(user_id, search_term, limit=limit)

    date_from_value = parse_python_datetime(date_from)
    date_to_value = parse_python_datetime(date_to)

    def matches_file_kind(file_name: str) -> bool:
        extension = Path(file_name or "").suffix.lower()
        image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico", ".avif", ".heic"}
        video_extensions = {".mp4", ".webm", ".mov", ".m4v", ".ogv"}
        document_extensions = {
            ".pdf", ".txt", ".md", ".json", ".xml", ".html", ".css", ".js", ".ts",
            ".py", ".yml", ".yaml", ".log", ".sql", ".doc", ".docx", ".rtf",
            ".xls", ".xlsx", ".csv", ".tsv", ".ppt", ".pptx"
        }

        if normalized_kind in {"", "all"}:
            return True
        if normalized_kind == "folders":
            return False
        if normalized_kind == "files":
            return True
        if normalized_kind == "images":
            return extension in image_extensions
        if normalized_kind == "videos":
            return extension in video_extensions
        if normalized_kind == "docs":
            return extension in document_extensions
        return True

    def matches_date(value) -> bool:
        modified_at = parse_python_datetime(value)
        if not modified_at:
            return True
        if date_from_value and modified_at < date_from_value:
            return False
        if date_to_value and modified_at > date_to_value.replace(hour=23, minute=59, second=59):
            return False
        return True

    filtered_folders = [
        folder for folder in found_folders
        if normalized_kind in {"", "all", "folders"} and matches_date(folder["lastModified"])
    ]
    filtered_files = [
        file for file in found_files
        if matches_file_kind(file["fileName"])
        and (min_size is None or (file["sizeBytes"] or 0) >= min_size)
        and (max_size is None or (file["sizeBytes"] or 0) <= max_size)
        and matches_date(file["lastModified"])
    ]

    return {
        "folders": [
            {
                "publicID": folder["publicID"],
                "public": folder["public"],
                "publicExpiresAt": folder.get("publicExpiresAt"),
                "folderName": folder["folderName"],
                "lastModified": folder["lastModified"],
                "path": build_folder_path(folder["folderID"], folders_by_id)
            }
            for folder in filtered_folders
        ],
        "files": [
            {
                "publicID": file["publicID"],
                "public": file["public"],
                "publicExpiresAt": file.get("publicExpiresAt"),
                "publicAllowDownload": file.get("publicAllowDownload", True),
                "fileName": file["fileName"],
                "sizeBytes": file["sizeBytes"],
                "previewPath": file["previewPath"],
                "lastModified": file["lastModified"],
                "path": build_folder_path(file["folderID"], folders_by_id)
            }
            for file in filtered_files
        ]
    }
