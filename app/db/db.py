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
    try:
        yield
    finally:
        await close_pool()


async def fetch_one(query: str, args: tuple | None = None):
    if _pool is None:
        raise RuntimeError("DB pool is not initialized")
    async with _pool.acquire() as conn:
        async with conn.cursor(asyncmy.cursors.DictCursor) as cur:
            await cur.execute(query, args)
            return await cur.fetchone()
        
async def fetch_all(query: str, args: tuple | None = None):
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

