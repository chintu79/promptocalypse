import asyncio
import aiosqlite

class AiosqlitePool:
    def __init__(self, db_path, max_size=10, init_func=None):
        self.db_path = db_path
        self.max_size = max_size
        self.init_func = init_func
        self._pool = asyncio.Queue(maxsize=max_size)
        self._created = 0
        self._lock = asyncio.Lock()

    async def acquire(self):
        # If pool is empty but we can create more, create one
        async with self._lock:
            if self._pool.empty() and self._created < self.max_size:
                conn = await aiosqlite.connect(self.db_path)
                if self.init_func:
                    await self.init_func(conn)
                self._created += 1
                return conn
        # Wait for a connection to become available
        return await self._pool.get()

    async def release(self, conn):
        await self._pool.put(conn)

    async def close_all(self):
        while not self._pool.empty():
            conn = await self._pool.get()
            await conn.close()

