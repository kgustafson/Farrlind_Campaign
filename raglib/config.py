from pathlib import Path
 
BASE   = Path("/Volumes/T7_WORK/AI_RAG/knowledge/Faban")
RAW    = BASE / "raw"
CLEAN  = BASE / "clean"
SESSIONS = BASE / "sessions"      # ← new
BASE2 = Path("/Volumes/T7_WORK/AI_RAG")  # ← new
 
# Ensure directories exist
for d in [RAW, CLEAN, SESSIONS]:
    d.mkdir(parents=True, exist_ok=True)

NOTES = BASE / "notes"

PROMPTS = BASE2 / "prompts"

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
