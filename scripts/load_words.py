# scripts/load_words.py
import csv
import asyncio
import asyncpg
from config import DATABASE_URL

async def load_words():
    # 接続プール作成
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    
    try:
        with open("data/All-words-modified_2025-10-29_08-31-22.csv", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            records = []
            for row in reader:
                # カンマ区切りをリストに（空なら None）
                syn = row["Synonym"].split(", ") if row["Synonym"].strip() else None
                ant = row["Antonym"].split(", ") if row["Antonym"].strip() else None
                der = row["Derived word"].split(", ") if row["Derived word"].strip() else None
                pos = row["part of speech"].split(", ")[0] if row["part of speech"].strip() else None

                records.append((
                    row["word"],
                    row["japanese"],
                    pos,
                    int(row["level"]) if row["level"].isdigit() else 1,
                    syn,
                    ant,
                    der,
                    row["example"],
                    row["ex_japa"]
                ))

        # 一括INSERT（効率的）
        async with pool.acquire() as con:
            await con.executemany("""
                INSERT INTO words(word, jp, pos, level, synonyms, antonyms, derived, example_en, example_ja)
                VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (word) DO NOTHING
            """, records)

        print(f"✅ {len(records)} 件の単語データをDBにロードしました（重複はスキップ）")

    except Exception as e:
        print(f"❌ エラー: {e}")
        raise
    finally:
        await pool.close()

if __name__ == "__main__":
    asyncio.run(load_words())