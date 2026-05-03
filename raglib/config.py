from pathlib import Path

# ===== Base Paths =====
BASE = Path("/Volumes/T7_WORK/AI_RAG")

KNOWLEDGE = BASE / "knowledge" / "Faban"
RAW = KNOWLEDGE / "raw"
CLEAN = KNOWLEDGE / "clean"
SUMMARIES = KNOWLEDGE / "summaries"
NOTES = KNOWLEDGE / "notes"

PROMPTS = BASE / "prompts"

# ===== Ollama =====
OLLAMA_URL = "http://localhost:11434"
MODEL = "llama3"  # use small model for extract; upgrade later for summarize

# ===== Chunking =====
CHUNK_MAX_CHARS = 3000     # safe size for local model
CHUNK_OVERLAP = 200        # helps preserve sentence continuity

# ===== Extraction =====
MIN_IMPORTANCE = "medium"  # filter threshold later

# ===== Utility =====
ENCODING = "utf-8"
