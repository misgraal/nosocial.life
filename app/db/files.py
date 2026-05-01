from app.db.db import execute, fetch_all, fetch_one
from app.security.folderHashGenerator import generateRandomHash


FILE_SUMMARY_FIELDS = "publicID, public, publicExpiresAt, publicAllowDownload, fileName, sizeBytes, previewPath, lastModified"
FILE_DETAIL_FIELDS = "fileID, userID, publicID, public, publicExpiresAt, publicPasswordHash, publicAllowDownload, fileName, folderID, serverPath, previewPath, sizeBytes, lastModified"


async def get_users_roots_child_files(id: int):
    return await fetch_all(
        f"select {FILE_SUMMARY_FIELDS} from files where userID=%s and folderID in (select folderID from folders where userID=%s and parentFolderID is null)",
        (id, id,)
    )


async def get_folders_child_files(folderID):
    return await fetch_all(
        f"select {FILE_SUMMARY_FIELDS} from files where folderID=%s",
        (folderID,)
    )


async def get_public_media_files(media_dirs: list[str]):
    if not media_dirs:
        return []

    clauses = []
    args = []
    for media_dir in media_dirs:
        normalized_dir = media_dir.rstrip("/\\")
        clauses.append("(serverPath=%s or serverPath like %s or serverPath like %s)")
        args.extend([
            normalized_dir,
            f"{normalized_dir}/%",
            f"{normalized_dir}\\%"
        ])

    where_clause = " or ".join(clauses)
    return await fetch_all(
        f"""
        select {FILE_SUMMARY_FIELDS}
        from files
        where public=true
          and ({where_clause})
        order by fileName asc, lastModified desc
        """,
        tuple(args)
    )


async def get_folders_child_files_for_delete(folderID):
    return await fetch_all(
        "select fileID, publicID, serverPath from files where folderID=%s",
        (folderID,)
    )


async def create_file_db(fileName, userID, folderID, serverPath, sizeBytes, previewPath):
    publicID = generateRandomHash()
    await execute(
        """
        insert into files (
            userID, publicID, fileName, folderID, serverPath, sizeBytes, previewPath, createdAt, lastModified
        ) values (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (userID, publicID, fileName, folderID, serverPath, sizeBytes, previewPath,)
    )
    return await fetch_one(
        f"select {FILE_SUMMARY_FIELDS} from files where userID=%s and publicID=%s",
        (userID, publicID,)
    )


async def get_user_file_by_id(userID, fileID):
    return await fetch_one(
        f"select {FILE_DETAIL_FIELDS} from files where userID=%s and fileID=%s",
        (userID, fileID,)
    )


async def get_user_file_by_public_id(userID, publicID):
    return await fetch_one(
        f"select {FILE_DETAIL_FIELDS} from files where userID=%s and publicID=%s",
        (userID, publicID,)
    )


async def get_file_by_public_id(publicID):
    return await fetch_one(
        f"select {FILE_DETAIL_FIELDS} from files where publicID=%s",
        (publicID,)
    )


async def is_file_shared_with_user(fileID, userID):
    share = await fetch_one(
        "select shareID from file_user_shares where fileID=%s and recipientUserID=%s",
        (fileID, userID,)
    )
    return bool(share)


async def get_file_shared_users(fileID):
    return await fetch_all(
        """
        select users.userID, users.username
        from file_user_shares
        inner join users on users.userID = file_user_shares.recipientUserID
        where file_user_shares.fileID=%s
        order by users.username asc
        """,
        (fileID,)
    )


async def replace_file_shared_users(fileID, recipient_user_ids: list[int]):
    await execute("delete from file_user_shares where fileID=%s", (fileID,))
    for recipient_user_id in recipient_user_ids:
        await execute(
            "insert into file_user_shares (fileID, recipientUserID) values (%s, %s)",
            (fileID, recipient_user_id,)
        )


async def get_shared_files_for_user(userID):
    return await fetch_all(
        f"""
        select
            {FILE_SUMMARY_FIELDS},
            files.folderID,
            files.userID,
            owners.username as ownerUsername
        from file_user_shares
        inner join files on files.fileID = file_user_shares.fileID
        inner join users as owners on owners.userID = files.userID
        where file_user_shares.recipientUserID=%s
        order by files.lastModified desc, files.fileName asc
        """,
        (userID,)
    )


async def get_user_file_by_name_in_folder(userID, folderID, fileName, excludeFileID=None):
    query = "select fileID, fileName from files where userID=%s and folderID=%s and fileName=%s"
    args = [userID, folderID, fileName]
    if excludeFileID is not None:
        query += " and fileID!=%s"
        args.append(excludeFileID)
    return await fetch_one(query, tuple(args))


async def update_file_name_db(userID, fileID, fileName, serverPath, previewPath):
    await execute(
        "update files set fileName=%s, serverPath=%s, previewPath=%s, lastModified=CURRENT_TIMESTAMP where userID=%s and fileID=%s",
        (fileName, serverPath, previewPath, userID, fileID,)
    )
    return await fetch_one(
        f"select {FILE_SUMMARY_FIELDS} from files where userID=%s and fileID=%s",
        (userID, fileID,)
    )


async def update_file_folder_db(userID, fileID, folderID):
    await execute(
        "update files set folderID=%s, lastModified=CURRENT_TIMESTAMP where userID=%s and fileID=%s",
        (folderID, userID, fileID,)
    )
    return await fetch_one(
        f"select {FILE_SUMMARY_FIELDS} from files where userID=%s and fileID=%s",
        (userID, fileID,)
    )


async def update_file_public_db(userID, fileID, isPublic):
    await execute(
        "update files set public=%s, lastModified=CURRENT_TIMESTAMP where userID=%s and fileID=%s",
        (isPublic, userID, fileID,)
    )
    return await fetch_one(
        f"select {FILE_SUMMARY_FIELDS} from files where userID=%s and fileID=%s",
        (userID, fileID,)
    )


async def update_file_share_settings_db(userID, fileID, isPublic, expiresAt, passwordHash, allowDownload):
    await execute(
        """
        update files
        set public=%s,
            publicExpiresAt=%s,
            publicPasswordHash=%s,
            publicAllowDownload=%s,
            lastModified=CURRENT_TIMESTAMP
        where userID=%s and fileID=%s
        """,
        (isPublic, expiresAt, passwordHash, allowDownload, userID, fileID,)
    )
    return await fetch_one(
        f"select {FILE_DETAIL_FIELDS} from files where userID=%s and fileID=%s",
        (userID, fileID,)
    )


async def delete_file_db(userID, fileID):
    return await execute("delete from files where userID=%s and fileID=%s", (userID, fileID,))


async def search_user_files_by_name(userID, query, limit=100):
    return await fetch_all(
        f"""
        select {FILE_SUMMARY_FIELDS}, folderID
        from files
        where userID=%s
          and fileName like concat('%%', %s, '%%')
        order by fileName asc
        limit %s
        """,
        (userID, query, limit)
    )
