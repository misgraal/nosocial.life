from app.db.db import execute, fetch_all, fetch_one
from app.security.folderHashGenerator import generateRandomHash


FOLDER_SUMMARY_FIELDS = "publicID, public, publicExpiresAt, folderName, lastModified"
FOLDER_DETAIL_FIELDS = "folderID, userID, publicID, public, publicExpiresAt, publicPasswordHash, folderName, parentFolderID, lastModified"


async def get_users_root_folder(id: int):
    return await fetch_all(
        f"select folderID, folderName, publicID, public, publicExpiresAt from folders where userID=%s and parentFolderID is null",
        (id,)
    )


async def add_root_folder(userID, folderName):
    return await execute(
        "insert into folders (userID, folderName, createdAt, lastModified, publicID) values (%s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, %s)",
        (userID, folderName, generateRandomHash(),)
    )


async def get_users_roots_child_folders(id: int):
    return await fetch_all(
        f"select {FOLDER_SUMMARY_FIELDS} from folders where userID=%s and parentFolderID in (select folderID from folders where userID=%s and parentFolderID is null)",
        (id, id,)
    )


async def create_folder_db(folderName, userID, parentFolderID):
    publicID = generateRandomHash()
    await execute(
        "insert into folders (userID, folderName, parentFolderID, createdAt, lastModified, publicID) values (%s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, %s)",
        (userID, folderName, parentFolderID, publicID,)
    )
    return await fetch_one(
        f"select {FOLDER_SUMMARY_FIELDS} from folders where userID=%s and publicID=%s",
        (userID, publicID,)
    )


async def get_folder_id_by_public_id(publicID):
    return await fetch_one("select folderID from folders where publicID=%s", (publicID,))


async def get_user_folder_by_public_id(userID, publicID):
    return await fetch_one(
        f"select {FOLDER_DETAIL_FIELDS} from folders where userID=%s and publicID=%s",
        (userID, publicID,)
    )


async def get_user_folder_by_id(userID, folderID):
    return await fetch_one(
        f"select {FOLDER_DETAIL_FIELDS} from folders where userID=%s and folderID=%s",
        (userID, folderID,)
    )


async def get_folder_by_public_id(publicID):
    return await fetch_one(
        f"select {FOLDER_DETAIL_FIELDS} from folders where publicID=%s",
        (publicID,)
    )


async def get_folder_by_id(folderID):
    return await fetch_one(
        f"select {FOLDER_DETAIL_FIELDS} from folders where folderID=%s",
        (folderID,)
    )


async def is_folder_shared_with_user(folderID, userID):
    share = await fetch_one(
        "select shareID from folder_user_shares where folderID=%s and recipientUserID=%s",
        (folderID, userID,)
    )
    return bool(share)


async def get_folder_shared_users(folderID):
    return await fetch_all(
        """
        select users.userID, users.username
        from folder_user_shares
        inner join users on users.userID = folder_user_shares.recipientUserID
        where folder_user_shares.folderID=%s
        order by users.username asc
        """,
        (folderID,)
    )


async def replace_folder_shared_users(folderID, recipient_user_ids: list[int]):
    await execute("delete from folder_user_shares where folderID=%s", (folderID,))
    for recipient_user_id in recipient_user_ids:
        await execute(
            "insert into folder_user_shares (folderID, recipientUserID) values (%s, %s)",
            (folderID, recipient_user_id,)
        )


async def get_shared_root_folders_for_user(userID):
    return await fetch_all(
        f"""
        select
            {FOLDER_DETAIL_FIELDS},
            owners.username as ownerUsername
        from folder_user_shares
        inner join folders on folders.folderID = folder_user_shares.folderID
        inner join users as owners on owners.userID = folders.userID
        where folder_user_shares.recipientUserID=%s
        order by folders.lastModified desc, folders.folderName asc
        """,
        (userID,)
    )


async def get_folders_names_in_folder(userID, folderID):
    return await fetch_all(
        "select folderName from folders where userID=%s and parentFolderID=%s",
        (userID, folderID,)
    )


async def get_user_folder_by_name_in_parent(userID, parentFolderID, folderName, excludeFolderID=None):
    query = "select folderID, publicID, folderName from folders where userID=%s and parentFolderID <=> %s and folderName=%s"
    args = [userID, parentFolderID, folderName]
    if excludeFolderID is not None:
        query += " and folderID!=%s"
        args.append(excludeFolderID)
    return await fetch_one(query, tuple(args))


async def get_folders_child_folders(folderID):
    return await fetch_all(
        f"select {FOLDER_DETAIL_FIELDS} from folders where parentFolderID=%s",
        (folderID,)
    )


async def get_folders_child_folder_ids(folderID):
    return await fetch_all("select folderID from folders where parentFolderID=%s", (folderID,))


async def get_parent_folder(folderID):
    return await fetch_one("select parentFolderID from folders where folderID=%s", (folderID,))


async def update_folder_name_db(userID, folderID, folderName):
    await execute(
        "update folders set folderName=%s, lastModified=CURRENT_TIMESTAMP where userID=%s and folderID=%s",
        (folderName, userID, folderID,)
    )
    return await fetch_one(
        f"select {FOLDER_SUMMARY_FIELDS} from folders where userID=%s and folderID=%s",
        (userID, folderID,)
    )


async def update_folder_parent_db(userID, folderID, parentFolderID):
    await execute(
        "update folders set parentFolderID=%s, lastModified=CURRENT_TIMESTAMP where userID=%s and folderID=%s",
        (parentFolderID, userID, folderID,)
    )
    return await fetch_one(
        f"select {FOLDER_SUMMARY_FIELDS} from folders where userID=%s and folderID=%s",
        (userID, folderID,)
    )


async def update_folder_public_db(userID, folderID, isPublic):
    await execute(
        "update folders set public=%s, lastModified=CURRENT_TIMESTAMP where userID=%s and folderID=%s",
        (isPublic, userID, folderID,)
    )
    return await fetch_one(
        f"select {FOLDER_SUMMARY_FIELDS} from folders where userID=%s and folderID=%s",
        (userID, folderID,)
    )


async def update_folder_share_settings_db(userID, folderID, isPublic, expiresAt, passwordHash):
    await execute(
        """
        update folders
        set public=%s,
            publicExpiresAt=%s,
            publicPasswordHash=%s,
            lastModified=CURRENT_TIMESTAMP
        where userID=%s and folderID=%s
        """,
        (isPublic, expiresAt, passwordHash, userID, folderID,)
    )
    return await fetch_one(
        f"select {FOLDER_DETAIL_FIELDS} from folders where userID=%s and folderID=%s",
        (userID, folderID,)
    )


async def get_all_user_folders(userID):
    return await fetch_all(
        f"select folderID, publicID, public, publicExpiresAt, folderName, parentFolderID from folders where userID=%s order by parentFolderID is null desc, folderName asc",
        (userID,)
    )


async def delete_folder_db(userID, folderID):
    return await execute("delete from folders where userID=%s and folderID=%s", (userID, folderID,))


async def search_user_folders_by_name(userID, query, limit=100):
    return await fetch_all(
        f"""
        select folderID, publicID, public, publicExpiresAt, folderName, parentFolderID, lastModified
        from folders
        where userID=%s
          and parentFolderID is not null
          and folderName like concat('%%', %s, '%%')
        order by folderName asc
        limit %s
        """,
        (userID, query, limit)
    )
