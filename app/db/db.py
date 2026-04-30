from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

import asyncmy
from fastapi import FastAPI

from app.security.folderHashGenerator import generateRandomHash
from config import DISKS, MEDIA_FOLDER_NAME, TMP_FOLDER


_pool: asyncmy.Pool | None = None


def ensure_storage_directories() -> None:
    for disk_path in DISKS:
        disk = Path(disk_path)
        disk.mkdir(parents=True, exist_ok=True)
        (disk / TMP_FOLDER).mkdir(parents=True, exist_ok=True)
        (disk / MEDIA_FOLDER_NAME).mkdir(parents=True, exist_ok=True)


async def init_pool() -> None:
    global _pool
    if _pool is None:
        _pool = await asyncmy.create_pool(
            host=os.getenv("DB_HOST", "127.0.0.1"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "server"),
            password=os.getenv("DB_PASSWORD", "server"),
            db=os.getenv("DB_NAME", "nosocial"),
            autocommit=True,
        )


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        await _pool.wait_closed()
        _pool = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_storage_directories()
    await init_pool()
    await init_schema()
    try:
        yield
    finally:
        await close_pool()


async def fetch_one(query: str, args: tuple | None = None) -> dict:
    if _pool is None:
        raise RuntimeError("DB pool is not initialized")
    async with _pool.acquire() as conn:
        async with conn.cursor(asyncmy.cursors.DictCursor) as cur:
            await cur.execute(query, args)
            return await cur.fetchone()


async def fetch_all(query: str, args: tuple | None = None) -> list[dict]:
    if _pool is None:
        raise RuntimeError("DB pool is not initialized")
    async with _pool.acquire() as conn:
        async with conn.cursor(asyncmy.cursors.DictCursor) as cur:
            await cur.execute(query, args)
            return await cur.fetchall()


async def execute(query: str, args: tuple | None = None):
    if _pool is None:
        raise RuntimeError("DB pool is not initialized")
    async with _pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, args)
            return cur.rowcount


async def ensure_schema_migrations_table():
    await execute(
        """
        create table if not exists schema_migrations (
            migrationName varchar(255) NOT NULL,
            appliedAt datetime NOT NULL default CURRENT_TIMESTAMP,
            primary key (migrationName)
        );
        """
    )


async def is_migration_applied(migration_name: str) -> bool:
    migration = await fetch_one(
        "select migrationName from schema_migrations where migrationName=%s",
        (migration_name,)
    )
    return bool(migration)


async def record_migration(migration_name: str):
    await execute(
        "insert into schema_migrations (migrationName) values (%s)",
        (migration_name,)
    )


async def init_schema():
    statements = [
        """
            create table if not exists schema_migrations (
                migrationName varchar(255) NOT NULL,
                appliedAt datetime NOT NULL default CURRENT_TIMESTAMP,
                primary key (migrationName)
            );
        """,
        """
            create table if not exists users (
                userID int NOT NULL AUTO_INCREMENT,
                username varchar(255) NOT NULL,
                password varchar(512) NOT NULL,
                blocked boolean NOT NULL default false,
                storageQuotaBytes BIGINT NULL,
                role varchar(20) NOT NULL default 'user'
                CHECK (role in ('user', 'admin')),
                PRIMARY KEY (userID),
                UNIQUE (username)
            );
        """,
        """
            create table if not exists folders (
                folderID int NOT NULL AUTO_INCREMENT,
                userID int NOT NULL,
                folderName varchar(255) NOT NULL,
                parentFolderID int NULL,
                createdAt datetime NOT NULL,
                lastModified datetime NOT NULL,
                publicID varchar(20),
                public boolean default false,
                publicExpiresAt datetime NULL,
                publicPasswordHash varchar(512) NULL,

                primary key (folderID),
                foreign key (userID) references users(userID),
                foreign key (parentFolderID) references folders(folderID)
            );
        """,
        """
            create table if not exists files (
                fileID int NOT NULL AUTO_INCREMENT,
                userID int NOT NULL,
                publicID varchar(20),
                public boolean default false,
                publicExpiresAt datetime NULL,
                publicPasswordHash varchar(512) NULL,
                publicAllowDownload boolean NOT NULL default true,
                fileName varchar(255) NOT NULL,
                folderID int NOT NULL,
                serverPath varchar(512) NOT NULL,
                sizeBytes BIGINT NOT NULL,
                previewPath varchar(512) NOT NULL,
                createdAt datetime NOT NULL,
                lastModified datetime NOT NULL,

                primary key (fileID),
                foreign key (userID) references users(userID),
                foreign key (folderID) references folders(folderID)
            );
        """,
        """
            create table if not exists upload_disks (
                diskPath varchar(512) NOT NULL,
                isEnabled boolean NOT NULL default true,
                primary key (diskPath)
            );
        """,
        """
            create table if not exists audit_logs (
                logID int NOT NULL AUTO_INCREMENT,
                userID int NULL,
                action varchar(120) NOT NULL,
                targetType varchar(60) NULL,
                targetPublicID varchar(120) NULL,
                details text NULL,
                createdAt datetime NOT NULL default CURRENT_TIMESTAMP,

                primary key (logID),
                foreign key (userID) references users(userID)
            );
        """,
        """
            create table if not exists file_user_shares (
                shareID int NOT NULL AUTO_INCREMENT,
                fileID int NOT NULL,
                recipientUserID int NOT NULL,
                createdAt datetime NOT NULL default CURRENT_TIMESTAMP,

                primary key (shareID),
                unique key uniq_file_recipient (fileID, recipientUserID),
                foreign key (fileID) references files(fileID) on delete cascade,
                foreign key (recipientUserID) references users(userID) on delete cascade
            );
        """,
        """
            create table if not exists folder_user_shares (
                shareID int NOT NULL AUTO_INCREMENT,
                folderID int NOT NULL,
                recipientUserID int NOT NULL,
                createdAt datetime NOT NULL default CURRENT_TIMESTAMP,

                primary key (shareID),
                unique key uniq_folder_recipient (folderID, recipientUserID),
                foreign key (folderID) references folders(folderID) on delete cascade,
                foreign key (recipientUserID) references users(userID) on delete cascade
            );
        """
    ]

    for statement in statements:
        await execute(statement)

    await ensure_schema_migrations_table()

    if not await is_migration_applied("2026_04_27_files_bigint_size"):
        await execute("ALTER TABLE files MODIFY COLUMN sizeBytes BIGINT NOT NULL")
        await record_migration("2026_04_27_files_bigint_size")

    if not await is_migration_applied("2026_04_27_files_public_id"):
        file_public_id_column = await fetch_all("SHOW COLUMNS FROM files LIKE 'publicID'")
        if not file_public_id_column:
            await execute("ALTER TABLE files ADD COLUMN publicID varchar(20) NULL")
        await record_migration("2026_04_27_files_public_id")

    if not await is_migration_applied("2026_04_27_files_public_flag"):
        file_public_column = await fetch_all("SHOW COLUMNS FROM files LIKE 'public'")
        if not file_public_column:
            await execute("ALTER TABLE files ADD COLUMN public boolean default false")
        await record_migration("2026_04_27_files_public_flag")

    if not await is_migration_applied("2026_04_27_users_blocked"):
        user_blocked_column = await fetch_all("SHOW COLUMNS FROM users LIKE 'blocked'")
        if not user_blocked_column:
            await execute("ALTER TABLE users ADD COLUMN blocked boolean NOT NULL default false")
        await record_migration("2026_04_27_users_blocked")

    if not await is_migration_applied("2026_04_27_users_storage_quota"):
        user_quota_column = await fetch_all("SHOW COLUMNS FROM users LIKE 'storageQuotaBytes'")
        if not user_quota_column:
            await execute("ALTER TABLE users ADD COLUMN storageQuotaBytes BIGINT NULL")
        await record_migration("2026_04_27_users_storage_quota")

    if not await is_migration_applied("2026_04_27_users_username_normalized"):
        username_column = await fetch_all("SHOW COLUMNS FROM users LIKE 'username'")
        legacy_username_column = await fetch_all("SHOW COLUMNS FROM users LIKE 'userName'")
        if not username_column and legacy_username_column:
            await execute("ALTER TABLE users CHANGE COLUMN userName username varchar(255) NOT NULL")
        await record_migration("2026_04_27_users_username_normalized")

    await execute("update users set role='admin' where lower(username)='admin' and role <> 'admin'")

    if not await is_migration_applied("2026_04_27_share_controls"):
        folder_public_expires_column = await fetch_all("SHOW COLUMNS FROM folders LIKE 'publicExpiresAt'")
        if not folder_public_expires_column:
            await execute("ALTER TABLE folders ADD COLUMN publicExpiresAt datetime NULL")

        folder_public_password_column = await fetch_all("SHOW COLUMNS FROM folders LIKE 'publicPasswordHash'")
        if not folder_public_password_column:
            await execute("ALTER TABLE folders ADD COLUMN publicPasswordHash varchar(512) NULL")

        file_public_expires_column = await fetch_all("SHOW COLUMNS FROM files LIKE 'publicExpiresAt'")
        if not file_public_expires_column:
            await execute("ALTER TABLE files ADD COLUMN publicExpiresAt datetime NULL")

        file_public_password_column = await fetch_all("SHOW COLUMNS FROM files LIKE 'publicPasswordHash'")
        if not file_public_password_column:
            await execute("ALTER TABLE files ADD COLUMN publicPasswordHash varchar(512) NULL")

        file_public_download_column = await fetch_all("SHOW COLUMNS FROM files LIKE 'publicAllowDownload'")
        if not file_public_download_column:
            await execute("ALTER TABLE files ADD COLUMN publicAllowDownload boolean NOT NULL default true")

        await record_migration("2026_04_27_share_controls")

    if not await is_migration_applied("2026_04_27_backfill_file_public_ids"):
        files_without_public_id = await fetch_all("select fileID from files where publicID is null or publicID=''", ())
        for file_row in files_without_public_id:
            await execute(
                "update files set publicID=%s where fileID=%s",
                (generateRandomHash(), file_row["fileID"])
            )
        await record_migration("2026_04_27_backfill_file_public_ids")

    if not await is_migration_applied("2026_04_27_seed_upload_disks"):
        from config import DISKS

        for disk_path in DISKS:
            existing_disk = await fetch_one(
                "select diskPath from upload_disks where diskPath=%s",
                (disk_path,)
            )
            if existing_disk:
                continue

            await execute(
                "insert into upload_disks (diskPath, isEnabled) values (%s, true)",
                (disk_path,)
            )

        await record_migration("2026_04_27_seed_upload_disks")

    if not await is_migration_applied("2026_04_27_user_shares"):
        await execute(
            """
            create table if not exists file_user_shares (
                shareID int NOT NULL AUTO_INCREMENT,
                fileID int NOT NULL,
                recipientUserID int NOT NULL,
                createdAt datetime NOT NULL default CURRENT_TIMESTAMP,

                primary key (shareID),
                unique key uniq_file_recipient (fileID, recipientUserID),
                foreign key (fileID) references files(fileID) on delete cascade,
                foreign key (recipientUserID) references users(userID) on delete cascade
            );
            """
        )
        await execute(
            """
            create table if not exists folder_user_shares (
                shareID int NOT NULL AUTO_INCREMENT,
                folderID int NOT NULL,
                recipientUserID int NOT NULL,
                createdAt datetime NOT NULL default CURRENT_TIMESTAMP,

                primary key (shareID),
                unique key uniq_folder_recipient (folderID, recipientUserID),
                foreign key (folderID) references folders(folderID) on delete cascade,
                foreign key (recipientUserID) references users(userID) on delete cascade
            );
            """
        )
        await record_migration("2026_04_27_user_shares")
