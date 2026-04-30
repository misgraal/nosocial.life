from dataclasses import dataclass
from pathlib import Path
import shutil

from app.db.admin import (
    clear_audit_log_user_references,
    count_admin_users,
    count_users,
    delete_user,
    delete_user_files,
    get_public_file_shares,
    get_public_folder_shares,
    get_user_by_id,
    get_user_files_for_admin,
    get_user_folders_for_admin,
    get_user_file_paths,
    get_user_role,
    get_user_storage_usage,
    get_users_with_stats,
    get_upload_disk_settings,
    revoke_file_share_admin,
    revoke_folder_share_admin,
    set_upload_disk_enabled,
    update_user_blocked,
    update_user_role,
    update_user_storage_quota,
)
from app.db.app import create_audit_log, get_audit_logs
from app.db.folders import delete_folder_db, get_all_user_folders
from app.security.sesions import delete_user_sessions
from app.services.app import build_folder_path
from config import DISKS


@dataclass
class AdminDashboardResult:
    current_user: dict
    stats: dict
    users: list
    disks: list
    audit_logs: list
    share_items: list
    inspected_user: dict | None
    inspected_items: dict | None


def format_bytes(size_bytes: int) -> str:
    if not size_bytes or size_bytes <= 0:
        return "0 B"

    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    unit_index = 0

    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    if unit_index == 0 or size >= 10:
        return f"{round(size)} {units[unit_index]}"
    return f"{size:.1f} {units[unit_index]}"


def get_existing_path(path: Path) -> Path:
    probe_path = path

    while not probe_path.exists() and probe_path != probe_path.parent:
        probe_path = probe_path.parent

    return probe_path


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


async def get_disk_stats_async() -> list[dict]:
    stats = []
    disk_settings = {
        disk["diskPath"]: bool(disk["isEnabled"])
        for disk in await get_upload_disk_settings()
    }

    for disk_path in DISKS:
        probe_path = get_existing_path(Path(disk_path))
        usage = shutil.disk_usage(probe_path)
        app_used_space = get_directory_used_space(disk_path)
        used_percent = round((usage.used / usage.total) * 100) if usage.total else 0
        app_used_percent = round((app_used_space / usage.total) * 100) if usage.total else 0

        stats.append({
            "name": Path(disk_path).name or disk_path,
            "path": disk_path,
            "percent": used_percent,
            "used": format_bytes(usage.used),
            "free": format_bytes(usage.free),
            "total": format_bytes(usage.total),
            "appUsed": format_bytes(app_used_space),
            "appPercent": app_used_percent,
            "isEnabled": disk_settings.get(disk_path, True),
        })

    return stats


async def assert_admin(user_id: int):
    role = await get_user_role(user_id)
    if role != "admin":
        raise ValueError("User is not an admin")


async def get_inspected_user_items(admin_user_id: int, target_user_id: int) -> tuple[dict | None, dict | None]:
    await assert_admin(admin_user_id)

    target_user = await get_user_by_id(target_user_id)
    if not target_user:
        return None, None

    folders = await get_user_folders_for_admin(target_user_id)
    files = await get_user_files_for_admin(target_user_id)
    folders_by_id = {folder["folderID"]: folder for folder in folders}
    root_folder = next((folder for folder in folders if folder["parentFolderID"] is None), None)

    folder_items = [
        {
            "publicID": folder["publicID"],
            "folderName": folder["folderName"],
            "public": bool(folder["public"]),
            "publicExpiresAt": folder["publicExpiresAt"],
            "lastModified": folder["lastModified"],
            "path": build_folder_path(folder["folderID"], folders_by_id),
        }
        for folder in folders
        if not root_folder or folder["folderID"] != root_folder["folderID"]
    ]

    file_items = [
        {
            "publicID": file["publicID"],
            "fileName": file["fileName"],
            "public": bool(file["public"]),
            "publicExpiresAt": file["publicExpiresAt"],
            "publicAllowDownload": bool(file["publicAllowDownload"]),
            "lastModified": file["lastModified"],
            "sizeBytes": file["sizeBytes"] or 0,
            "size": format_bytes(file["sizeBytes"] or 0),
            "path": build_folder_path(file["folderID"], folders_by_id),
        }
        for file in files
    ]

    return target_user, {
        "folders": folder_items,
        "files": file_items,
    }


async def get_access_share_items() -> list[dict]:
    public_files = await get_public_file_shares()
    public_folders = await get_public_folder_shares()

    share_items = [
        {
            "itemType": "file",
            "publicID": file["publicID"],
            "name": file["fileName"],
            "owner": file["username"],
            "userID": file["userID"],
            "lastModified": file["lastModified"],
            "expiresAt": file["publicExpiresAt"],
            "allowDownload": bool(file["publicAllowDownload"]),
        }
        for file in public_files
    ]
    share_items.extend(
        {
            "itemType": "folder",
            "publicID": folder["publicID"],
            "name": folder["folderName"],
            "owner": folder["username"],
            "userID": folder["userID"],
            "lastModified": folder["lastModified"],
            "expiresAt": folder["publicExpiresAt"],
            "allowDownload": None,
        }
        for folder in public_folders
    )

    share_items.sort(key=lambda item: str(item["lastModified"] or ""), reverse=True)
    return share_items


async def get_admin_dashboard(user_id: int, inspect_user_id: int | None = None) -> AdminDashboardResult:
    await assert_admin(user_id)

    users = await get_users_with_stats()
    total_storage_bytes = sum(user["totalSizeBytes"] or 0 for user in users)
    total_files = sum(user["fileCount"] or 0 for user in users)
    total_folders = sum(user["folderCount"] or 0 for user in users)
    admin_count = await count_admin_users()
    total_users = await count_users()

    current_user = await get_user_by_id(user_id)
    user_rows = []

    for user in users:
        is_current_user = user["userID"] == user_id
        is_admin = user["role"] == "admin"
        can_demote = is_admin and admin_count > 1 and not is_current_user
        can_promote = not is_admin
        can_delete = not is_current_user

        user_rows.append({
            "userID": user["userID"],
            "username": user["username"],
            "role": user["role"],
            "blocked": bool(user["blocked"]),
            "fileCount": user["fileCount"],
            "folderCount": user["folderCount"],
            "totalSize": format_bytes(user["totalSizeBytes"] or 0),
            "storageQuota": format_bytes(user["storageQuotaBytes"]) if user["storageQuotaBytes"] is not None else "Unlimited",
            "storageQuotaBytes": user["storageQuotaBytes"],
            "canPromote": can_promote,
            "canDemote": can_demote,
            "canDelete": can_delete,
            "isCurrentUser": is_current_user,
        })

    stats = {
        "totalUsers": total_users,
        "adminUsers": admin_count,
        "totalFiles": total_files,
        "totalFolders": total_folders,
        "totalStorage": format_bytes(total_storage_bytes),
    }

    inspected_user = None
    inspected_items = None
    if inspect_user_id is not None:
        inspected_user, inspected_items = await get_inspected_user_items(user_id, inspect_user_id)

    return AdminDashboardResult(
        current_user=current_user,
        stats=stats,
        users=user_rows,
        disks=await get_disk_stats_async(),
        audit_logs=await get_audit_logs(),
        share_items=await get_access_share_items(),
        inspected_user=inspected_user,
        inspected_items=inspected_items,
    )


async def toggle_user_role(admin_user_id: int, target_user_id: int) -> dict:
    await assert_admin(admin_user_id)

    user = await get_user_by_id(target_user_id)
    if not user:
        raise ValueError("User was not found")

    if user["userID"] == admin_user_id:
        raise ValueError("You cannot change your own role")

    if str(user["username"]).casefold() == "admin":
        raise ValueError("The admin account must keep admin privileges")

    if user["role"] == "admin":
        admin_count = await count_admin_users()
        if admin_count <= 1:
            raise ValueError("At least one admin must remain")
        next_role = "user"
    else:
        next_role = "admin"

    updated_user = await update_user_role(target_user_id, next_role)
    await create_audit_log(
        admin_user_id,
        "admin.user.role.updated",
        "user",
        str(target_user_id),
        {"username": updated_user["username"], "role": updated_user["role"]}
    )
    return updated_user


async def delete_user_account(admin_user_id: int, target_user_id: int):
    await assert_admin(admin_user_id)

    user = await get_user_by_id(target_user_id)
    if not user:
        raise ValueError("User was not found")

    if user["userID"] == admin_user_id:
        raise ValueError("You cannot delete your own account")

    if user["role"] == "admin":
        admin_count = await count_admin_users()
        if admin_count <= 1:
            raise ValueError("At least one admin must remain")

    file_paths = await get_user_file_paths(target_user_id)
    for file_row in file_paths:
        file_path = Path(file_row["serverPath"])
        if file_path.exists() and file_path.is_file():
            try:
                file_path.unlink()
            except OSError:
                continue

    await delete_user_files(target_user_id)

    folders = await get_all_user_folders(target_user_id)
    folders_by_id = {folder["folderID"]: folder for folder in folders}

    def get_depth(folder_id: int) -> int:
        depth = 0
        current_folder = folders_by_id.get(folder_id)

        while current_folder and current_folder["parentFolderID"] is not None:
            depth += 1
            current_folder = folders_by_id.get(current_folder["parentFolderID"])

        return depth

    for folder in sorted(folders, key=lambda folder: get_depth(folder["folderID"]), reverse=True):
        await delete_folder_db(target_user_id, folder["folderID"])

    await clear_audit_log_user_references(target_user_id)
    await delete_user(target_user_id)
    delete_user_sessions(target_user_id)
    await create_audit_log(
        admin_user_id,
        "admin.user.deleted",
        "user",
        str(target_user_id),
        {"username": user["username"]}
    )


async def update_active_upload_disks(admin_user_id: int, selected_disks: list[str]):
    await assert_admin(admin_user_id)

    normalized_selected_disks = {disk_path for disk_path in selected_disks if disk_path in DISKS}
    if not normalized_selected_disks:
        raise ValueError("At least one disk must remain enabled")

    for disk_path in DISKS:
        await set_upload_disk_enabled(disk_path, disk_path in normalized_selected_disks)
    await create_audit_log(
        admin_user_id,
        "admin.upload_disks.updated",
        "system",
        None,
        {"enabledDisks": sorted(normalized_selected_disks)}
    )


async def toggle_user_blocked(admin_user_id: int, target_user_id: int):
    await assert_admin(admin_user_id)

    user = await get_user_by_id(target_user_id)
    if not user:
        raise ValueError("User was not found")

    if user["userID"] == admin_user_id:
        raise ValueError("You cannot block your own account")

    updated_user = await update_user_blocked(target_user_id, not bool(user["blocked"]))
    if updated_user["blocked"]:
        delete_user_sessions(target_user_id)

    await create_audit_log(
        admin_user_id,
        "admin.user.block.updated",
        "user",
        str(target_user_id),
        {"username": updated_user["username"], "blocked": bool(updated_user["blocked"])}
    )
    return updated_user


async def set_user_storage_quota(admin_user_id: int, target_user_id: int, storage_quota_bytes: int | None):
    await assert_admin(admin_user_id)

    user = await get_user_by_id(target_user_id)
    if not user:
        raise ValueError("User was not found")

    if storage_quota_bytes is not None and storage_quota_bytes < 0:
        raise ValueError("Storage quota must be zero or greater")

    current_usage = await get_user_storage_usage(target_user_id)
    if storage_quota_bytes is not None and current_usage > storage_quota_bytes:
        raise ValueError("Current user storage exceeds the requested quota")

    updated_user = await update_user_storage_quota(target_user_id, storage_quota_bytes)
    await create_audit_log(
        admin_user_id,
        "admin.user.quota.updated",
        "user",
        str(target_user_id),
        {"username": updated_user["username"], "storageQuotaBytes": storage_quota_bytes}
    )
    return updated_user


async def revoke_file_share(admin_user_id: int, file_public_id: str):
    await assert_admin(admin_user_id)

    updated_file = await revoke_file_share_admin(file_public_id)
    if not updated_file:
        raise ValueError("File was not found")

    await create_audit_log(
        admin_user_id,
        "admin.file.share.revoked",
        "file",
        file_public_id,
        {"ownerUserID": updated_file["userID"], "fileName": updated_file["fileName"]}
    )
    return updated_file


async def revoke_folder_share(admin_user_id: int, folder_public_id: str):
    await assert_admin(admin_user_id)

    updated_folder = await revoke_folder_share_admin(folder_public_id)
    if not updated_folder:
        raise ValueError("Folder was not found")

    await create_audit_log(
        admin_user_id,
        "admin.folder.share.revoked",
        "folder",
        folder_public_id,
        {"ownerUserID": updated_folder["userID"], "folderName": updated_folder["folderName"]}
    )
    return updated_folder
