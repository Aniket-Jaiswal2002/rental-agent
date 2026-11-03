"""Settings, read from the environment (.env is loaded first)."""
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
LISTINGS_PATH = ROOT / "data" / "listings.json"


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


class Settings:
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    groq_rpm: int = _int("GROQ_RPM", 20)
    groq_tpm: int = _int("GROQ_TPM", 7000)  # stay under the per-minute token cap (free tier: 8000)
    stt_model: str = os.getenv("STT_MODEL", "whisper-large-v3-turbo")
    stt_language: str = os.getenv("STT_LANGUAGE", "")  # empty = auto-detect (needed for Hinglish)
    groq_max_retries: int = _int("GROQ_MAX_RETRIES", 5)
    groq_max_wait_s: int = _int("GROQ_MAX_WAIT_S", 900)


settings = Settings()


def today() -> date:
    """Today's date; pinned via TODAY_OVERRIDE so relative dates are reproducible."""
    override = os.getenv("TODAY_OVERRIDE")
    return date.fromisoformat(override) if override else date.today()
