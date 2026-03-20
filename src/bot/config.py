import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
DEFAULT_AI_MODEL: str = os.getenv("DEFAULT_AI_MODEL", "claude-sonnet-4.6")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
HOSTS_DIR = PROJECT_ROOT / "hosts"
MODELS_DIR = PROJECT_ROOT / "models"
