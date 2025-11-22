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
MAX_PLAYERS = _int("MAX_PLAYERS", 2)
TURN_TIMEOUT = _int("TURN_TIMEOUT", 120)
HOST = _str("HOST", "127.0.0.1")
CARDS_NUMBER = _int("CARDS_NUMBER", 2)