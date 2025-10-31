-- ユーザー管理（オンボーディング情報含む）
CREATE TABLE IF NOT EXISTS users (
  user_id TEXT PRIMARY KEY,
  channel_id TEXT,
  join_date TIMESTAMPTZ DEFAULT now(),
  age INT,
  grade TEXT,
  self_level TEXT,
  goal TEXT,
  level_est INT DEFAULT 1,
  streak INT DEFAULT 0
);

-- 語彙マスター（CSV対応）
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

-- SRS（英単語）
CREATE TABLE IF NOT EXISTS srs_state (
  user_id TEXT NOT NULL,
  word_id INT NOT NULL REFERENCES words(word_id) ON DELETE CASCADE,
  next_review DATE,
  easiness NUMERIC DEFAULT 2.5,
  interval_days INT DEFAULT 0,
  consecutive_correct INT DEFAULT 0,
  last_result INT,
  PRIMARY KEY(user_id, word_id)
);

-- 英文解釈アイテム
CREATE TABLE IF NOT EXISTS svocm_items (
  item_id SERIAL PRIMARY KEY,
  sentence_en TEXT NOT NULL,
  pattern INT,
  level INT,
  tags TEXT[],
  source TEXT DEFAULT 'static',
  created_at TIMESTAMPTZ DEFAULT now()
);

-- SRS（英文解釈）
CREATE TABLE IF NOT EXISTS svocm_srs_state (
  user_id TEXT NOT NULL,
  item_id INT NOT NULL REFERENCES svocm_items(item_id) ON DELETE CASCADE,
  next_review DATE,
  easiness NUMERIC DEFAULT 2.5,
  interval_days INT DEFAULT 0,
  consecutive_correct INT DEFAULT 0,
  last_result INT,
  PRIMARY KEY(user_id, item_id)
);

-- 長文読解
CREATE TABLE IF NOT EXISTS reading_items (
  item_id SERIAL PRIMARY KEY,
  topic TEXT,
  level TEXT,
  skill_tag TEXT,
  passage_en TEXT NOT NULL,
  questions JSONB NOT NULL,
  answer_key JSONB NOT NULL,
  reasoning_span JSONB,
  source TEXT DEFAULT 'static',
  created_at TIMESTAMPTZ DEFAULT now()
);

-- 学習ログ（全モジュール共通）
CREATE TABLE IF NOT EXISTS study_logs (
  log_id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL,
  module TEXT NOT NULL,        -- 'vocab' | 'svocm' | 'reading'
  item_id INT,
  batch_id TEXT,
  ts TIMESTAMPTZ DEFAULT now(),
  result JSONB                 -- {known: bool, score: int, choice: 'A', ...}
);

-- セッションバッチ（復習用）
CREATE TABLE IF NOT EXISTS session_batches (
  user_id TEXT NOT NULL,
  module TEXT NOT NULL,
  batch_id TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY(user_id, module, batch_id)
);