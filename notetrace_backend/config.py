import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = os.getenv("DATA_DIR", str(BASE_DIR / "data"))
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.getenv("DB_PATH", str(Path(DATA_DIR) / "notetrace.db"))
UPLOADS_PATH = os.getenv("UPLOADS_PATH", str(Path(DATA_DIR) / "uploads"))
BACKUPS_PATH = os.getenv("BACKUPS_PATH", str(Path(DATA_DIR) / "backups"))
STATIC_DIR = os.getenv("STATIC_DIR", str(BASE_DIR / "static"))

os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
os.makedirs(UPLOADS_PATH, exist_ok=True)
os.makedirs(BACKUPS_PATH, exist_ok=True)

# Server config
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
if BASE_URL and not BASE_URL.startswith("/"):
    BASE_URL = f"/{BASE_URL}"

# Auth config
JWT_SECRET = os.getenv("JWT_SECRET", "notetrace-dev-secret-change-in-production")
NODE_ENV = os.getenv("NODE_ENV", "production")
DEFAULT_SESSION_HOURS = 8760  # 1 year
MAX_SESSION_HOURS = int(os.getenv("MAX_SESSION_HOURS", "8760"))

# Rate limiting
API_RATE_LIMIT_PER_MIN = int(os.getenv("API_RATE_LIMIT_PER_MIN", "60"))
