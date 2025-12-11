import os
from pathlib import Path

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / "../.env"
if env_path.exists():
    load_dotenv(env_path)


def _int(name, default):
    val = os.environ.get(name)
    return int(val) if val is not None and val != "" else default


def _str(name, default):
    return os.environ.get(name, default)

DB_DSN = _str("DB_DSN", "dbname=game_db user=postgres password=Sup3rSecret0 host=localhost port=5432")
SERVER_PORT = _int("SERVER_PORT", 8899)
