"""Central place for settings. Secrets come from the .env file, never from source code."""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=True)


def _clean(value):
    """Treat empty values and the placeholder text from .env.example as 'not set'."""
    if not value or value.strip().lower().startswith(("your_", "xxx")):
        return None
    return value.strip()


ANTHROPIC_API_KEY = _clean(os.getenv("ANTHROPIC_API_KEY"))
LANGFUSE_PUBLIC_KEY = _clean(os.getenv("LANGFUSE_PUBLIC_KEY"))
LANGFUSE_SECRET_KEY = _clean(os.getenv("LANGFUSE_SECRET_KEY"))
LANGFUSE_BASE_URL = os.getenv("LANGFUSE_BASE_URL") or "https://cloud.langfuse.com"
PROMPT_NAME = os.getenv("LANGFUSE_PROMPT_NAME") or "invoice-extractor"
BACKEND_URL = os.getenv("BACKEND_URL") or "http://localhost:8000"

# Label shown in the UI -> real model ID sent to Claude.
# (Langfuse infers cost from the model ID, so keep these as official model IDs.)
MODELS = {
    "Claude Haiku 4.5": "claude-haiku-4-5-20251001",
    "Claude Sonnet 4.6": "claude-sonnet-4-6",
}
DEFAULT_MODEL_LABEL = "Claude Haiku 4.5"

MAX_UPLOAD_MB = 10
