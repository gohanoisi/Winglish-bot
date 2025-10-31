# apply_schema.py
import asyncio
from db import init_db

asyncio.run(init_db())
print("✅ スキーマをDBに適用しました")