import asyncpg
from config import DATABASE_URL

_pool = None

async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    return _pool

async def init_db():
    pool = await get_pool()
    with open("sql/schema.sql", "r", encoding="utf-8") as f:
        schema = f.read()
    async with pool.acquire() as con:
        await con.execute(schema)
