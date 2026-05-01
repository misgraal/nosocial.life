import csv
import hashlib
import mimetypes
import shutil
import subprocess
import time
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from app.db.admin import get_user_by_id, get_user_storage_usage, get_upload_disk_settings
from app.db.app import create_audit_log
from app.db.files import (
    create_file_db,
    delete_file_db,
    get_file_by_public_id,
    get_file_shared_users,
    get_folders_child_files_for_delete,
    get_shared_files_for_user,
    get_user_file_by_name_in_folder,
    get_user_file_by_public_id,
    is_file_shared_with_user,
    replace_file_shared_users,
    update_file_public_db,
    update_file_share_settings_db,
)
from app.db.folders import (
    create_folder_db,
    delete_folder_db,
    get_folder_by_id,
    get_folder_id_by_public_id,
    get_folders_child_folder_ids,
    get_user_folder_by_name_in_parent,
    get_user_folder_by_public_id,
    get_users_root_folder,
    update_folder_public_db,
)
from app.services.app import DeleteItemsPayload, UploadChunkPayload
from app.services.app import normalize_share_expires_at, parse_python_datetime, resolve_share_recipient_users
from app.services.folders import can_user_access_shared_folder
from app.security.passwords import hash_password
from config import DISKS, MEDIA_FOLDER_NAME, RUNTIME_DIR, tmpFolder


upload_list = []
cancelled_upload_ids = set()
last_upload_cleanup_at = 0
STALE_UPLOAD_MAX_AGE_SECONDS = 60 * 60 * 24
CLEANUP_INTERVAL_SECONDS = 60 * 30


def get_existing_path(path: Path) -> Path:
    probe_path = path

    while not probe_path.exists() and probe_path != probe_path.parent:
        probe_path = probe_path.parent

    return probe_path


def get_disk_free_space(disk_path: str) -> int:
    probe_path = get_existing_path(Path(disk_path))

    try:
        return shutil.disk_usage(probe_path).free
    except OSError:
        return -1


def get_disk_device_id(disk_path: str) -> int | None:
    probe_path = get_existing_path(Path(disk_path))

    try:
        return probe_path.stat().st_dev
    except OSError:
        return None


def get_directory_used_space(disk_path: str) -> int:
    root_path = Path(disk_path)
    if not root_path.exists():
        return 0

    total_size = 0
    for file_path in root_path.rglob("*"):
        if not file_path.is_file():
            continue

        try:
            total_size += file_path.stat().st_size
        except OSError:
            continue

    return total_size


async def get_enabled_upload_disks() -> list[str]:
    disk_settings = await get_upload_disk_settings()
    enabled_disks = [disk["diskPath"] for disk in disk_settings if disk["isEnabled"]]

    if enabled_disks:
        return enabled_disks

    return DISKS


async def select_upload_disk(file_size: int) -> str:
    available_disks = await get_enabled_upload_disks()
    if not available_disks:
        raise ValueError("Upload disks are not configured")

    candidates = []
    for disk_path in available_disks:
        free_space = get_disk_free_space(disk_path)
        if free_space < file_size:
            continue

        candidates.append({
            "path": disk_path,
            "freeSpace": free_space,
            "usedSpace": get_directory_used_space(disk_path),
            "deviceId": get_disk_device_id(disk_path)
        })

    if not candidates:
        raise ValueError("No upload disk has enough free space")

    unique_device_ids = {candidate["deviceId"] for candidate in candidates}
    if len(unique_device_ids) == 1:
        candidates.sort(key=lambda candidate: (candidate["usedSpace"], candidate["path"]))
        return candidates[0]["path"]

    candidates.sort(
        key=lambda candidate: (-candidate["freeSpace"], candidate["usedSpace"], candidate["path"])
    )
    return candidates[0]["path"]


def get_existing_upload(upload_id: str):
    for upload in upload_list:
        if upload["uploadId"] == upload_id:
            return upload

    return None


async def get_or_create_upload(upload_id: str, file_size: int):
    upload = get_existing_upload(upload_id)
    if upload:
        return upload

    upload = {
        "uploadId": upload_id,
        "uploadDisk": await select_upload_disk(file_size)
    }
    upload_list.append(upload)
    return upload


def build_upload_paths(upload: dict):
    upload_disk = Path(upload["uploadDisk"])
    temp_root_name = Path(tmpFolder).name
    upload_root = upload_disk / temp_root_name
    temp_dir = upload_root / "chunks" / upload["uploadId"]
    final_dir = upload_disk
    temp_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir, final_dir


def validate_chunk_payload(payload: UploadChunkPayload):
    validate_upload_id(payload.upload_id)
    if payload.chunk_index < 0 or payload.total_chunks < 1 or payload.chunk_index >= payload.total_chunks:
        raise ValueError("Invalid chunk metadata")
    if payload.chunk_start is not None:
        if payload.chunk_start < 0 or payload.chunk_start + payload.chunk_size > payload.file_size:
            raise ValueError("Invalid chunk offset")
        if payload.is_last_chunk and payload.chunk_start + payload.chunk_size != payload.file_size:
            raise ValueError("Invalid final chunk size")


def validate_upload_id(upload_id: str):
    if not upload_id or Path(upload_id).name != upload_id or upload_id in {".", ".."}:
        raise ValueError("Invalid upload id")


def is_platform_compatible_disk_path(disk_path: str) -> bool:
    try:
        Path(disk_path)
        return True
    except (TypeError, ValueError):
        return False


def get_streamed_upload_path(temp_dir: Path) -> Path:
    return temp_dir / "upload.data"


def get_chunk_marker_path(temp_dir: Path, chunk_index: int) -> Path:
    return temp_dir / f"{chunk_index:08d}.done"


def save_chunk(temp_dir: Path, payload: UploadChunkPayload, chunk_bytes: bytes):
    if len(chunk_bytes) != payload.chunk_size:
        raise ValueError("Chunk size mismatch")

    if payload.chunk_start is not None:
        upload_path = get_streamed_upload_path(temp_dir)
        mode = "r+b" if upload_path.exists() else "w+b"
        with open(upload_path, mode) as file:
            file.seek(payload.chunk_start)
            file.write(chunk_bytes)
        get_chunk_marker_path(temp_dir, payload.chunk_index).touch()
        return

    chunk_path = temp_dir / f"{payload.chunk_index:08d}.part"
    with open(chunk_path, "wb") as file:
        file.write(chunk_bytes)


def assert_no_missing_chunks(temp_dir: Path, total_chunks: int, marker_suffix: str = ".part"):
    missing_chunks = [
        index for index in range(total_chunks)
        if not (temp_dir / f"{index:08d}{marker_suffix}").exists()
    ]
    if missing_chunks:
        raise ValueError(f"Missing chunks: {missing_chunks}")


def build_final_path(final_dir: Path, upload_id: str, file_name: str) -> Path:
    safe_file_name = Path(file_name).name
    final_path = final_dir / safe_file_name
    if final_path.exists():
        final_path = final_dir / f"{upload_id}_{safe_file_name}"

    return final_path


async def get_folder_path_parts(folder_id: int | None) -> list[str]:
    if folder_id is None:
        return []

    parts = []
    current_folder = await get_folder_by_id(folder_id)
    while current_folder:
        parts.append(current_folder["folderName"])
        parent_folder_id = current_folder["parentFolderID"]
        if parent_folder_id is None:
            break
        current_folder = await get_folder_by_id(parent_folder_id)

    return list(reversed(parts))


def is_media_folder_name(folder_name: str) -> bool:
    return str(folder_name or "").casefold() == MEDIA_FOLDER_NAME.casefold()


async def is_media_folder_tree(folder_id: int | None) -> bool:
    folder_parts = await get_folder_path_parts(folder_id)
    return len(folder_parts) >= 2 and is_media_folder_name(folder_parts[1])


async def get_folder_physical_upload_dir(upload: dict, folder_id: int | None) -> Path:
    upload_disk = Path(upload["uploadDisk"])
    folder_parts = await get_folder_path_parts(folder_id)

    if len(folder_parts) >= 2 and is_media_folder_name(folder_parts[1]):
        final_dir = upload_disk.joinpath(MEDIA_FOLDER_NAME, *folder_parts[2:])
    else:
        final_dir = upload_disk

    final_dir.mkdir(parents=True, exist_ok=True)
    return final_dir


async def is_public_upload_folder(folder_id: int | None) -> bool:
    if folder_id is None:
        return False

    folder = await get_folder_by_id(folder_id)
    return bool(folder and folder.get("public"))


async def should_folder_be_public_after_upload(parent_folder_id: int | None, folder_name: str) -> bool:
    parent_parts = await get_folder_path_parts(parent_folder_id)
    is_root_child = len(parent_parts) == 1
    return (
        await is_public_upload_folder(parent_folder_id)
        or await is_media_folder_tree(parent_folder_id)
        or (is_root_child and is_media_folder_name(folder_name))
    )


def assemble_file(temp_dir: Path, final_path: Path, total_chunks: int) -> int:
    bytes_written = 0
    with open(final_path, "wb") as final_file:
        for index in range(total_chunks):
            part_path = temp_dir / f"{index:08d}.part"
            with open(part_path, "rb") as part_file:
                data = part_file.read()
                final_file.write(data)
                bytes_written += len(data)

    return bytes_written


def cleanup_temp_chunks(temp_dir: Path):
    shutil.rmtree(temp_dir, ignore_errors=True)


def remove_upload_from_memory(upload: dict):
    if upload in upload_list:
        upload_list.remove(upload)


async def cancel_upload(upload_id: str) -> dict:
    validate_upload_id(upload_id)
    cancelled_upload_ids.add(upload_id)

    matching_uploads = [
        upload for upload in upload_list
        if upload["uploadId"] == upload_id
    ]
    for upload in matching_uploads:
        remove_upload_from_memory(upload)

    candidate_disks = {
        disk_path
        for disk_path in [*DISKS, *(await get_enabled_upload_disks())]
        if is_platform_compatible_disk_path(disk_path)
    }
    candidate_disks.update(upload["uploadDisk"] for upload in matching_uploads)

    temp_root_name = Path(tmpFolder).name
    for disk_path in candidate_disks:
        temp_dir = Path(disk_path) / temp_root_name / "chunks" / upload_id
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

    return {"status": "cancelled", "uploadId": upload_id}


async def get_upload_status(upload_id: str) -> dict:
    validate_upload_id(upload_id)
    temp_root_name = Path(tmpFolder).name
    candidate_disks = {
        disk_path
        for disk_path in [*DISKS, *(await get_enabled_upload_disks())]
        if is_platform_compatible_disk_path(disk_path)
    }

    matching_upload = get_existing_upload(upload_id)
    if matching_upload:
        candidate_disks.add(matching_upload["uploadDisk"])

    completed_chunks = set()
    uploaded_bytes = 0
    exists = False

    for disk_path in candidate_disks:
        temp_dir = Path(disk_path) / temp_root_name / "chunks" / upload_id
        if not temp_dir.exists():
            continue

        exists = True
        for marker_path in temp_dir.glob("*.done"):
            try:
                completed_chunks.add(int(marker_path.stem))
            except ValueError:
                continue

        streamed_upload_path = get_streamed_upload_path(temp_dir)
        if streamed_upload_path.exists():
            try:
                uploaded_bytes = max(uploaded_bytes, streamed_upload_path.stat().st_size)
            except OSError:
                pass

    return {
        "uploadId": upload_id,
        "exists": exists,
        "completedChunks": sorted(completed_chunks),
        "uploadedBytes": uploaded_bytes,
    }


async def cleanup_stale_upload_chunks():
    global last_upload_cleanup_at

    now = time.time()
    if now - last_upload_cleanup_at < CLEANUP_INTERVAL_SECONDS:
        return

    temp_root_name = Path(tmpFolder).name
    candidate_disks = await get_enabled_upload_disks()

    for disk_path in candidate_disks:
        chunks_root = Path(disk_path) / temp_root_name / "chunks"
        if not chunks_root.exists():
            continue

        for upload_dir in chunks_root.iterdir():
            if not upload_dir.is_dir():
                continue

            try:
                modified_at = upload_dir.stat().st_mtime
            except OSError:
                continue

            if now - modified_at < STALE_UPLOAD_MAX_AGE_SECONDS:
                continue

            shutil.rmtree(upload_dir, ignore_errors=True)

    last_upload_cleanup_at = now


def get_share_access_cookie_name(file_public_id: str) -> str:
    return f"share_file_{file_public_id}"


def is_share_expired(item: dict) -> bool:
    expires_at = parse_python_datetime(item.get("publicExpiresAt"))
    if not expires_at:
        return False
    return datetime.now() > expires_at


def is_share_password_required(item: dict) -> bool:
    return bool(item.get("publicPasswordHash"))


def is_public_file_accessible(item: dict) -> bool:
    return bool(item and item.get("public")) and not is_share_expired(item)


async def set_file_visibility(user_id: int, file_public_id: str, is_public: bool) -> dict:
    file = await get_user_file_by_public_id(user_id, file_public_id)
    if not file:
        raise ValueError("File was not found")

    updated_file = await update_file_public_db(user_id, file["fileID"], is_public)
    await create_audit_log(
        user_id,
        "file.visibility.updated",
        "file",
        updated_file["publicID"],
        {"public": bool(updated_file["public"])}
    )
    return {
        "file": updated_file,
        "publicUrl": f"/app/files/{updated_file['publicID']}"
    }


async def update_file_share_settings(
    user_id: int,
    file_public_id: str,
    is_public: bool,
    expires_at: str | None,
    password: str | None,
    clear_password: bool,
    allow_download: bool,
    shared_users: list[str] | None = None
) -> dict:
    file = await get_user_file_by_public_id(user_id, file_public_id)
    if not file:
        raise ValueError("File was not found")

    recipient_users = await resolve_share_recipient_users(user_id, shared_users)
    expires_at_value = normalize_share_expires_at(expires_at)
    password_hash = file.get("publicPasswordHash")
    if clear_password:
        password_hash = None
    elif password and password.strip():
        password_hash = hash_password(password.strip())

    updated_file = await update_file_share_settings_db(
        user_id,
        file["fileID"],
        is_public,
        expires_at_value,
        password_hash,
        allow_download
    )
    await replace_file_shared_users(
        file["fileID"],
        [recipient_user["userID"] for recipient_user in recipient_users]
    )
    await create_audit_log(
        user_id,
        "file.share.updated",
        "file",
        updated_file["publicID"],
        {
            "public": bool(updated_file["public"]),
            "expiresAt": expires_at_value.isoformat() if expires_at_value else None,
            "passwordProtected": bool(updated_file.get("publicPasswordHash")),
            "allowDownload": bool(updated_file.get("publicAllowDownload", True)),
            "sharedUsers": [recipient_user["username"] for recipient_user in recipient_users]
        }
    )
    return {
        "file": updated_file,
        "publicUrl": f"/app/files/{updated_file['publicID']}",
        "sharedUsers": [recipient_user["username"] for recipient_user in recipient_users]
    }


async def get_accessible_file(user_id: int | None, file_public_id: str):
    file = None

    if user_id:
        file = await get_user_file_by_public_id(user_id, file_public_id)
        if file:
            return file

        file = await get_file_by_public_id(file_public_id)
        if file:
            if await is_file_shared_with_user(file["fileID"], user_id):
                return file

            folder = await get_folder_by_id(file["folderID"])
            if await can_user_access_shared_folder(user_id, folder):
                return file

    file = await get_file_by_public_id(file_public_id)
    if not file or not is_public_file_accessible(file):
        return None

    return file


async def get_file_shared_usernames(file_id: int) -> list[str]:
    shared_users = await get_file_shared_users(file_id)
    return [user["username"] for user in shared_users]


async def get_file_share_settings(user_id: int, file_public_id: str) -> dict:
    file = await get_user_file_by_public_id(user_id, file_public_id)
    if not file:
        raise ValueError("File was not found")

    return {
        "file": file,
        "sharedUsers": await get_file_shared_usernames(file["fileID"])
    }


async def resolve_upload_folder_id(user_id: int, folder_public_id: str | None) -> int:
    if folder_public_id:
        folder = await get_folder_id_by_public_id(folder_public_id)
        return folder["folderID"]

    root_folder = await get_users_root_folder(user_id)
    return root_folder[0]["folderID"]


def get_relative_folder_parts(relative_path: str | None) -> list[str]:
    if not relative_path:
        return []

    normalized_path = str(relative_path).replace("\\", "/").strip("/")
    if not normalized_path:
        return []

    parts = [part.strip() for part in normalized_path.split("/") if part.strip() and part not in {".", ".."}]
    if len(parts) <= 1:
        return []

    return parts[:-1]


async def ensure_nested_upload_folders(user_id: int, base_folder_id: int, relative_path: str | None) -> int:
    current_folder_id = base_folder_id

    for folder_name in get_relative_folder_parts(relative_path):
        existing_folder = await get_user_folder_by_name_in_parent(user_id, current_folder_id, folder_name)
        if existing_folder:
            if await should_folder_be_public_after_upload(current_folder_id, folder_name):
                await update_folder_public_db(user_id, existing_folder["folderID"], True)
            current_folder_id = existing_folder["folderID"]
            continue

        created_folder = await create_folder_db(folder_name, user_id, current_folder_id)
        folder_row = await get_folder_id_by_public_id(created_folder["publicID"])
        if await should_folder_be_public_after_upload(current_folder_id, folder_name):
            await update_folder_public_db(user_id, folder_row["folderID"], True)
        current_folder_id = folder_row["folderID"]

    return current_folder_id


async def handle_chunk_upload(user_id: int, payload: UploadChunkPayload, chunk_bytes: bytes) -> dict:
    await cleanup_stale_upload_chunks()
    validate_chunk_payload(payload)

    upload = await get_or_create_upload(payload.upload_id, payload.file_size)
    temp_dir, final_dir = build_upload_paths(upload)
    safe_file_name = Path(payload.file_name).name

    if payload.upload_id in cancelled_upload_ids:
        cleanup_temp_chunks(temp_dir)
        remove_upload_from_memory(upload)
        raise ValueError("Upload was cancelled")

    save_chunk(temp_dir, payload, chunk_bytes)
    if payload.upload_id in cancelled_upload_ids:
        cleanup_temp_chunks(temp_dir)
        remove_upload_from_memory(upload)
        raise ValueError("Upload was cancelled")

    if not payload.is_last_chunk:
        return {
            "status": "chunk_saved",
            "uploadId": payload.upload_id,
            "chunkIndex": payload.chunk_index,
            "totalChunks": payload.total_chunks
        }

    if payload.chunk_start is None:
        assert_no_missing_chunks(temp_dir, payload.total_chunks)
        bytes_written = payload.file_size
    else:
        assert_no_missing_chunks(temp_dir, payload.total_chunks, marker_suffix=".done")
        streamed_upload_path = get_streamed_upload_path(temp_dir)
        if not streamed_upload_path.exists():
            raise ValueError("Upload data is missing")
        bytes_written = streamed_upload_path.stat().st_size

    if bytes_written != payload.file_size:
        raise ValueError("Final file size mismatch")

    root_folder_id = await resolve_upload_folder_id(user_id, payload.folder_public_id)
    folder_id = await ensure_nested_upload_folders(user_id, root_folder_id, payload.relative_path)
    final_dir = await get_folder_physical_upload_dir(upload, folder_id)
    user = await get_user_by_id(user_id)
    current_usage = await get_user_storage_usage(user_id)
    storage_quota_bytes = user["storageQuotaBytes"] if user else None
    if storage_quota_bytes is not None and current_usage + bytes_written > storage_quota_bytes:
        cleanup_temp_chunks(temp_dir)
        remove_upload_from_memory(upload)
        raise ValueError("Storage quota exceeded")

    final_path = build_final_path(final_dir, payload.upload_id, payload.file_name)
    if payload.chunk_start is None:
        bytes_written = assemble_file(temp_dir, final_path, payload.total_chunks)
    else:
        get_streamed_upload_path(temp_dir).replace(final_path)

    file = await create_file_db(
        safe_file_name,
        user_id,
        folder_id,
        str(final_path),
        bytes_written,
        str(final_path)
    )
    if await is_public_upload_folder(folder_id) or await is_media_folder_tree(folder_id):
        created_file = await get_user_file_by_public_id(user_id, file["publicID"])
        file = await update_file_public_db(user_id, created_file["fileID"], True)

    await create_audit_log(
        user_id,
        "file.upload.completed",
        "file",
        file["publicID"],
        {
            "fileName": safe_file_name,
            "fileSize": bytes_written,
            "folderPublicId": payload.folder_public_id,
            "relativePath": payload.relative_path,
            "savedTo": str(final_path)
        }
    )

    cleanup_temp_chunks(temp_dir)
    remove_upload_from_memory(upload)
    cancelled_upload_ids.discard(payload.upload_id)

    return {
        "status": "completed",
        "uploadId": payload.upload_id,
        "fileName": safe_file_name,
        "mimeType": payload.mime_type,
        "fileSize": bytes_written,
        "folderPublicId": payload.folder_public_id,
        "currentUrl": payload.current_url,
        "savedTo": str(final_path),
        "file": file
    }


def delete_physical_file(server_path: str):
    if not server_path:
        return

    file_path = Path(server_path)
    if file_path.exists() and file_path.is_file():
        file_path.unlink()


async def collect_folder_delete_data(folder_id: int) -> tuple[list[int], list[dict]]:
    child_folder_rows = await get_folders_child_folder_ids(folder_id)
    folder_ids = [folder_id]
    files_to_delete = await get_folders_child_files_for_delete(folder_id)

    for child_folder_row in child_folder_rows:
        child_folder_ids, child_files = await collect_folder_delete_data(child_folder_row["folderID"])
        folder_ids.extend(child_folder_ids)
        files_to_delete.extend(child_files)

    return folder_ids, files_to_delete


async def delete_items(user_id: int, payload: DeleteItemsPayload) -> dict:
    deleted_file_public_ids = []
    deleted_folder_public_ids = []
    processed_file_public_ids = set()

    for file_public_id in payload.file_public_ids:
        file = await get_user_file_by_public_id(user_id, file_public_id)
        if not file:
            continue

        delete_physical_file(file["serverPath"])
        await delete_file_db(user_id, file["fileID"])
        await create_audit_log(
            user_id,
            "file.deleted",
            "file",
            file_public_id,
            {"serverPath": file["serverPath"]}
        )
        deleted_file_public_ids.append(file_public_id)
        processed_file_public_ids.add(file_public_id)

    for folder_public_id in payload.folder_public_ids:
        folder = await get_user_folder_by_public_id(user_id, folder_public_id)
        if not folder:
            continue

        folder_ids, files_to_delete = await collect_folder_delete_data(folder["folderID"])
        for file in files_to_delete:
            if file["publicID"] in processed_file_public_ids:
                continue

            delete_physical_file(file["serverPath"])
            await delete_file_db(user_id, file["fileID"])
            await create_audit_log(
                user_id,
                "file.deleted",
                "file",
                file["publicID"],
                {"serverPath": file["serverPath"], "viaFolderDelete": True}
            )
            deleted_file_public_ids.append(file["publicID"])
            processed_file_public_ids.add(file["publicID"])

        for nested_folder_id in reversed(folder_ids):
            await delete_folder_db(user_id, nested_folder_id)

        await create_audit_log(
            user_id,
            "folder.deleted",
            "folder",
            folder_public_id,
            {"nestedFolderCount": len(folder_ids), "deletedFileCount": len(files_to_delete)}
        )
        deleted_folder_public_ids.append(folder_public_id)

    return {
        "deletedFilePublicIds": deleted_file_public_ids,
        "deletedFolderPublicIds": deleted_folder_public_ids
    }


IMAGE_FILE_EXTENSIONS = {
    ".3fr", ".ari", ".arw", ".avif", ".bay", ".bmp", ".cap", ".cr2", ".cr3",
    ".crw", ".dcr", ".dng", ".erf", ".fff", ".gif", ".heic", ".heif", ".ico",
    ".iiq", ".j2c", ".j2k", ".jfif", ".jp2", ".jpe", ".jpeg", ".jpg", ".jxl",
    ".k25", ".kdc", ".mef", ".mos", ".mrw", ".nef", ".nrw", ".orf", ".pef",
    ".png", ".ppm", ".psd", ".raf", ".raw", ".rw2", ".rwl", ".sr2", ".srf",
    ".srw", ".svg", ".tga", ".tif", ".tiff", ".webp", ".x3f"
}
VIDEO_FILE_EXTENSIONS = {
    ".3g2", ".3gp", ".asf", ".avi", ".divx", ".dv", ".f4v", ".flv", ".m2t",
    ".m2ts", ".m4v", ".mkv", ".mod", ".mov", ".mp4", ".mpeg", ".mpg", ".mts",
    ".mxf", ".ogm", ".ogv", ".rm", ".rmvb", ".ts", ".vob", ".webm", ".wmv"
}
MEDIA_TYPE_OVERRIDES = {
    ".3g2": "video/3gpp2",
    ".3gp": "video/3gpp",
    ".avi": "video/x-msvideo",
    ".avif": "image/avif",
    ".flv": "video/x-flv",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".jxl": "image/jxl",
    ".m2t": "video/mp2t",
    ".m2ts": "video/mp2t",
    ".m4v": "video/mp4",
    ".mkv": "video/x-matroska",
    ".mov": "video/quicktime",
    ".mts": "video/mp2t",
    ".ogm": "video/ogg",
    ".ogv": "video/ogg",
    ".rm": "application/vnd.rn-realmedia",
    ".rmvb": "application/vnd.rn-realmedia-vbr",
    ".svg": "image/svg+xml",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".ts": "video/mp2t",
    ".vob": "video/dvd",
    ".webm": "video/webm",
    ".wmv": "video/x-ms-wmv",
}
BROWSER_NATIVE_IMAGE_MEDIA_TYPES = {
    "image/avif",
    "image/bmp",
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/svg+xml",
    "image/vnd.microsoft.icon",
    "image/webp",
    "image/x-icon",
}
TEXT_FILE_EXTENSIONS = {
    ".txt", ".md", ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".scss",
    ".json", ".xml", ".yml", ".yaml", ".log", ".ini", ".cfg", ".toml", ".sh",
    ".bat", ".env", ".sql", ".rtf"
}
EXCEL_FILE_EXTENSIONS = {
    ".xlsx", ".csv", ".tsv"
}


def get_file_extension(file_name: str) -> str:
    return Path(file_name or "").suffix.lower()


def get_file_media_type(file_name: str) -> str:
    extension = get_file_extension(file_name)
    if extension in MEDIA_TYPE_OVERRIDES:
        return MEDIA_TYPE_OVERRIDES[extension]

    media_type, _ = mimetypes.guess_type(file_name)
    return media_type or "application/octet-stream"


def get_file_view_kind(file_name: str) -> str:
    extension = get_file_extension(file_name)
    media_type = get_file_media_type(file_name)

    if extension == ".pdf":
        return "pdf"
    if extension in EXCEL_FILE_EXTENSIONS:
        return "excel"
    if extension in IMAGE_FILE_EXTENSIONS or media_type.startswith("image/"):
        return "image"
    if extension in VIDEO_FILE_EXTENSIONS or media_type.startswith("video/"):
        return "video"
    if extension in TEXT_FILE_EXTENSIONS or media_type.startswith("text/"):
        return "text"
    return "unsupported"


def get_file_view_type_label(file_name: str) -> str:
    view_kind = get_file_view_kind(file_name)
    extension = get_file_extension(file_name)

    if view_kind == "pdf":
        return "PDF document"
    if view_kind == "image":
        return "Image"
    if view_kind == "video":
        return "Video"
    if view_kind == "text":
        return "Text document"
    if view_kind == "excel":
        return "Spreadsheet"
    if extension:
        return f"{extension[1:].upper()} file"
    return "File"


def can_generate_media_thumbnail(file_name: str) -> bool:
    return get_file_view_kind(file_name) in {"image", "video"}


def is_browser_native_image(file_name: str) -> bool:
    return get_file_media_type(file_name).lower() in BROWSER_NATIVE_IMAGE_MEDIA_TYPES


def get_media_thumbnail_cache_path(file_path: Path, file_name: str) -> Path:
    stat = file_path.stat()
    cache_key = "|".join([
        str(file_path),
        file_name or file_path.name,
        str(stat.st_size),
        str(int(stat.st_mtime))
    ])
    digest = hashlib.sha256(cache_key.encode("utf-8", "ignore")).hexdigest()
    return RUNTIME_DIR / "previews" / f"{digest}.jpg"


def generate_media_thumbnail(file_path: Path, file_name: str) -> Path:
    if not can_generate_media_thumbnail(file_name):
        raise ValueError("Preview image is not available for this file type")

    cache_path = get_media_thumbnail_cache_path(file_path, file_name)
    if cache_path.exists() and cache_path.stat().st_size > 0:
        return cache_path

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = cache_path.with_suffix(".tmp.jpg")
    view_kind = get_file_view_kind(file_name)
    seek_options = [["-ss", "00:00:02"], []] if view_kind == "video" else [[]]
    last_error = "Preview generation failed"

    for seek_option in seek_options:
        temp_path.unlink(missing_ok=True)
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *seek_option]
        command.extend([
            "-i", str(file_path),
            "-frames:v", "1",
            "-vf", "scale=w='min(1280,iw)':h='min(1280,ih)':force_original_aspect_ratio=decrease,format=yuvj420p",
            "-q:v", "3",
            str(temp_path)
        ])

        try:
            subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30)
        except FileNotFoundError as error:
            raise ValueError("ffmpeg is not installed") from error
        except subprocess.TimeoutExpired as error:
            temp_path.unlink(missing_ok=True)
            raise ValueError("Preview generation timed out") from error
        except subprocess.CalledProcessError as error:
            detail = error.stderr.decode("utf-8", "ignore").strip()
            last_error = detail or "Preview generation failed"
            continue

        if temp_path.exists() and temp_path.stat().st_size > 0:
            break
    else:
        temp_path.unlink(missing_ok=True)
        raise ValueError(last_error)

    temp_path.replace(cache_path)
    return cache_path


def read_text_file_preview(file_path: Path, max_chars: int = 500000) -> dict:
    encodings = ("utf-8", "utf-8-sig", "cp1251", "latin-1")

    for encoding in encodings:
        try:
            with file_path.open("r", encoding=encoding) as file_handle:
                content = file_handle.read(max_chars + 1)
            truncated = len(content) > max_chars
            if truncated:
                content = content[:max_chars]
            return {
                "content": content,
                "truncated": truncated,
                "encoding": encoding
            }
        except UnicodeDecodeError:
            continue

    raise ValueError("File could not be decoded as text")


def get_delimited_file_preview(file_path: Path, delimiter: str, max_rows: int = 100, max_cols: int = 20) -> dict:
    text_preview = read_text_file_preview(file_path)
    rows = []
    truncated = text_preview["truncated"]

    reader = csv.reader(text_preview["content"].splitlines(), delimiter=delimiter)
    for index, row in enumerate(reader):
        if index >= max_rows:
            truncated = True
            break
        if len(row) > max_cols:
            truncated = True
        rows.append(row[:max_cols])

    column_count = max((len(row) for row in rows), default=0)
    normalized_rows = []
    for row in rows:
        normalized_rows.append(row + [""] * max(0, column_count - len(row)))

    return {
        "supported": True,
        "rows": normalized_rows,
        "columnCount": column_count,
        "truncated": truncated,
        "sheetName": file_path.name
    }


def get_xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []

    namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    shared_strings_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    strings = []

    for item in shared_strings_root.findall("main:si", namespace):
        text_nodes = item.findall(".//main:t", namespace)
        strings.append("".join(node.text or "" for node in text_nodes))

    return strings


def get_excel_column_index(cell_reference: str) -> int:
    letters = "".join(character for character in cell_reference if character.isalpha()).upper()
    if not letters:
        return 0

    index = 0
    for character in letters:
        index = index * 26 + (ord(character) - 64)

    return index - 1


def get_xlsx_first_sheet_path(archive: zipfile.ZipFile) -> tuple[str | None, str | None]:
    spreadsheet_namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    relationships_namespace = {"rel": "http://schemas.openxmlformats.org/package/2006/relationships"}
    office_relationship = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"

    workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
    first_sheet = workbook_root.find("main:sheets/main:sheet", spreadsheet_namespace)
    if first_sheet is None:
        return None, None

    relationship_id = first_sheet.attrib.get(office_relationship)
    sheet_name = first_sheet.attrib.get("name")
    if not relationship_id:
        return None, sheet_name

    workbook_relationships_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    for relationship in workbook_relationships_root.findall("rel:Relationship", relationships_namespace):
        if relationship.attrib.get("Id") == relationship_id:
            target = relationship.attrib.get("Target", "")
            if target.startswith("/"):
                return target.lstrip("/"), sheet_name
            return f"xl/{target.lstrip('/')}", sheet_name

    return None, sheet_name


def get_xlsx_cell_value(cell: ET.Element, namespace: dict[str, str], shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    value_node = cell.find("main:v", namespace)

    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//main:t", namespace))

    if value_node is None:
        return ""

    raw_value = value_node.text or ""
    if cell_type == "s":
        shared_index = int(raw_value) if raw_value.isdigit() else 0
        if 0 <= shared_index < len(shared_strings):
            return shared_strings[shared_index]
        return ""
    if cell_type == "b":
        return "TRUE" if raw_value == "1" else "FALSE"

    return raw_value


def get_xlsx_file_preview(file_path: Path, max_rows: int = 100, max_cols: int = 20) -> dict:
    namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

    with zipfile.ZipFile(file_path) as archive:
        shared_strings = get_xlsx_shared_strings(archive)
        sheet_path, sheet_name = get_xlsx_first_sheet_path(archive)
        if not sheet_path or sheet_path not in archive.namelist():
            return {
                "supported": False,
                "reason": "Spreadsheet preview is not available for this file."
            }

        sheet_root = ET.fromstring(archive.read(sheet_path))
        rows = []
        max_seen_columns = 0
        truncated = False

        for row_index, row in enumerate(sheet_root.findall(".//main:sheetData/main:row", namespace)):
            if row_index >= max_rows:
                truncated = True
                break

            row_values = {}
            for cell in row.findall("main:c", namespace):
                column_index = get_excel_column_index(cell.attrib.get("r", "A1"))
                if column_index >= max_cols:
                    truncated = True
                    continue
                row_values[column_index] = get_xlsx_cell_value(cell, namespace, shared_strings)
                max_seen_columns = max(max_seen_columns, column_index + 1)

            rows.append(row_values)

    column_count = max_seen_columns or 1
    normalized_rows = []
    for row in rows:
        normalized_rows.append([
            row.get(column_index, "")
            for column_index in range(column_count)
        ])

    return {
        "supported": True,
        "rows": normalized_rows,
        "columnCount": column_count,
        "truncated": truncated,
        "sheetName": sheet_name or file_path.stem
    }


def get_excel_file_preview(file_path: Path, max_rows: int = 100, max_cols: int = 20) -> dict:
    extension = file_path.suffix.lower()

    if extension == ".csv":
        return get_delimited_file_preview(file_path, ",", max_rows=max_rows, max_cols=max_cols)
    if extension == ".tsv":
        return get_delimited_file_preview(file_path, "\t", max_rows=max_rows, max_cols=max_cols)
    if extension == ".xlsx":
        return get_xlsx_file_preview(file_path, max_rows=max_rows, max_cols=max_cols)

    return {
        "supported": False,
        "reason": "Spreadsheet preview is available for .xlsx, .csv and .tsv files."
    }
