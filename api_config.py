from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

API_DIR = Path(__file__).resolve().parent
STORAGE_DIR = API_DIR / "storage"
UPLOAD_DIR = STORAGE_DIR / "uploads"
GENERATED_DIR = STORAGE_DIR / "generated"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_SIZE_MB = 25
ALLOWED_EXTENSIONS = {".pdf"}
