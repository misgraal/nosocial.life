from app.db.db import execute, fetch_all, fetch_one


async def get_user_role(user_id):
    user = await fetch_one("select role from users where userID=%s", (user_id,))
    return user["role"] if user else None


async def count_admin_users():
    result = await fetch_one("select count(*) as total from users where role='admin'")
    return result["total"] if result else 0


async def get_user_by_id(user_id):
    return await fetch_one(
        "select userID, username, role, blocked, storageQuotaBytes from users where userID=%s",
        (user_id,)
    )


async def get_users_by_usernames(usernames: list[str]):
    normalized_usernames = [username for username in usernames if username]
    if not normalized_usernames:
        return []

    placeholders = ", ".join(["%s"] * len(normalized_usernames))
    return await fetch_all(
        f"select userID, username, blocked from users where username in ({placeholders})",
        tuple(normalized_usernames)
    )


async def get_users_with_stats():
    return await fetch_all(
        """
        select
            users.userID,
            users.username,
            users.role,
            users.blocked,
            users.storageQuotaBytes,
            coalesce(file_stats.fileCount, 0) as fileCount,
            coalesce(file_stats.totalSizeBytes, 0) as totalSizeBytes,
            coalesce(folder_stats.folderCount, 0) as folderCount
        from users
        left join (
            select
                userID,
                count(*) as fileCount,
                coalesce(sum(sizeBytes), 0) as totalSizeBytes
            from files
            group by userID
        ) as file_stats on file_stats.userID = users.userID
        left join (
            select
                userID,
                greatest(count(*) - 1, 0) as folderCount
            from folders
            group by userID
        ) as folder_stats on folder_stats.userID = users.userID
        order by (users.role = 'admin') desc, users.username asc
        """
    )


async def get_user_folders_for_admin(user_id):
    return await fetch_all(
        """
        select folderID, publicID, public, publicExpiresAt, folderName, parentFolderID, lastModified
        from folders
        where userID=%s
        order by parentFolderID is null desc, folderName asc
        """,
        (user_id,)
    )


async def get_user_files_for_admin(user_id):
    return await fetch_all(
        """
        select fileID, publicID, public, publicExpiresAt, publicAllowDownload, fileName, folderID, sizeBytes, lastModified
        from files
        where userID=%s
        order by fileName asc
        """,
        (user_id,)
    )


async def get_public_file_shares():
    return await fetch_all(
        """
        select
            files.fileID,
            files.publicID,
            files.fileName,
            files.publicExpiresAt,
            files.publicAllowDownload,
            files.lastModified,
            files.userID,
            users.username
        from files
        inner join users on users.userID = files.userID
        where files.public=true
        order by files.lastModified desc, files.fileID desc
        """
    )


async def get_public_folder_shares():
    return await fetch_all(
        """
        select
            folders.folderID,
            folders.publicID,
            folders.folderName,
            folders.publicExpiresAt,
            folders.lastModified,
            folders.userID,
            users.username,
            folders.parentFolderID
        from folders
        inner join users on users.userID = folders.userID
        where folders.public=true and folders.parentFolderID is not null
        order by folders.lastModified desc, folders.folderID desc
        """
    )


async def count_users():
    result = await fetch_one("select count(*) as total from users")
    return result["total"] if result else 0


async def update_user_role(user_id, role):
    await execute(
        "update users set role=%s where userID=%s",
        (role, user_id,)
    )
    return await get_user_by_id(user_id)


async def update_user_blocked(user_id, blocked):
    await execute(
        "update users set blocked=%s where userID=%s",
        (blocked, user_id,)
    )
    return await get_user_by_id(user_id)


async def update_user_storage_quota(user_id, storage_quota_bytes):
    await execute(
        "update users set storageQuotaBytes=%s where userID=%s",
        (storage_quota_bytes, user_id,)
    )
    return await get_user_by_id(user_id)


async def revoke_file_share_admin(file_public_id):
    await execute(
        """
        update files
        set public=false,
            publicExpiresAt=null,
            publicPasswordHash=null,
            publicAllowDownload=true,
            lastModified=CURRENT_TIMESTAMP
        where publicID=%s
        """,
        (file_public_id,)
    )
    return await fetch_one(
        """
        select fileID, userID, publicID, public, publicExpiresAt, publicAllowDownload, fileName
        from files
        where publicID=%s
        """,
        (file_public_id,)
    )


async def revoke_folder_share_admin(folder_public_id):
    await execute(
        """
        update folders
        set public=false,
            publicExpiresAt=null,
            publicPasswordHash=null,
            lastModified=CURRENT_TIMESTAMP
        where publicID=%s
        """,
        (folder_public_id,)
    )
    return await fetch_one(
        """
        select folderID, userID, publicID, public, publicExpiresAt, folderName
        from folders
        where publicID=%s
        """,
        (folder_public_id,)
    )


async def get_user_file_paths(user_id):
    return await fetch_all(
        "select serverPath from files where userID=%s",
        (user_id,)
    )


async def get_user_storage_usage(user_id):
    result = await fetch_one(
        "select coalesce(sum(sizeBytes), 0) as totalSizeBytes from files where userID=%s",
        (user_id,)
    )
    return result["totalSizeBytes"] if result else 0


async def get_storage_usage_for_disk_path(disk_path):
    normalized_path = str(disk_path).rstrip("/\\")
    result = await fetch_one(
        """
        select coalesce(sum(sizeBytes), 0) as totalSizeBytes
        from files
        where serverPath=%s
           or serverPath like %s
           or serverPath like %s
        """,
        (
            normalized_path,
            f"{normalized_path}/%",
            f"{normalized_path}\\%",
        )
    )
    return result["totalSizeBytes"] if result else 0


async def delete_user_files(user_id):
    return await execute("delete from files where userID=%s", (user_id,))


async def delete_user_folders(user_id):
    return await execute("delete from folders where userID=%s", (user_id,))


async def delete_user(user_id):
    return await execute("delete from users where userID=%s", (user_id,))


async def clear_audit_log_user_references(user_id):
    return await execute("update audit_logs set userID=null where userID=%s", (user_id,))


async def get_upload_disk_settings():
    return await fetch_all(
        "select diskPath, isEnabled from upload_disks order by diskPath asc"
    )


async def set_upload_disk_enabled(disk_path, is_enabled):
    await execute(
        """
        insert into upload_disks (diskPath, isEnabled)
        values (%s, %s)
        on duplicate key update isEnabled=values(isEnabled)
        """,
        (disk_path, is_enabled,)
    )
