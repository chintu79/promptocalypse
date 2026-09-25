import re

with open("backend/app/database.py", "r") as f:
    content = f.read()

# Replace CREATE TABLE users
old_table = """CREATE TABLE IF NOT EXISTS users (
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
);"""

new_table = """CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL COLLATE NOCASE,
    email TEXT NULL COLLATE NOCASE,
    active_level INTEGER NOT NULL DEFAULT 1 CHECK(active_level BETWEEN 1 AND 3),
    cleared_levels TEXT NOT NULL DEFAULT '[]',
    start_time TIMESTAMP NOT NULL,
    completed_at TIMESTAMP NULL,
    total_prompts INTEGER NOT NULL DEFAULT 0,
    total_chars INTEGER NOT NULL DEFAULT 0,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    final_score REAL NOT NULL DEFAULT 0.0,
    is_disqualified INTEGER NOT NULL DEFAULT 0
);"""

content = content.replace(old_table, new_table)

# Add migrations
old_migration = """        # Migration: Ensure email column exists if users table was created earlier
        async with db.execute("PRAGMA table_info(users)") as cursor:
            columns = [row[1] for row in await cursor.fetchall()]
            if "email" not in columns:
                await db.execute("ALTER TABLE users ADD COLUMN email TEXT NULL COLLATE NOCASE")"""

new_migration = """        # Migration: Ensure new columns exist if users table was created earlier
        async with db.execute("PRAGMA table_info(users)") as cursor:
            columns = [row[1] for row in await cursor.fetchall()]
            if "email" not in columns:
                await db.execute("ALTER TABLE users ADD COLUMN email TEXT NULL COLLATE NOCASE")
            if "active_level" not in columns and "current_level" in columns:
                await db.execute("ALTER TABLE users RENAME COLUMN current_level TO active_level")
            if "cleared_levels" not in columns:
                await db.execute("ALTER TABLE users ADD COLUMN cleared_levels TEXT NOT NULL DEFAULT '[]'")"""

content = content.replace(old_migration, new_migration)

# Fix indexes that might reference current_level
content = content.replace("current_level DESC,", "active_level DESC,")

with open("backend/app/database.py", "w") as f:
    f.write(content)
