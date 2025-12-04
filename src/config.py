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
HOST = _str("HOST", "127.0.0.1")
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
"""


