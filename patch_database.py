import re

with open("backend/app/database.py", "r") as f:
    content = f.read()

import_statement = """from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import asyncio"""

content = content.replace("from collections.abc import AsyncGenerator\nfrom contextlib import asynccontextmanager", import_statement)

pool_code = """_PRAGMAS = [
    "PRAGMA journal_mode = WAL;",
    "PRAGMA synchronous = NORMAL;",
    "PRAGMA busy_timeout = 5000;",
    "PRAGMA cache_size = -64000;",
    "PRAGMA foreign_keys = ON;",
]

class AiosqlitePool:
    def __init__(self, db_path: str, max_size: int = 10):
        self.db_path = db_path
        self.max_size = max_size
        self._pool: asyncio.Queue[aiosqlite.Connection] = asyncio.Queue(maxsize=max_size)
        self._created = 0
        self._lock = asyncio.Lock()

    async def acquire(self) -> aiosqlite.Connection:
        async with self._lock:
            if self._pool.empty() and self._created < self.max_size:
                conn = await aiosqlite.connect(self.db_path)
                await _apply_pragmas(conn)
                conn.row_factory = aiosqlite.Row
                self._created += 1
                return conn
        return await self._pool.get()

    async def release(self, conn: aiosqlite.Connection):
        await self._pool.put(conn)

    async def close_all(self):
        while not self._pool.empty():
            conn = await self._pool.get()
            await conn.close()

_GLOBAL_POOL = None

def get_pool() -> AiosqlitePool:
    global _GLOBAL_POOL
    if _GLOBAL_POOL is None:
        settings = get_settings()
        _GLOBAL_POOL = AiosqlitePool(settings.DB_PATH, max_size=10)
    return _GLOBAL_POOL
"""

content = content.replace("""_PRAGMAS = [
    "PRAGMA journal_mode = WAL;",
    "PRAGMA synchronous = NORMAL;",
    "PRAGMA busy_timeout = 5000;",
    "PRAGMA cache_size = -64000;",
    "PRAGMA foreign_keys = ON;",
]""", pool_code)

old_get_db = """async def get_db() -> aiosqlite.Connection:
    \"\"\"
    Open and return a new aiosqlite connection with PRAGMAs applied.

    Callers are responsible for closing the connection when done.
    Prefer :func:`get_db_context` for automatic cleanup.
    \"\"\"
    settings = get_settings()
    db = await aiosqlite.connect(settings.DB_PATH)
    await _apply_pragmas(db)
    db.row_factory = aiosqlite.Row
    return db


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[aiosqlite.Connection, None]:
    \"\"\"
    Async context manager that yields a fully configured database connection
    and ensures it is closed on exit.

    Usage::

        async with get_db_context() as db:
            cursor = await db.execute("SELECT ...")
    \"\"\"
    db = await get_db()
    try:
        yield db
    finally:
        await db.close()"""

new_get_db = """async def get_db() -> aiosqlite.Connection:
    \"\"\"
    DEPRECATED for manual use. 
    Use get_db_context() to properly acquire and release from the pool.
    \"\"\"
    pool = get_pool()
    return await pool.acquire()

@asynccontextmanager
async def get_db_context() -> AsyncGenerator[aiosqlite.Connection, None]:
    \"\"\"
    Async context manager that yields a pooled database connection
    and ensures it is returned to the pool on exit.
    \"\"\"
    pool = get_pool()
    db = await pool.acquire()
    try:
        yield db
    finally:
        await pool.release(db)"""

content = content.replace(old_get_db, new_get_db)

with open("backend/app/database.py", "w") as f:
    f.write(content)
