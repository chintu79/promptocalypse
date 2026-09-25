"""
SQLite database initialization with WAL mode and performance PRAGMAs.

Implements Issue #1: SQLite Schema Initialization with WAL Mode & PRAGMAs.
Reference: docs/TECH-SPEC.md §3 — Database Specification & Indexing Strategy.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import asyncio

import aiosqlite

from app.config import get_settings

# ---------------------------------------------------------------------------
# SQL: Table Definitions
# ---------------------------------------------------------------------------
# Matches TECH-SPEC.md §3 exactly. Uses IF NOT EXISTS so init_db() is
# idempotent and safe to call on every application startup.
# ---------------------------------------------------------------------------

_CREATE_TABLES = """
-- 1. User state and final aggregates
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL COLLATE NOCASE,
    email TEXT NULL COLLATE NOCASE,
    current_level INTEGER NOT NULL DEFAULT 1 CHECK(current_level BETWEEN 1 AND 3),
    start_time TIMESTAMP NOT NULL,
    completed_at TIMESTAMP NULL,
    total_prompts INTEGER NOT NULL DEFAULT 0,
    total_chars INTEGER NOT NULL DEFAULT 0,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    final_score REAL NOT NULL DEFAULT 0.0,
    is_disqualified INTEGER NOT NULL DEFAULT 0
);

-- 2. Audit ledger for prompt submissions
CREATE TABLE IF NOT EXISTS prompt_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    level INTEGER NOT NULL CHECK(level BETWEEN 1 AND 3),
    prompt_text TEXT NOT NULL,
    response_text TEXT NOT NULL,
    char_count INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    is_firewall_blocked INTEGER NOT NULL DEFAULT 0,
    is_leak_blocked INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 3. Flag submission transaction history
CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    level INTEGER NOT NULL CHECK(level BETWEEN 1 AND 3),
    submitted_key TEXT NOT NULL,
    is_correct INTEGER NOT NULL,
    submitted_at TIMESTAMP NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 4. Shared rate-limiter cooldown state (Issue #40)
-- One row per participant so every Uvicorn worker process enforces the same
-- cooldown window; in-memory state exists once per worker process only.
CREATE TABLE IF NOT EXISTS rate_limits (
    user_id TEXT PRIMARY KEY,
    last_request_at REAL NOT NULL
);
"""

# ---------------------------------------------------------------------------
# SQL: Index Definitions
# ---------------------------------------------------------------------------
# Composite leaderboard index enables the multi-tier tie-breaking ORDER BY
# used by GET /api/leaderboard without a filesort.
# ---------------------------------------------------------------------------

_CREATE_INDEXES = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username
    ON users(username);

CREATE INDEX IF NOT EXISTS idx_users_email
    ON users(email);

CREATE INDEX IF NOT EXISTS idx_leaderboard_rank
    ON users(
        final_score DESC,
        current_level DESC,
        total_prompts ASC,
        total_chars ASC,
        completed_at ASC
    );

CREATE INDEX IF NOT EXISTS idx_prompt_ledger_user
    ON prompt_ledger(user_id, level);

CREATE INDEX IF NOT EXISTS idx_submissions_user
    ON submissions(user_id);
"""

# ---------------------------------------------------------------------------
# PRAGMAs applied on every new connection
# ---------------------------------------------------------------------------
# - WAL:          Non-blocking concurrent readers during write transactions.
# - synchronous:  NORMAL is safe with WAL and avoids fsync on every commit.
# - busy_timeout: Wait up to 10 s for a write-lock instead of failing immediately.
# - cache_size:   -64000 → 64 MB in-memory page cache (negative = KiB).
# - foreign_keys: Enforce FK constraints at runtime (SQLite default is OFF).
# ---------------------------------------------------------------------------

_PRAGMAS = [
    "PRAGMA journal_mode = WAL;",
    "PRAGMA synchronous = NORMAL;",
    "PRAGMA busy_timeout = 10000;",
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
    settings = get_settings()
    if _GLOBAL_POOL is None or _GLOBAL_POOL.db_path != settings.DB_PATH:
        # Note: In a real app we'd carefully close the old pool.
        # But this condition only triggers in tests when DB_PATH changes.
        _GLOBAL_POOL = AiosqlitePool(settings.DB_PATH, max_size=10)
    return _GLOBAL_POOL



async def _apply_pragmas(db: aiosqlite.Connection) -> None:
    """Apply performance and safety PRAGMAs to the given connection."""
    for pragma in _PRAGMAS:
        await db.execute(pragma)


async def init_db() -> None:
    """
    Initialize the SQLite database: apply PRAGMAs, create tables, and
    build indexes.

    This function is idempotent — safe to call on every application startup.
    It is invoked from the FastAPI ``startup`` event in ``app/main.py``.
    """
    settings = get_settings()
    db = await aiosqlite.connect(settings.DB_PATH)
    try:
        await _apply_pragmas(db)
        await db.executescript(_CREATE_TABLES)

        # Migration: Ensure email column exists if users table was created earlier
        async with db.execute("PRAGMA table_info(users)") as cursor:
            columns = [row[1] for row in await cursor.fetchall()]
            if "email" not in columns:
                await db.execute("ALTER TABLE users ADD COLUMN email TEXT NULL COLLATE NOCASE")

        await db.executescript(_CREATE_INDEXES)
        await db.commit()
    finally:
        await db.close()


async def get_db() -> aiosqlite.Connection:
    """
    DEPRECATED for manual use. 
    Use get_db_context() to properly acquire and release from the pool.
    """
    pool = get_pool()
    return await pool.acquire()

@asynccontextmanager
async def get_db_context() -> AsyncGenerator[aiosqlite.Connection, None]:
    """
    Async context manager that yields a pooled database connection
    and ensures it is returned to the pool on exit.
    """
    pool = get_pool()
    db = await pool.acquire()
    try:
        yield db
    finally:
        await pool.release(db)
