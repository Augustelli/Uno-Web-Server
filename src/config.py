# python
from pathlib import Path
import os
import sys
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
MAX_PLAYERS = _int("MAX_PLAYERS", 2)
TURN_TIMEOUT = _int("TURN_TIMEOUT", 120)
HOST = _str("HOST", "127.0.0.1")
CARDS_NUMBER = _int("CARDS_NUMBER", 2)
LOG_DB_DSN = _str("LOG_DB_DSN", "dbname=game_db user=postgres password=Sup3rSecret0 host=localhost port=5432")
DATABASE_URL = _str("DATABASE_URL", LOG_DB_DSN)
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

def ensure_logs_table(dsn: str | None = None) -> None:
    """
    Create the logs table if it does not exist. Safe: prints errors and returns if DB unreachable
    or psycopg not installed. This is called at import time if a DSN is present.
    """
    dsn = dsn or DATABASE_URL or LOG_DB_DSN
    if not dsn:
        return
    try:
        import psycopg
    except Exception as e:
        print(f"Warning: psycopg is not available, skipping logs table creation: {e}", file=sys.stderr)
        return

    try:
        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(DB_TABLE_CREATION_QUERY)
            conn.commit()
    except Exception as e:
        print(f"Warning: could not create logs table: {e}", file=sys.stderr)

# attempt to create table automatically on program start if a DSN is configured
if LOG_DB_DSN or DATABASE_URL:
    try:
        ensure_logs_table(LOG_DB_DSN or DATABASE_URL)
    except Exception:
        # keep import-time side effects safe: swallow unexpected exceptions
        pass