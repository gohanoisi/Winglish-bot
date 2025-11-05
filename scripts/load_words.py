# scripts/load_words.py  (schema-aligned, robust)
import asyncio, os, csv, asyncpg, sys, traceback
from dotenv import load_dotenv

load_dotenv()
DSN = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
CSV_PATH = os.getenv("WORDS_CSV_PATH") or "data/All-words-modified_2025-10-29_08-31-22.csv"
LIMIT = int(os.getenv("WORDS_LIMIT") or 0)   # テスト投入数（0で全件）

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS words (
  word_id SERIAL PRIMARY KEY,
  word TEXT NOT NULL UNIQUE,
  jp TEXT NOT NULL,
  pos TEXT,
  cefr TEXT,
  level INT,
  topic_tags TEXT[],
  synonyms TEXT[],
  antonyms TEXT[],
  derived TEXT[],
  example_en TEXT,
  example_ja TEXT
);
-- 念のため指数
CREATE UNIQUE INDEX IF NOT EXISTS ux_words_word ON words(word);
"""

UPSERT_SQL = """
INSERT INTO words(word, jp, pos, cefr, level, topic_tags, synonyms, antonyms, derived, example_en, example_ja)
VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
ON CONFLICT (word) DO UPDATE
SET jp=EXCLUDED.jp,
    pos=EXCLUDED.pos,
    cefr=EXCLUDED.cefr,
    level=EXCLUDED.level,
    topic_tags=EXCLUDED.topic_tags,
    synonyms=EXCLUDED.synonyms,
    antonyms=EXCLUDED.antonyms,
    derived=EXCLUDED.derived,
    example_en=EXCLUDED.example_en,
    example_ja=EXCLUDED.example_ja;
"""

def to_array(s: str):
    """
    CSVのカンマ区切りを TEXT[] に変換。
    全角カンマや余計な空白もケア。空なら None（=NULL）。
    """
    if not s:
        return None
    # 全角→半角
    s = s.replace("，", ",")
    parts = [p.strip() for p in s.split(",")]
    parts = [p for p in parts if p]  # 空要素除去
    return parts or None

def row_to_params(row: dict):
    word = (row.get("word") or "").strip()
    jp   = (row.get("japanese") or "").strip()
    pos  = (row.get("part of speech") or "").strip()

    level_raw = (row.get("level") or "").strip()
    try:
        level = int(level_raw) if level_raw != "" else None
    except:
        level = None

    example_en = (row.get("example") or "").strip()
    example_ja = (row.get("ex_japa") or "").strip()

    synonyms = to_array((row.get("Synonym") or "").strip())
    antonyms = to_array((row.get("Antonym") or "").strip())
    derived  = to_array((row.get("Derived word") or "").strip())

    cefr = None         # CSVに無いのでNULL
    topic_tags = None   # CSVに無いのでNULL

    # word/jp は NOT NULL。空ならスキップ対象に。
    return (word, jp, pos, cefr, level, topic_tags, synonyms, antonyms, derived, example_en, example_ja)

async def main():
    if not DSN:
        print("❌ DATABASE_PUBLIC_URL / DATABASE_URL が未設定です。", file=sys.stderr)
        sys.exit(1)

    print("DB =", DSN[:80] + "...")
    print("CSV =", CSV_PATH)

    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=5)
    async with pool.acquire() as con:
        await con.execute(SCHEMA_SQL)

    ok = ng = 0
    first_error = None
    first_error_row = None

    try:
        with open(CSV_PATH, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader, start=1):
                if LIMIT and idx > LIMIT:
                    break

                params = row_to_params(row)
                word, jp = params[0], params[1]
                if not word or not jp:  # NOT NULLカラムの欠落はスキップ
                    ng += 1
                    if first_error is None:
                        first_error = ValueError("required column empty (word/jp)")
                        first_error_row = (idx, dict(row))
                    continue

                try:
                    async with pool.acquire() as con:
                        await con.execute(UPSERT_SQL, *params)
                    ok += 1
                except Exception as e:
                    ng += 1
                    if first_error is None:
                        first_error = e
                        first_error_row = (idx, dict(row))

                if idx % 1000 == 0:
                    print(f"...progress: read={idx}, OK={ok}, NG={ng}")

    finally:
        await pool.close()

    print(f"Import done: OK={ok}, NG={ng}")
    if first_error:
        print("---- First error detail ----", file=sys.stderr)
        print(f"Row idx: {first_error_row[0]}", file=sys.stderr)
        compact = {k: (str(v)[:200] if v is not None else v) for k, v in first_error_row[1].items()}
        print(f"Row data: {compact}", file=sys.stderr)
        print("Exception:", repr(first_error), file=sys.stderr)
        traceback.print_exception(type(first_error), first_error, first_error.__traceback__)
        # スキップしつつ続行したので exit 2 にしておく
        sys.exit(2)

if __name__ == "__main__":
    asyncio.run(main())
