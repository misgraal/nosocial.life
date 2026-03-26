from __future__ import annotations

import os
import asyncmy
from contextlib import asynccontextmanager
from fastapi import FastAPI

_pool: asyncmy.Pool | None = None

async def init_pool() -> None:
    global _pool
    if _pool is None:
        _pool = await asyncmy.create_pool(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT")),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            db=os.getenv("DB_NAME"),
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
        
async def init_schema():
    statements = [
        """
            create table if not exists users (
                userID int NOT NULL AUTO_INCREMENT,
                userName varchar(255) NOT NULL,
                password varchar(512) NOT NULL,
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
                
                primary key (folderID),
                foreign key (userID) references users(userID),
                foreign key (parentFolderID) references folders(folderID)
            );
        """,
        """
            create table if not exists files (
                fileID int NOT NULL AUTO_INCREMENT,
                userID int NOT NULL,
                fileName varchar(255) NOT NULL,
                folderID int NOT NULL,
                serverPath varchar(512) NOT NULL,
                sizeBytes int NOT NULL,
                previewPath varchar(512) NOT NULL,
                createdAt datetime NOT NULL,
                lastModified datetime NOT NULL,
                
                primary key (fileID),
                foreign key (userID) references users(userID),
                foreign key (folderID) references folders(folderID)
            );
        """
    ]
    for statement in statements:
        await execute(statement)

