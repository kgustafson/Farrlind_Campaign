import re

from raglib.config import CLEAN
from raglib.io_utils import read_text, write_text


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

    "corvinaus": "Corvinas",
    "corvinox": "Corvinas",
    "corvance": "Corvinas",
    "corvinas": "Corvinas",

    "gildas": "Gildas",

    # Wells / places / items
    "syfie": "Saiffi",
    "scythe": "Saiffi",
    "saiffy": "Saiffi",
    "saiffi": "Saiffi",

    "balrog": "Balrog",

    "water skin": "waterskin",
    "wine skin": "wineskin",
    "bag of folding": "bag of holding",

    "Mouth-a-lug": "Lightdelver",
    "mouth-a-lug": "Lightdelver",

    # Common garbles
    "cloud dagger": "Cloud of Daggers",
    "cloud daggers": "Cloud of Daggers",
    "clap daggers": "Cloud of Daggers",
}


def normalize_text(text: str) -> str:
    normalized = text

    for wrong, right in NORMALIZATION_MAP.items():
        pattern = re.compile(rf"\b{re.escape(wrong)}\b", re.IGNORECASE)
        normalized = pattern.sub(right, normalized)

    return normalized

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


def normalize_session(session_name: str):
    input_path = CLEAN / f"{session_name}_filtered.md"
    output_path = CLEAN / f"{session_name}_normalized.md"

    text = read_text(input_path)
    normalized = normalize_text(text)

    write_text(output_path, normalized)

    print(f"Normalized events written to: {output_path}")
