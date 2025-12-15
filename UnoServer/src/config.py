from pathlib import Path
import os
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / "../.env"
if env_path.exists():
    load_dotenv(env_path)


def _int(name, default):
    val = os.environ.get(name)
    return int(val) if val is not None and val != "" else default


def _str(name, default):
    return os.environ.get(name, default)


PORT = _int("PORT", 8000)
MIN_PLAYERS = _int("MIN_PLAYERS", 2)
MAX_PLAYERS = _int("MAX_PLAYERS", 10)
TURN_TIMEOUT = _int("TURN_TIMEOUT", 120)
HOST = _str("HOST", "0.0.0.0")
CARDS_NUMBER = _int("CARDS_NUMBER", 2)
LOG_DB_DSN = _str("LOG_DB_DSN", "dbname=game_db user=postgres password=Sup3rSecret0 host=localhost port=5432")
DB_TABLE_CREATION_QUERY = """
CREATE TABLE IF NOT EXISTS logs (
  id bigserial PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  level text NOT NULL,
  logger_name text,
  process_name text,
  thread_name text,
  message text,
  game_id text,
  player_id text,
  extra jsonb
);
CREATE INDEX IF NOT EXISTS idx_logs_created_at ON logs (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_logs_created_at
    ON logs (created_at DESC);

CREATE TABLE IF NOT EXISTS games (
    id           bigserial PRIMARY KEY,
    game_id      text UNIQUE NOT NULL,       -- mismo id que usa GameManager
    started_at   timestamptz NOT NULL DEFAULT now(),
    ended_at     timestamptz,
    max_players  integer    NOT NULL,
    winner_player integer,
    total_turns  integer    NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS game_events (
    id         bigserial PRIMARY KEY,
    game_id    text NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    ts         timestamptz NOT NULL DEFAULT now(),
    player_id  integer,
    player_name text,
    event_type text NOT NULL,   -- 'start', 'play', 'draw', 'pass', 'timeout', 'end'
    card       text,
    extra      jsonb
);

CREATE INDEX IF NOT EXISTS idx_game_events_game_ts
    ON game_events (game_id, ts);

CREATE TABLE IF NOT EXISTS player_stats (
    player_name        text PRIMARY KEY,
    games_played       integer NOT NULL DEFAULT 0,
    games_won          integer NOT NULL DEFAULT 0,
    total_turns        integer NOT NULL DEFAULT 0,
    total_cards_played integer NOT NULL DEFAULT 0
);
"""
VLLM_MODEL_NAME = _str("VLLM_MODEL_NAME", "meta-llama/Llama-2-7b-chat-hf")
VLLM_CHAT_URL = _str("VLLM_CHAT_URL", "https://huggingface.co/meta-llama/Llama-2-7b-chat-hf/resolve/main/")

