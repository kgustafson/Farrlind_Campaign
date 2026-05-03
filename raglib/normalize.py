import re
from pathlib import Path

import yaml

from raglib.config import CLEAN, SESSIONS
from raglib.io_utils import read_text, write_text


# =============================================================================
# GLOBAL NORMALIZATION MAP
# Whisper garbles that appear across multiple sessions
# =============================================================================

NORMALIZATION_MAP = {
    # Party names
    "faven": "Faban",
    "faben": "Faban",
    "faban": "Faban",

    "rune": "Roon",
    "roon": "Roon",

    "bridget": "Brigit",
    "brigit": "Brigit",

    "makani": "Mikani",
    "mikani": "Mikani",
    "mithyra": "Mikani",
    "mithra": "Mikani",

    "corvinaus": "Corvinas",
    "corvinox": "Corvinas",
    "corvance": "Corvinas",
    "corvinus": "Corvinas",
    "corvinas": "Corvinas",

    "gildas": "Gildas",

    # Wells / places / items
    "syfie": "Saiffi",
    "scythe": "Saiffi",
    "saiffy": "Saiffi",
    "saiffi": "Saiffi",
    "couture": "Catur",
    "katoor": "Catur",
    "katur": "Catur",

    "balrog": "Balrog",

    "water skin": "waterskin",
    "wine skin": "wineskin",
    "bag of folding": "bag of holding",

    "mouth-a-lug": "Lightdelver",

    # Common spell garbles
    "cloud dagger": "Cloud of Daggers",
    "cloud daggers": "Cloud of Daggers",
    "clap daggers": "Cloud of Daggers",
}


# =============================================================================
# SESSION CONTEXT LOADER
# =============================================================================

def load_session_context(session_name: str) -> dict:
    """
    Loads session-specific normalization context from:
        <SESSIONS>/<session_name>_context.yaml

    Returns a normalization map (garble → correct) merged from:
        - new_npcs variants
        - new_locations variants
        - new_items variants
        - new_enemies variants

    Returns empty dict if no context file exists.
    """
    context_path = SESSIONS / f"{session_name}_context.yaml"

    if not context_path.exists():
        print(f"[normalize] No session context found at {context_path} — using global map only.")
        return {}

    with open(context_path, "r", encoding="utf-8") as f:
        ctx = yaml.safe_load(f)

    session_map = {}

    entity_sections = ["new_npcs", "new_locations", "new_items", "new_enemies"]

    for section in entity_sections:
        entries = ctx.get(section, {}) or {}
        for correct_name, details in entries.items():
            if not details:
                continue
            variants = details.get("variants", []) or []
            for variant in variants:
                session_map[variant.lower()] = correct_name

    print(f"[normalize] Loaded {len(session_map)} session-specific terms from {context_path.name}")
    return session_map


def load_known_garbles(session_name: str) -> dict:
    """
    Loads known_garbles section for flagging in output.
    These are unresolved garbles that need manual review.
    """
    context_path = SESSIONS / f"{session_name}_context.yaml"

    if not context_path.exists():
        return {}

    with open(context_path, "r", encoding="utf-8") as f:
        ctx = yaml.safe_load(f)

    return ctx.get("known_garbles", {}) or {}


def load_session_notes(session_name: str) -> str:
    """
    Returns freeform session notes for injection into summarize prompt.
    """
    context_path = SESSIONS / f"{session_name}_context.yaml"

    if not context_path.exists():
        return ""

    with open(context_path, "r", encoding="utf-8") as f:
        ctx = yaml.safe_load(f)

    return ctx.get("notes", "") or ""


# =============================================================================
# NORMALIZATION
# =============================================================================

def build_normalization_map(session_name: str) -> dict:
    """
    Merges global map with session-specific map.
    Session-specific entries take precedence.
    """
    session_map = load_session_context(session_name)
    merged = {**NORMALIZATION_MAP, **session_map}
    return merged


def normalize_text(text: str, norm_map: dict) -> str:
    normalized = text

    for wrong, right in norm_map.items():
        pattern = re.compile(rf"\b{re.escape(wrong)}\b", re.IGNORECASE)
        normalized = pattern.sub(right, normalized)

    return normalized


def flag_known_garbles(text: str, garbles: dict) -> str:
    """
    Wraps known unresolved garbles in [REVIEW: ...] markers
    so they're visible in the output and easy to grep for.
    """
    flagged = text

    for garble, note in garbles.items():
        if garble.lower() in flagged.lower():
            pattern = re.compile(rf"\b{re.escape(garble)}\b", re.IGNORECASE)
            flagged = pattern.sub(f"[REVIEW: {garble}]", flagged)

    return flagged


def normalize_key(key: str) -> str:
    key = key.lower().strip()

    if "dragon" in key and "breath" in key:
        return "dragon_breath"
    if "initiative" in key:
        return "combat_start"
    if "eldritch" in key:
        return "eldritch_blast"
    if "dagger" in key:
        return "cloud_of_daggers"

    return key


# =============================================================================
# MAIN
# =============================================================================

def normalize_session(session_name: str):
    classified_path = CLEAN / f"{session_name}_classified.md"
    filtered_path   = CLEAN / f"{session_name}_filtered.md"

    input_path  = classified_path if classified_path.exists() else filtered_path
    output_path = CLEAN / f"{session_name}_normalized.md"

    text     = read_text(input_path)
    norm_map = build_normalization_map(session_name)
    garbles  = load_known_garbles(session_name)

    normalized = normalize_text(text, norm_map)
    normalized = flag_known_garbles(normalized, garbles)

    write_text(output_path, normalized)

    print(f"[normalize] Normalized events written to: {output_path}")
    print(f"[normalize] Global terms: {len(NORMALIZATION_MAP)} | Session terms: {len(norm_map) - len(NORMALIZATION_MAP)}")

    if garbles:
        print(f"[normalize] Flagged {len(garbles)} known garble(s) for review — grep for [REVIEW: in output")
