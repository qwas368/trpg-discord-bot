import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
DEFAULT_AI_MODEL: str = os.getenv("DEFAULT_AI_MODEL", "claude-sonnet-4.6")
DEFAULT_REASONING_EFFORT: str | None = (os.getenv("DEFAULT_REASONING_EFFORT") or "").strip() or None
XAI_API_KEY: str = os.getenv("XAI_API_KEY", "")
DEFAULT_GROK_MODEL: str = os.getenv("DEFAULT_GROK_MODEL", "grok-4-1-fast-reasoning")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
HOSTS_DIR = PROJECT_ROOT / "hosts"
MODELS_DIR = PROJECT_ROOT / "models"
