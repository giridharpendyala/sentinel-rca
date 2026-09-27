from pathlib import Path
from dotenv import load_dotenv

# Auto-load project .env file on package import
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")
