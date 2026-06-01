import os
from pathlib import Path

from raglib.campaign import active_campaign_name, campaign_root, clean_dir, notes_dir, raw_dir, sessions_dir, ensure_campaign_dirs

BASE2 = Path(__file__).resolve().parents[1]
CAMPAIGN_NAME = active_campaign_name()
BASE = campaign_root(CAMPAIGN_NAME)
RAW = raw_dir(CAMPAIGN_NAME)
CLEAN = clean_dir(CAMPAIGN_NAME)
SESSIONS = sessions_dir(CAMPAIGN_NAME)

ensure_campaign_dirs(CAMPAIGN_NAME)

NOTES = notes_dir(CAMPAIGN_NAME)

PROMPTS = BASE2 / "prompts"

# ===== Ollama =====
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
MODEL = "llama3"  # use small model for extract; upgrade later for summarize

# ===== Chunking =====
CHUNK_MAX_CHARS = 3000     # safe size for local model
CHUNK_OVERLAP = 200        # helps preserve sentence continuity

# ===== Extraction =====
MIN_IMPORTANCE = "medium"  # filter threshold later

# ===== Utility =====
ENCODING = "utf-8"
