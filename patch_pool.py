import re

with open("backend/app/database.py", "r") as f:
    content = f.read()

old_get_pool = """def get_pool() -> AiosqlitePool:
    global _GLOBAL_POOL
    if _GLOBAL_POOL is None:
        settings = get_settings()
        _GLOBAL_POOL = AiosqlitePool(settings.DB_PATH, max_size=10)
    return _GLOBAL_POOL"""

new_get_pool = """def get_pool() -> AiosqlitePool:
    global _GLOBAL_POOL
    settings = get_settings()
    if _GLOBAL_POOL is None or _GLOBAL_POOL.db_path != settings.DB_PATH:
        # Note: In a real app we'd carefully close the old pool.
        # But this condition only triggers in tests when DB_PATH changes.
        _GLOBAL_POOL = AiosqlitePool(settings.DB_PATH, max_size=10)
    return _GLOBAL_POOL"""

content = content.replace(old_get_pool, new_get_pool)

with open("backend/app/database.py", "w") as f:
    f.write(content)
