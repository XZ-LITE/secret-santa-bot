import os
import logging
from typing import List
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

def _parse_id_list(env_var: str, default: List[int]) -> List[int]:
    raw = os.getenv(env_var)
    if not raw:
        return default
    try:
        return [int(x.strip()) for x in raw.split(",") if x.strip()]
    except ValueError:
        logging.warning("Не удалось прочитать %s из .env, используются значения по умолчанию", env_var)
        return default

ADMIN_IDS: List[int] = _parse_id_list("ADMIN_IDS", [])
INITIAL_ALLOWED_USERS: List[int] = _parse_id_list(
    "INITIAL_ALLOWED_USERS", 
    ADMIN_IDS.copy()
)
DB_PATH: str = os.getenv("DB_PATH", "data/database.json")
BACKUP_DIR: str = os.getenv("BACKUP_DIR", "backups")
try:
    GIFT_BUDGET: int = int(os.getenv("GIFT_BUDGET", "1000").strip())
except (ValueError, TypeError):
    GIFT_BUDGET = 1000
