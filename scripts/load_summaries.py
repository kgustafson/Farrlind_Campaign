import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from raglib.config import CLEAN, BASE2
from raglib.summarize import (
    diary_path,
    format_physical_date,
    load_session_metadata,
    optional_read,
    parse_diary_in_game_dates,
    parse_diary_physical_date,
    parse_diary_title,
)


OUT_DIR = BASE2 / "farrlind" / "out"
OUT_SQL = OUT_DIR / "load_summaries.sql"
TRAVEL_FACTS_PATH = BASE2 / "knowledge" / "Faban" / "travel.yaml"
SONG_PROMPTS_PATH = BASE2 / "knowledge" / "Faban" / "songbook" / "prompts.md"
CANON_DECISIONS_PATH = BASE2 / "knowledge" / "Faban" / "canon_decisions.yaml"
REVIEWS_DIR = BASE2 / "knowledge" / "Faban" / "reviews"

KNOWN_LOCATIONS = [
    "Bentrios",
    "Alexander's Inn",
    "Thataways",
    "Fey Woods",
    "Road to Fey Woods",
    "Paramon",
    "Balrog",
    "Coast near Catur",
    "Catur",
    "Gale Monastery",
    "Hanedal Island",
]

TRAVEL_LOCATION_ALIASES = {
    "Alexander's Inn": ["alexander's inn"],
    "Bentrios": ["bentrios"],
    "Thataways": ["thataways", "thisaway"],
    "Fey Woods": ["fey woods", "fey wilds", "fey wild", "feywild", "outer fey woods"],
    "Road to Fey Woods": ["road to fey woods", "road to the fey woods", "near the fey wilds"],
    "Paramon": ["paramon"],
    "Balrog": ["balrog"],
    "Catur": ["catur", "sunken city", "catur shoreline"],
    "Coast near Catur": ["coast near catur", "catur shoreline", "shoreline near catur"],
    "Gale Monastery": ["gale monastery"],
    "Hanedal Island": ["hanedal", "haunidal", "hanedal island"],
}

CANON_NPCS = [
    {
        "name": "Baron Wells",
        "first_seen_session": 1,
        "location": "Bentrios",
        "description": "Mayor of Bentrios whose infernal contract with Salazar led to the city's Age of Discovery reversion.",
        "status": "alive",
    },
    {
        "name": "Father Joseph",
        "first_seen_session": 2,
        "location": "Bentrios",
        "description": "Priest or scholar of Siath in Bentrios who advises the party on demonic artifacts, Rage, Salazar, the Wells of Magic, the Cataclysm, and the search for Urgan's Axe.",
        "status": "alive",
    },
    {
        "name": "Oak",
        "first_seen_session": 2,
        "location": "Fey Woods",
        "description": "Dryad of the outer Fey Woods who warns the party that fey are hostile to outsiders, says she is bound by a vow of silence about Urgan's Axe, and directs them toward a centaur lake.",
        "status": "alive",
    },
    {
        "name": "Ardema",
        "first_seen_session": 6,
        "location": "Thataways",
        "description": "Hostile caster fought during the defense of the Tree and the Well of Magic.",
        "status": "fled",
    },
    {
        "name": "Claris",
        "first_seen_session": 6,
        "location": "Thataways",
        "description": "Librarian under the tree in Thataways.",
        "status": "alive",
    },
    {
        "name": "Leprechaun thief",
        "first_seen_session": 5,
        "location": "Thataways",
        "description": "Unnamed leprechaun who followed the party near the Fey forest and tried to steal Urgan's Axe.",
        "status": "fled",
        "is_named": False,
    },
    {
        "name": "Satyr violinist",
        "first_seen_session": 4,
        "location": "Thataways",
        "description": "Unnamed satyr violinist in Thataways who told Faban Urgan's Axe was buried under the tree and later blessed Faban's fiddle with magical runes.",
        "status": "alive",
        "is_named": False,
    },
    {
        "name": "Birdfolk wizard",
        "first_seen_session": 4,
        "location": "Thataways",
        "description": "Unnamed birdfolk wizard and tree sage in Thataways who keeps the library, maintains defensive magic, explains infernal item marks, and escorts the party to the sage council.",
        "status": "alive",
        "is_named": False,
    },
    {
        "name": "Zakana",
        "first_seen_session": 8,
        "location": "Spore Sanctuary",
        "description": "Giant firbolg in the Spore Sanctuary who helped the party leave and provided healing mushrooms.",
        "status": "alive",
    },
    {
        "name": "Aracokin",
        "first_seen_session": 9,
        "location": "Bellemaine",
        "description": "Quartermaster who offered to accompany the party to survey the site.",
        "status": "alive",
    },
    {
        "name": "Thompson",
        "first_seen_session": 9,
        "location": "Bellemaine",
        "description": "Naturalist quartermaster who provided information about Jen/Jennifer and the druid commune.",
        "status": "alive",
    },
    {
        "name": "Rebar",
        "first_seen_session": 9,
        "location": "Bellemaine",
        "description": "Half-giant who arm-wrestled Roon.",
        "status": "alive",
    },
    {
        "name": "General Chris",
        "first_seen_session": 10,
        "location": "Bellemaine",
        "description": "General who spoke with the party after the Bellemaine construct and Dao battle.",
        "status": "alive",
    },
    {
        "name": "Richard",
        "first_seen_session": 10,
        "location": "Road to Archaeological Dig Site",
        "description": "Caravan contact when the party began the journey north.",
        "status": "alive",
    },
    {
        "name": "Teddy",
        "first_seen_session": 10,
        "location": "Road to Archaeological Dig Site",
        "description": "Caravan member excited that the party joined the group.",
        "status": "alive",
    },
    {
        "name": "Sam",
        "first_seen_session": 11,
        "location": "Road to Archaeological Dig Site",
        "description": "Suspicious man in a rickety carriage; necrotic agent who infiltrated the caravan.",
        "status": "dead",
    },
    {
        "name": "Cole",
        "first_seen_session": 13,
        "location": "Mountain Road",
        "description": "Traveler who appeared with a magical deck of cards.",
        "status": "alive",
    },
    {
        "name": "Jennifer",
        "alias": "Jennifer Wilbreta",
        "first_seen_session": 1,
        "location": "Druid Retreat",
        "description": "Jennifer Wilbreta, ancient pale elf of the Fey, elvish archer, and druid; first mentioned in Faban's ballad as Urgan's bride who buried his axe, later confirmed the Wells and the missing Wand of Wells.",
        "status": "alive",
    },
    {
        "name": "Zerzer",
        "first_seen_session": 14,
        "location": "Druid Retreat",
        "description": "Druid Retreat resident seeking a plant that could help the party breathe beneath the sea near Catur.",
        "status": "alive",
    },
    {
        "name": "Ordor",
        "first_seen_session": 14,
        "location": "Paramon",
        "description": "Entity or person at Paramon's Well who warned danger was imminent.",
        "status": "unknown",
    },
    {
        "name": "Biha-Bibir",
        "first_seen_session": 14,
        "location": "Paramon",
        "description": "Seaweed and living-current entity fought at Paramon.",
        "status": "dead",
    },
    {
        "name": "Black-furred tabaxi",
        "first_seen_session": 15,
        "location": "Paramon",
        "description": "Tabaxi questioned by Faban who spoke of ancient dragonlands, Tiamat, demons, and the Cataclysm.",
        "status": "fled",
    },
    {
        "name": "Sapphire-eyed stranger",
        "first_seen_session": 15,
        "location": "Paramon",
        "description": "Stranger who spoke with Gildas in a tavern.",
        "status": "unknown",
    },
    {
        "name": "Iron Paw",
        "first_seen_session": 15,
        "location": "Paramon",
        "description": "Head priest of the Temple of Namaloa in Paramon; revealed as false or hostile and defeated by the party.",
        "status": "dead",
    },
    {
        "name": "Erling Rostad",
        "first_seen_session": 17,
        "location": "Paramon",
        "description": "Survivor who spoke of primordial forces and the Cataclysm as over-release.",
        "status": "alive",
    },
    {
        "name": "Apothecary",
        "first_seen_session": 17,
        "location": "Paramon",
        "description": "Apothecary who provided twenty potions of borrowed gills and temporary courage.",
        "status": "alive",
    },
    {
        "name": "Forgebottom",
        "first_seen_session": 17,
        "location": "Balrog",
        "description": "Balrog listener who faltered at Faban's song about the Wells, Cataclysm, and unrestrained power.",
        "status": "alive",
    },
    {
        "name": "Lightdelver",
        "first_seen_session": 18,
        "location": "Balrog",
        "description": "Dwarven wizard rescued from a falling tower in Balrog.",
        "status": "alive",
    },
    {
        "name": "Sleeping dwarven guard",
        "first_seen_session": 18,
        "location": "Balrog",
        "description": "Dwarven guard awakened in the forge and mines of Balrog.",
        "status": "alive",
    },
    {
        "name": "Saiffi",
        "first_seen_session": 18,
        "location": "Balrog",
        "description": "Well bound to truth in Balrog; described as the weakest but perhaps wisest and most informed Well.",
        "status": "alive",
    },
    {
        "name": "Orsydon",
        "first_seen_session": 18,
        "location": "Balrog",
        "description": "Dragon summoned by cultists in Balrog and defeated by the party.",
        "status": "dead",
    },
    {
        "name": "Alistair",
        "first_seen_session": 20,
        "location": "Coast near Catur",
        "description": "Coastal boat contact who gave the party a boat near Catur.",
        "status": "alive",
    },
]

KNOWN_NPCS = [npc["name"] for npc in CANON_NPCS]

CANON_ENEMIES = [
    {
        "name": "Salazar",
        "enemy_type": "demon_lord",
        "first_encountered_session": 1,
        "description": "Demon Lord of Lightning who threatened Baron Wells in Bentrios Tower, brought an unnatural storm down on Bentrios, and demanded the final item tied to Urgan's Axe.",
        "status": "alive",
        "threat_level": "existential",
    },
    {
        "name": "Fey witch",
        "enemy_type": "fey_witch",
        "first_encountered_session": 3,
        "description": "Unnamed fey witch in the Fey Woods who summoned goblins, nearly killed Faban and Roon, and left behind a satchel containing souls and an ancient necromantic tome.",
        "status": "dead",
        "threat_level": "moderate",
    },
]

KNOWN_ENEMIES = [
    "Orsydon",
    "Ardema",
    "Iron Paw",
] + [enemy["name"] for enemy in CANON_ENEMIES]

KNOWN_ARTIFACTS = [
    "The Black Blade",
    "Grimoire Mutandi",
    "Urgan's Axe",
    "Infernal Orb of Rage",
    "Wand of Wells",
    "Gildas' Enhanced Staff",
    "Mikani's Breathing Cap",
    "Brigit's Upgraded Bow",
    "Corvinas' Flame Blade",
    "Roon's Shield",
]

SONG_TITLE_TO_NUMBER = {
    "the off-key dragon": 1,
    "sally and the good day": 2,
    "roll the barrel": 3,
    "the one-legged lass": 4,
    "the one legged lass": 4,
    "the contract of baron wells": 5,
    "the contract of baron welles": 5,
    "the lord who bought his battles": 6,
    "the lord who hires heroes": 6,
    "the braggart baron who bought his battles": 6,
    "the fool who outsang the devil": 7,
    "flight of the fairies": 8,
    "the flight of the fairies": 8,
    "don't step in the fairy ring": 9,
    "don’t step in the fairy ring": 9,
    "the stars and the centaurs": 10,
    "urgan wyrmbane": 11,
    "the day we called it victory": 12,
    "the defense of the watery dunes": 13,
    "the defense of the watery deep": 13,
    "the fallen few": 14,
    "the fallen few at devilspawn valley": 14,
    "the lost miners of karadum": 15,
    "the battle of flintrock": 16,
    "the ballad of flintrock": 16,
    "the fate of the emerald eel": 17,
    "ranger rick and his mighty stick": 18,
    "mihira's rise": 19,
    "mihira’s rise": 19,
    "mihira's rise (the ballad of justice untamed)": 19,
    "mihira’s rise (the ballad of justice untamed)": 19,
    "the ballad of mortalkind": 20,
    "the keeper of the quiet key": 21,
    "keeper of the quiet key": 21,
    "silent queen of whisper vale": 22,
    "the silent queen of whisper vale": 22,
    "the hand that did not open": 23,
    "the road we walk together": 24,
    "the long road home": 25,
    "the lantern in your window": 26,
    "the lantern in the window": 26,
}

SONG_TITLES = {
    1: "The Off-Key Dragon",
    2: "Sally and the Good Day",
    3: "Roll the Barrel",
    4: "The One-Legged Lass",
    5: "The Contract of Baron Wells",
    6: "The Lord Who Bought His Battles",
    7: "The Fool Who Outsang the Devil",
    8: "Flight of the Fairies",
    9: "Don't Step in the Fairy Ring",
    10: "The Stars and the Centaurs",
    11: "Urgan Wyrmbane",
    12: "The Day We Called It Victory",
    13: "The Defense of the Watery Dunes",
    14: "The Fallen Few at Devilspawn Valley",
    15: "The Lost Miners of Karadum",
    16: "The Battle of Flintrock",
    17: "The Fate of the Emerald Eel",
    18: "Ranger Rick and his Mighty Stick",
    19: "Mihira's Rise (The Ballad of Justice Untamed)",
    20: "The Ballad of Mortalkind",
    21: "The Keeper of the Quiet Key",
    22: "Silent Queen of Whisper Vale",
    23: "The Hand That Did Not Open",
    24: "The Road We Walk Together",
    25: "The Long Road Home",
    26: "The Lantern in Your Window",
}

PROMPT_FIELDS = {"title", "alias", "prompt", "tempo", "meter", "key", "instrumentation"}


def sql_quote(value):
    if value is None or value == "":
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def normalize_lookup(value: str) -> str:
    return " ".join(value.replace("’", "'").split()).strip().lower()


def parse_session_number(path: Path) -> int:
    match = re.search(r"session(\d+)_summary\.md$", path.name)
    if not match:
        raise ValueError(f"Could not parse session number from {path}")
    return int(match.group(1))


def parse_session_ref(value) -> int:
    if isinstance(value, int):
        return value
    match = re.search(r"(\d+)$", str(value))
    if not match:
        raise ValueError(f"Could not parse session reference: {value!r}")
    return int(match.group(1))


def strip_bullet(line: str) -> str:
    return re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()


def clean_prompt_value(value: str) -> str:
    value = value.strip()
    value = re.sub(r"\*\*(.+?)\*\*", r"\1", value)
    value = re.sub(r"(?m)^\s*-\s+", "", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def parse_song_prompts() -> tuple[list[dict], list[str]]:
    if not SONG_PROMPTS_PATH.exists():
        return [], []

    entries = []
    warnings = []
    current = None
    current_field = None

    def flush():
        nonlocal current
        if not current:
            return

        title = clean_prompt_value(current.get("title", ""))
        prompt = clean_prompt_value(current.get("prompt", ""))
        if not title and not prompt:
            current = None
            return
        if not title:
            warnings.append("Skipped prompt block with no title.")
            current = None
            return
        if not prompt:
            warnings.append(f"Skipped {title}: prompt is blank.")
            current = None
            return

        song_number = SONG_TITLE_TO_NUMBER.get(normalize_lookup(title))
        if song_number is None:
            warnings.append(f"Skipped {title}: no matching song number.")
            current = None
            return

        entry = {
            "song_number": song_number,
            "title": title,
            "prompt": prompt,
            "tempo": clean_prompt_value(current.get("tempo", "")),
            "meter": clean_prompt_value(current.get("meter", "")),
            "key": clean_prompt_value(current.get("key", "")),
            "instrumentation": clean_prompt_value(current.get("instrumentation", "")),
        }

        if not entry["tempo"]:
            match = re.search(r"(?im)\btempo:\s*([^\n]+)", prompt)
            if match:
                entry["tempo"] = clean_prompt_value(match.group(1))
        if not entry["meter"]:
            match = re.search(r"(?im)\bmeter:\s*([^\n]+)", prompt)
            if match:
                entry["meter"] = clean_prompt_value(match.group(1))
        if not entry["key"]:
            match = re.search(r"(?im)\bkey:\s*([^\n]+)", prompt)
            if match:
                entry["key"] = clean_prompt_value(match.group(1))

        entries.append(entry)
        current = None

    for line in SONG_PROMPTS_PATH.read_text(encoding="utf-8").splitlines():
        field_match = re.match(r"^\s*([A-Za-z_]+)\s*:\s*(.*)$", line)
        if field_match and field_match.group(1).lower() in PROMPT_FIELDS:
            field = field_match.group(1).lower()
            value = field_match.group(2)
            if field == "title":
                flush()
                current = {"title": value}
            else:
                if current is None:
                    current = {}
                current[field] = value
            current_field = field
            continue

        if current is not None and current_field in {"prompt", "instrumentation", "alias"}:
            current[current_field] = "\n".join(
                part for part in [current.get(current_field, ""), line] if part != ""
            )

    flush()

    by_number = {}
    for entry in entries:
        previous = by_number.get(entry["song_number"])
        if previous:
            warnings.append(
                f"Duplicate prompt for song {entry['song_number']}: "
                f"using {entry['title']} over {previous['title']}."
            )
        by_number[entry["song_number"]] = entry

    return [by_number[number] for number in sorted(by_number)], warnings


def parse_summary(path: Path) -> dict:
    text = path.read_text(encoding="utf-8").strip()
    session_number = parse_session_number(path)
    session_name = f"session{session_number:02d}"
    diary = optional_read(diary_path(session_name))
    metadata = load_session_metadata(session_name)

    physical_date = (
        field_value(text, "Physical Session Date")
        or format_physical_date(metadata)
        or parse_diary_physical_date(diary)
    )
    in_game_date = (
        field_value(text, "In-Game Date")
        or ", ".join(parse_diary_in_game_dates(diary))
    )
    title = (
        field_value(text, "Title")
        or parse_diary_title(diary)
        or f"Session {session_number:02d}"
    )

    key_events = parse_key_events(text)
    summary = parse_prose_summary(text)

    return {
        "session_number": session_number,
        "physical_date": physical_date,
        "in_game_date": in_game_date,
        "title": title,
        "summary": summary,
        "events": key_events,
        "source_path": str(path),
        "location": detect_location(f"{title}\n{summary}\n" + "\n".join(key_events)),
    }


def field_value(text: str, field: str) -> str:
    match = re.search(rf"(?im)^{re.escape(field)}:\s*(.+?)\s*$", text)
    return match.group(1).strip() if match else ""


def parse_key_events(text: str) -> list[str]:
    match = re.search(r"(?ims)^Key Events:\s*(.*?)(?:^\w[\w ]+:\s*|\Z)", text)
    if not match:
        return []

    events = []
    for line in match.group(1).splitlines():
        event = strip_bullet(line)
        if event:
            events.append(event)

    return events


def parse_prose_summary(text: str) -> str:
    body = re.sub(r"(?im)^Session Summary:\s*", "", text).strip()
    body = re.sub(r"(?im)^Physical Session Date:.*$", "", body)
    body = re.sub(r"(?im)^In-Game Date:.*$", "", body)
    body = re.sub(r"(?im)^Title:.*$", "", body)
    body = re.split(r"(?im)^Key Events:\s*$", body)[0]
    return body.strip()


def detect_location(text: str) -> str:
    low = text.lower()
    for location in KNOWN_LOCATIONS:
        aliases = TRAVEL_LOCATION_ALIASES.get(location, [location])
        if any(alias.lower() in low for alias in aliases):
            return location
    return ""


def location_mentions(text: str) -> list[str]:
    low = text.lower()
    mentions = []

    for location in KNOWN_LOCATIONS:
        aliases = TRAVEL_LOCATION_ALIASES.get(location, [location])
        if any(alias.lower() in low for alias in aliases):
            mentions.append(location)

    return mentions


def detect_travel_method(text: str) -> str:
    low = text.lower()

    if any(term in low for term in ["portal", "transported", "teleport", "dimension door"]):
        return "portal"
    if re.search(r"\b(boat|ship|vessel|sailing)\b", low):
        return "ship"
    if re.search(r"\b(carriage|wagon|cart)\b", low):
        return "wagon"
    if re.search(r"\b(horse|mount|mounts)\b", low):
        return "horse"
    if re.search(r"\b(swim|underwater)\b", low) or any(term in low for term in ["beneath the sea", "descend into the sunken city"]):
        return "swim"

    return "foot"


def detect_duration_days(text: str):
    low = text.lower()
    number_words = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
    }

    match = re.search(r"\b(\d+)\s+days?\b", low)
    if match:
        return int(match.group(1))

    for word, value in number_words.items():
        if re.search(rf"\b{word}\s+days?\b", low):
            return value

    return None


def extract_travel_logs(summary: dict) -> list[dict]:
    logs = []
    pending_from = ""
    pending_duration = None
    pending_notes = []

    for event in summary["events"]:
        low = event.lower()
        if not any(term in low for term in [
            "travel", "depart", "left", "arrived", "journey", "returned",
            "reached", "headed", "set out", "went to", "transported",
        ]):
            continue

        from_location = ""
        to_location = ""

        explicit_match = re.search(
            r"\bfrom\s+([A-Za-z' ]+?)\s+to\s+([A-Za-z' ]+?)(?:,|\.|$)",
            event,
            re.IGNORECASE,
        )
        if explicit_match:
            from_location = detect_location(explicit_match.group(1))
            to_location = detect_location(explicit_match.group(2))

        depart_match = re.search(r"\bdeparted\s+([A-Za-z' ]+?)(?:\s+with|\s+for|,|$)", event, re.IGNORECASE)
        if depart_match:
            pending_from = detect_location(depart_match.group(1))
            pending_notes = [event]
            pending_duration = detect_duration_days(event)
            continue

        set_out_match = re.search(r"\bset out for\s+([A-Za-z' ]+?)(?:,|\.|$)", event, re.IGNORECASE)
        if set_out_match:
            to_location = detect_location(set_out_match.group(1))
            from_location = summary.get("location", "")

        if "travel" in low and not to_location and not from_location:
            duration = detect_duration_days(event)
            if duration is not None:
                pending_duration = duration
                pending_notes.append(event)
                continue

        return_match = re.search(r"\breturned?\s+(?:to|toward)\s+([A-Za-z' ]+?)(?:,|\.|$)", event, re.IGNORECASE)
        if return_match:
            to_location = detect_location(return_match.group(1))
            from_location = from_location or pending_from or summary.get("location", "")

        arrive_match = re.search(r"\barrived?\s+(?:at|in|on)\s+([A-Za-z' ]+?)(?:,|\.|$)", event, re.IGNORECASE)
        if arrive_match:
            to_location = detect_location(arrive_match.group(1))
            from_location = from_location or pending_from or summary.get("location", "")

        if to_location and from_location != to_location:
            notes = " ".join([*pending_notes, event]).strip()
            logs.append({
                "session_number": summary["session_number"],
                "from_location": from_location,
                "to_location": to_location,
            "travel_method": detect_travel_method(notes),
            "duration_days": pending_duration or detect_duration_days(event),
            "duration_confidence": "low",
            "duration_basis": "Inferred from summary event wording.",
            "notes": notes,
            "source": "summary",
        })
            pending_from = ""
            pending_duration = None
            pending_notes = []

    return logs


def load_travel_facts() -> list[dict]:
    if not TRAVEL_FACTS_PATH.exists():
        return []

    with open(TRAVEL_FACTS_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    logs = []
    for entry in data.get("travel", []) or []:
        logs.append({
            "session_number": parse_session_ref(entry.get("session")),
            "from_location": entry.get("from", ""),
            "to_location": entry.get("to", ""),
            "travel_method": entry.get("method", "foot") or "foot",
            "duration_days": entry.get("duration_days"),
            "duration_confidence": entry.get("duration_confidence", ""),
            "duration_basis": entry.get("duration_basis", ""),
            "notes": entry.get("notes", ""),
            "source": "travel_yaml",
        })

    return logs


def load_canon_decisions() -> dict:
    if not CANON_DECISIONS_PATH.exists():
        return {}

    with open(CANON_DECISIONS_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def canon_session_number(item: dict) -> Optional[int]:
    try:
        return parse_session_ref(item.get("session"))
    except ValueError:
        return None


def canon_primary_locations(decisions: dict) -> dict[int, dict]:
    entries = {}
    for item in decisions.get("session_primary_locations", []) or []:
        session_number = canon_session_number(item)
        if session_number is None:
            continue
        if item.get("status") in {"needs_db_update", "active", "applied"}:
            entries[session_number] = item
    return entries


def canon_event_decisions(decisions: dict) -> dict[int, list[dict]]:
    entries: dict[int, list[dict]] = {}
    for item in decisions.get("event_review_decisions", []) or []:
        if item.get("decision_type") != "missing_primary_event":
            continue
        if item.get("status") not in {"needs_db_update", "active", "applied"}:
            continue
        session_number = canon_session_number(item)
        if session_number is None:
            continue
        entries.setdefault(session_number, []).append(item)
    return entries


def load_review_documents() -> dict[int, dict]:
    if not REVIEWS_DIR.exists():
        return {}

    documents = {}
    for path in sorted(REVIEWS_DIR.glob("*_review.yaml")):
        with open(path, "r", encoding="utf-8") as f:
            document = yaml.safe_load(f) or {}
        try:
            session_number = parse_session_ref(document.get("session"))
        except ValueError:
            continue
        documents[session_number] = document
    return documents


def reviewed_event_text(item: dict) -> str:
    if item.get("decision") == "corrected":
        return (item.get("canonical_text") or "").strip()
    if item.get("decision") == "added":
        return (item.get("canonical_text") or item.get("source_text") or "").strip()
    return (item.get("source_text") or "").strip()


def review_sequence_value(item: dict, fallback: float) -> float:
    try:
        return float(item.get("sequence"))
    except (TypeError, ValueError):
        return fallback


def ordered_review_items(review: dict) -> list[dict]:
    indexed = []
    for index, item in enumerate([*(review.get("items") or []), *(review.get("added_items") or [])], start=1):
        indexed.append((review_sequence_value(item, float(index)), index, item))
    return [item for _sequence, _index, item in sorted(indexed, key=lambda entry: (entry[0], entry[1]))]


def review_events_for_session(summary: dict, review: Optional[dict]) -> Optional[list[dict]]:
    if not review or review.get("status") not in {"reviewed", "complete", "applied"}:
        return None

    events = []
    for item in ordered_review_items(review):
        decision = item.get("decision") or "pending"
        if decision in {"pending", "rejected"}:
            continue
        text = reviewed_event_text(item)
        if not text:
            continue
        events.append({
            "description": text,
            "event_type": item.get("event_type") or classify_event_type(text),
            "location": item.get("location") or detect_location(text),
            "significance": item.get("significance") or event_significance(text),
            "notes": f"Loaded from {review.get('session', 'review')} review: {item.get('id', 'unknown')}",
        })

    return events


def review_primary_locations(reviews: dict[int, dict]) -> dict[int, str]:
    locations = {}
    for session_number, review in reviews.items():
        if review.get("status") not in {"reviewed", "complete", "applied"}:
            continue
        location = (review.get("primary_location") or "").strip()
        if location:
            locations[session_number] = location
    return locations


def review_location_names(reviews: dict[int, dict]) -> set[str]:
    locations = set()
    for review in reviews.values():
        if review.get("status") not in {"reviewed", "complete", "applied"}:
            continue
        for location in [review.get("primary_location") or ""]:
            if location.strip():
                locations.add(location.strip())
        for item in [*(review.get("items") or []), *(review.get("added_items") or [])]:
            if item.get("decision") in {"pending", "rejected"}:
                continue
            location = (item.get("location") or "").strip()
            if location:
                locations.add(location)
    return locations


def review_location_sql(name: str) -> str:
    return f"""
INSERT INTO location (name, location_type_id, description)
VALUES (
    {sql_quote(name)},
    (SELECT id FROM location_type WHERE type_name = 'wilderness'),
    {sql_quote("Location introduced through session review.")}
)
ON CONFLICT (name) DO NOTHING;
""".strip()


def event_identity(description: str, location: str = "") -> tuple[str, str]:
    description_key = re.sub(r"\s+", " ", description or "").strip().lower()
    location_key = re.sub(r"\s+", " ", location or "").strip().lower()
    return description_key, location_key


def canon_events_for_load(session_number: int, reviewed_events: Optional[list[dict]], canon_events: dict[int, list[dict]]) -> list[dict]:
    items = canon_events.get(session_number, []) or []
    if reviewed_events is None:
        return items

    reviewed_keys = {
        event_identity(event.get("description", ""), event.get("location", ""))
        for event in reviewed_events
    }
    return [
        item for item in items
        if event_identity(item.get("description", ""), item.get("location", "")) not in reviewed_keys
    ]


def entity_mentioned(entity: str, text: str) -> bool:
    low = text.lower()

    aliases = {
        "The Black Blade": ["black blade", "dark blade"],
        "Grimoire Mutandi": ["grimoire mutandi", "grimoire", "satchel"],
        "Infernal Orb of Rage": ["infernal orb", "orb of rage", "red orb"],
        "Wand of Wells": ["wand of wells"],
        "Gildas' Enhanced Staff": ["enhanced staff", "magical staff", "staff of defense"],
        "Mikani's Breathing Cap": ["breathing cap", "cap of water breathing", "water breathing cap"],
        "Brigit's Upgraded Bow": ["upgraded bow", "magical bow", "bow of warning", "short bow of warning"],
        "Corvinas' Flame Blade": ["flame blade", "flaming longsword", "flaming sword", "flametongue"],
        "Roon's Shield": ["magical shield", "new shield", "shield and armor class"],
    }.get(entity, [entity])

    return any(alias.lower() in low for alias in aliases)


def first_mention_session(entity: str, summaries: list[dict]) -> Optional[int]:
    for summary in summaries:
        text = "\n".join([
            summary["title"],
            summary["summary"],
            *summary["events"],
        ])
        if entity_mentioned(entity, text):
            return summary["session_number"]
    return None


def classify_event_type(event: str) -> str:
    low = event.lower()

    if any(term in low for term in ["combat", "attack", "damage", "defeated", "battle", "cultist"]):
        return "combat"
    if re.search(r"\bdragon\b", low):
        return "combat"
    if any(term in low for term in ["travel", "depart", "road", "journey", "coast", "shoreline"]):
        return "travel"
    if re.search(r"\barrived?\s+(?:at|in|on)\b", low):
        return "travel"
    if any(term in low for term in ["gift", "given", "received", "acquired", "cap", "blade", "bow", "shield", "staff"]):
        return "acquisition"
    if any(term in low for term in ["rest", "long rest", "sleep"]):
        return "rest"
    if any(term in low for term in ["meet", "met", "talk", "asks", "asked", "discuss", "conversation"]):
        return "social"
    if any(term in low for term in ["learn", "discover", "find", "found", "revealed", "well", "wand", "lore"]):
        return "discovery"

    return "discovery"


def event_significance(event: str) -> int:
    low = event.lower()

    if any(term in low for term in ["dragon", "cataclysm", "well", "wand", "demon lord", "defeated"]):
        return 5
    if any(term in low for term in ["gift", "received", "arrived", "learned", "discovered"]):
        return 4
    return 3


def location_expr(location: str) -> str:
    if not location:
        return "NULL"
    return f"(SELECT id FROM location WHERE name = {sql_quote(location)} LIMIT 1)"


def canon_location_sql(name: str, description: str = "") -> str:
    return f"""
INSERT INTO location (name, location_type_id, description)
VALUES (
    {sql_quote(name)},
    (SELECT id FROM location_type WHERE type_name = 'coastal'),
    {sql_quote(description)}
)
ON CONFLICT (name) DO UPDATE SET
    location_type_id = COALESCE(location.location_type_id, EXCLUDED.location_type_id),
    description = COALESCE(NULLIF(location.description, ''), EXCLUDED.description);
""".strip()


def session_sql(session: dict) -> str:
    number = session["session_number"]
    audio_path = BASE2 / "audio" / f"session{number:02d}.wav"
    transcript_path = BASE2 / "knowledge" / "Faban" / "raw" / f"session{number:02d}_transcript.txt"

    return f"""
INSERT INTO session (
    session_number, session_date, in_game_date, title, summary,
    location_id, audio_file_path, transcript_path, notes
)
VALUES (
    {number},
    {sql_quote(session["physical_date"])},
    {sql_quote(session["in_game_date"])},
    {sql_quote(session["title"])},
    {sql_quote(session["summary"])},
    {location_expr(session["location"])},
    {sql_quote(str(audio_path) if audio_path.exists() else "")},
    {sql_quote(str(transcript_path) if transcript_path.exists() else "")},
    {sql_quote("Loaded from " + session["source_path"])}
)
ON CONFLICT (session_number) DO UPDATE SET
    session_date = EXCLUDED.session_date,
    in_game_date = EXCLUDED.in_game_date,
    title = EXCLUDED.title,
    summary = EXCLUDED.summary,
    location_id = EXCLUDED.location_id,
    audio_file_path = EXCLUDED.audio_file_path,
    transcript_path = EXCLUDED.transcript_path,
    notes = EXCLUDED.notes;
""".strip()


def delete_events_sql(session_number: int) -> str:
    return f"""
DELETE FROM session_event
WHERE session_id = (SELECT id FROM session WHERE session_number = {session_number});
""".strip()


def delete_travel_logs_sql(session_number: int) -> str:
    return f"""
DELETE FROM travel_log
WHERE session_id = (SELECT id FROM session WHERE session_number = {session_number})
  AND notes LIKE '%Loaded from summary travel inference%';
""".strip()


def event_sql(session_number: int, sequence: int, event: str) -> str:
    event_type = classify_event_type(event)
    location = detect_location(event)

    return f"""
INSERT INTO session_event (
    session_id, event_type_id, sequence_order, location_id,
    description, significance, notes
)
VALUES (
    (SELECT id FROM session WHERE session_number = {session_number}),
    (SELECT id FROM event_type WHERE type_name = {sql_quote(event_type)}),
    {sequence},
    {location_expr(location)},
    {sql_quote(event)},
    {event_significance(event)},
    {sql_quote("Loaded from summary key event")}
);
""".strip()


def canon_event_sql(session_number: int, sequence: int, item: dict) -> str:
    description = item.get("description", "").strip()
    event_type = item.get("event_type", "discovery")
    location = item.get("location", "")
    significance = item.get("significance", 4)
    notes = item.get("reason") or "Loaded from canon_decisions.yaml"

    return f"""
INSERT INTO session_event (
    session_id, event_type_id, sequence_order, location_id,
    description, significance, notes
)
VALUES (
    (SELECT id FROM session WHERE session_number = {session_number}),
    (SELECT id FROM event_type WHERE type_name = {sql_quote(event_type)}),
    {sequence},
    {location_expr(location)},
    {sql_quote(description)},
    {significance},
    {sql_quote("Loaded from canon_decisions.yaml: " + notes)}
);
""".strip()


def reviewed_event_sql(session_number: int, sequence: int, item: dict) -> str:
    return f"""
INSERT INTO session_event (
    session_id, event_type_id, sequence_order, location_id,
    description, significance, notes
)
VALUES (
    (SELECT id FROM session WHERE session_number = {session_number}),
    (SELECT id FROM event_type WHERE type_name = {sql_quote(item.get("event_type", "discovery"))}),
    {sequence},
    {location_expr(item.get("location", ""))},
    {sql_quote(item.get("description", ""))},
    {item.get("significance", 3)},
    {sql_quote(item.get("notes", "Loaded from review"))}
);
""".strip()


def travel_log_sql(log: dict) -> str:
    duration = log["duration_days"] if log["duration_days"] is not None else "NULL"
    duration_confidence = log.get("duration_confidence", "")
    duration_basis = log.get("duration_basis", "")
    if log.get("source") == "travel_yaml":
        notes = f"Loaded from travel.yaml: {log['notes']}"
    else:
        notes = f"Loaded from summary travel inference: {log['notes']}"

    return f"""
INSERT INTO travel_log (
    session_id, from_location_id, to_location_id,
    travel_method, duration_days, duration_confidence,
    duration_basis, notes
)
VALUES (
    (SELECT id FROM session WHERE session_number = {log["session_number"]}),
    {location_expr(log["from_location"])},
    {location_expr(log["to_location"])},
    {sql_quote(log["travel_method"])},
    {duration},
    {sql_quote(duration_confidence)},
    {sql_quote(duration_basis)},
    {sql_quote(notes)}
);
""".strip()


def travel_log_schema_sql() -> str:
    return """
ALTER TABLE travel_log ADD COLUMN IF NOT EXISTS duration_confidence VARCHAR(30);
ALTER TABLE travel_log ADD COLUMN IF NOT EXISTS duration_basis TEXT;
""".strip()


def song_prompt_sql(entry: dict) -> str:
    assignments = [
        f"suno_prompt = {sql_quote(entry['prompt'])}",
        f"musical_key = {sql_quote(entry.get('key', ''))}",
        f"meter = {sql_quote(entry.get('meter', ''))}",
        f"tempo = {sql_quote(entry.get('tempo', ''))}",
        f"instrumentation = {sql_quote(entry.get('instrumentation', ''))}",
    ]

    return f"""
UPDATE song
SET {", ".join(assignments)}
WHERE song_number = {entry["song_number"]};
""".strip()


def song_schema_sql() -> str:
    return """
ALTER TABLE song ADD COLUMN IF NOT EXISTS tempo VARCHAR(60);

DROP VIEW IF EXISTS v_songbook;
ALTER TABLE song ALTER COLUMN musical_key TYPE VARCHAR(120);
ALTER TABLE song ALTER COLUMN meter TYPE VARCHAR(120);
ALTER TABLE song ALTER COLUMN tempo TYPE VARCHAR(120);

CREATE VIEW v_songbook AS
    SELECT s.song_number, s.title, ss.style_name AS style,
           sc.category_name AS category, s.song_type, s.short_description,
           s.long_description, s.summary, s.suno_prompt, s.musical_key,
           s.meter, s.tempo, s.instrumentation,
           s.lyrics_local_path, s.mp3_local_path, s.mp3_url, s.lyrics_url
    FROM song s
    LEFT JOIN song_style ss ON s.style_id = ss.id
    LEFT JOIN song_category sc ON s.category_id = sc.id
    LEFT JOIN song_performance sp ON s.id = sp.song_id
    GROUP BY s.id, s.song_number, s.title, ss.style_name, sc.category_name, s.song_type,
             s.short_description, s.long_description, s.summary, s.suno_prompt, s.musical_key,
             s.meter, s.tempo, s.instrumentation, s.lyrics_local_path, s.mp3_local_path, s.mp3_url, s.lyrics_url
    ORDER BY s.song_number;
""".strip()


def canon_npc_sql(npc: dict) -> str:
    name = npc["name"]
    alias = npc.get("alias", "")
    description = npc.get("description", "")
    location = npc.get("location", "")
    first_seen_session = npc.get("first_seen_session")
    status = npc.get("status", "unknown")
    is_named = "TRUE" if npc.get("is_named", True) else "FALSE"

    return f"""
UPDATE npc
SET
    entity_status_id = COALESCE((SELECT id FROM entity_status WHERE status_code = {sql_quote(status)} LIMIT 1), npc.entity_status_id),
    last_known_location_id = COALESCE({location_expr(location)}, npc.last_known_location_id),
    first_seen_session = COALESCE((SELECT id FROM session WHERE session_number = {first_seen_session}), npc.first_seen_session),
    alias = COALESCE(NULLIF({sql_quote(alias)}, ''), npc.alias),
    description = COALESCE(NULLIF({sql_quote(description)}, ''), npc.description),
    is_named = {is_named},
    notes = {sql_quote("Updated from reviewed canon NPC scrub.")}
WHERE name = {sql_quote(name)};

INSERT INTO npc (
    name, alias, entity_status_id, last_known_location_id,
    first_seen_session, description, is_named, notes
)
SELECT
    {sql_quote(name)},
    {sql_quote(alias)},
    (SELECT id FROM entity_status WHERE status_code = {sql_quote(status)} LIMIT 1),
    {location_expr(location)},
    (SELECT id FROM session WHERE session_number = {first_seen_session}),
    {sql_quote(description)},
    {is_named},
    {sql_quote("Loaded from reviewed canon NPC scrub.")}
WHERE NOT EXISTS (SELECT 1 FROM npc WHERE name = {sql_quote(name)});
""".strip()


def canon_npc_scrub_sql() -> str:
    return "\n\n".join(canon_npc_sql(npc) for npc in CANON_NPCS)


def canon_enemy_sql(enemy: dict) -> str:
    name = enemy["name"]
    enemy_type = enemy.get("enemy_type", "")
    description = enemy.get("description", "")
    first_encountered_session = enemy.get("first_encountered_session")
    status = enemy.get("status", "unknown")
    threat_level = enemy.get("threat_level", "moderate")

    return f"""
UPDATE enemy
SET
    enemy_type = COALESCE(NULLIF({sql_quote(enemy_type)}, ''), enemy.enemy_type),
    threat_level_id = COALESCE((SELECT id FROM threat_level WHERE level_code = {sql_quote(threat_level)} LIMIT 1), enemy.threat_level_id),
    entity_status_id = COALESCE((SELECT id FROM entity_status WHERE status_code = {sql_quote(status)} LIMIT 1), enemy.entity_status_id),
    first_encountered_session = COALESCE((SELECT id FROM session WHERE session_number = {first_encountered_session}), enemy.first_encountered_session),
    description = COALESCE(NULLIF({sql_quote(description)}, ''), enemy.description),
    notes = {sql_quote("Updated from reviewed canon enemy scrub.")}
WHERE name = {sql_quote(name)};

INSERT INTO enemy (
    name, enemy_type, threat_level_id,
    entity_status_id, first_encountered_session,
    description, notes
)
SELECT
    {sql_quote(name)},
    {sql_quote(enemy_type)},
    (SELECT id FROM threat_level WHERE level_code = {sql_quote(threat_level)} LIMIT 1),
    (SELECT id FROM entity_status WHERE status_code = {sql_quote(status)} LIMIT 1),
    (SELECT id FROM session WHERE session_number = {first_encountered_session}),
    {sql_quote(description)},
    {sql_quote("Loaded from reviewed canon enemy scrub.")}
WHERE NOT EXISTS (SELECT 1 FROM enemy WHERE name = {sql_quote(name)});
""".strip()


def canon_enemy_scrub_sql() -> str:
    return "\n\n".join(canon_enemy_sql(enemy) for enemy in CANON_ENEMIES)


def pipeline_run_sql(session_count: int, event_count: int) -> str:
    return f"""
INSERT INTO pipeline_run (
    pipeline_stage, model_used, input_file, output_file,
    records_created, records_updated, success
)
VALUES (
    'summary_db_load',
    'deterministic-python',
    {sql_quote(str(CLEAN / "session*_summary.md"))},
    {sql_quote(str(OUT_SQL))},
    {session_count + event_count},
    0,
    TRUE
);
""".strip()


def first_seen_sql(summaries: list[dict]) -> str:
    statements = []

    for location in KNOWN_LOCATIONS:
        session_number = first_mention_session(location, summaries)
        if session_number is None:
            continue
        statements.append(
            "UPDATE location "
            f"SET first_visited_session = COALESCE(first_visited_session, (SELECT id FROM session WHERE session_number = {session_number})) "
            f"WHERE name = {sql_quote(location)};"
        )

    for npc in KNOWN_NPCS:
        session_number = first_mention_session(npc, summaries)
        if session_number is None:
            continue
        statements.append(
            "UPDATE npc "
            f"SET first_seen_session = COALESCE(first_seen_session, (SELECT id FROM session WHERE session_number = {session_number})) "
            f"WHERE name = {sql_quote(npc)};"
        )

    for enemy in KNOWN_ENEMIES:
        session_number = first_mention_session(enemy, summaries)
        if session_number is None:
            continue
        statements.append(
            "UPDATE enemy "
            f"SET first_encountered_session = COALESCE(first_encountered_session, (SELECT id FROM session WHERE session_number = {session_number})) "
            f"WHERE name = {sql_quote(enemy)};"
        )

    for artifact in KNOWN_ARTIFACTS:
        session_number = first_mention_session(artifact, summaries)
        if session_number is None:
            continue
        statements.append(
            "UPDATE artifact "
            f"SET discovered_session = COALESCE(discovered_session, (SELECT id FROM session WHERE session_number = {session_number})) "
            f"WHERE name = {sql_quote(artifact)};"
        )

    return "\n".join(statements)


def build_sql(summaries: list[dict]) -> str:
    decisions = load_canon_decisions()
    primary_locations = canon_primary_locations(decisions)
    canon_events = canon_event_decisions(decisions)
    reviews = load_review_documents()
    reviewed_primary_locations = review_primary_locations(reviews)
    reviewed_locations = review_location_names(reviews)
    review_events = {
        summary["session_number"]: review_events_for_session(summary, reviews.get(summary["session_number"]))
        for summary in summaries
    }
    total_events = sum(
        (
            len(review_events[summary["session_number"]])
            if review_events[summary["session_number"]] is not None
            else len(summary["events"])
        )
        + len(canon_events_for_load(
            summary["session_number"],
            review_events[summary["session_number"]],
            canon_events,
        ))
        for summary in summaries
    )
    inferred_travel_logs = [
        log
        for summary in summaries
        for log in extract_travel_logs(summary)
    ]
    trusted_travel_logs = load_travel_facts()
    trusted_keys = {
        (log["session_number"], log["from_location"], log["to_location"])
        for log in trusted_travel_logs
    }
    travel_logs = [
        *trusted_travel_logs,
        *[
            log
            for log in inferred_travel_logs
            if (log["session_number"], log["from_location"], log["to_location"]) not in trusted_keys
        ],
    ]
    statements = [
        "-- Generated by scripts/load_summaries.py. Safe to rerun.",
        "BEGIN;",
    ]

    if any(item.get("canonical") == "Coast near Catur" for item in primary_locations.values()):
        statements.append(canon_location_sql(
            "Coast near Catur",
            "Coast roughly 6 miles from Catur; party staging point before entering the sunken city.",
        ))
    for location in sorted(reviewed_locations):
        statements.append(review_location_sql(location))

    for summary in summaries:
        decision = primary_locations.get(summary["session_number"])
        if decision:
            summary = {**summary, "location": decision.get("canonical", summary["location"])}
        elif summary["session_number"] in reviewed_primary_locations:
            summary = {**summary, "location": reviewed_primary_locations[summary["session_number"]]}
        statements.append(session_sql(summary))

    statements.append(canon_npc_scrub_sql())
    statements.append(canon_enemy_scrub_sql())
    statements.append(travel_log_schema_sql())

    for summary in summaries:
        statements.append(delete_events_sql(summary["session_number"]))
        reviewed_events = review_events[summary["session_number"]]
        if reviewed_events is not None:
            for sequence, item in enumerate(reviewed_events, start=1):
                statements.append(reviewed_event_sql(summary["session_number"], sequence, item))
            base_count = len(reviewed_events)
        else:
            for sequence, event in enumerate(summary["events"], start=1):
                statements.append(event_sql(summary["session_number"], sequence, event))
            base_count = len(summary["events"])
        for offset, item in enumerate(canon_events_for_load(
            summary["session_number"],
            reviewed_events,
            canon_events,
        ), start=1):
            statements.append(canon_event_sql(
                summary["session_number"],
                base_count + offset,
                item,
            ))

    for summary in summaries:
        statements.append(delete_travel_logs_sql(summary["session_number"]))
    statements.append("DELETE FROM travel_log WHERE notes LIKE '%Loaded from travel.yaml%';")
    for log in travel_logs:
        statements.append(travel_log_sql(log))

    statements.append(first_seen_sql(summaries))
    statements.append(pipeline_run_sql(len(summaries), total_events + len(travel_logs)))
    statements.append("COMMIT;")
    statements.append("")

    return "\n\n".join(statements)


def discover_summaries() -> list[dict]:
    return [
        parse_summary(path)
        for path in sorted(CLEAN.glob("session*_summary.md"))
    ]


def write_sql() -> Path:
    summaries = discover_summaries()
    decisions = load_canon_decisions()
    canon_events = canon_event_decisions(decisions)
    reviews = load_review_documents()
    review_events = {
        summary["session_number"]: review_events_for_session(summary, reviews.get(summary["session_number"]))
        for summary in summaries
    }
    reviewed_event_count = sum(len(events) for events in review_events.values() if events is not None)
    canon_event_count = sum(
        len(canon_events_for_load(summary["session_number"], review_events[summary["session_number"]], canon_events))
        for summary in summaries
    )
    trusted_travel_logs = load_travel_facts()
    inferred_travel_logs = [
        log
        for summary in summaries
        for log in extract_travel_logs(summary)
    ]
    trusted_keys = {
        (log["session_number"], log["from_location"], log["to_location"])
        for log in trusted_travel_logs
    }
    travel_log_count = len(trusted_travel_logs) + len([
        log
        for log in inferred_travel_logs
        if (log["session_number"], log["from_location"], log["to_location"]) not in trusted_keys
    ])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_SQL.write_text(build_sql(summaries), encoding="utf-8")
    event_count = sum(
        len(review_events[summary["session_number"]])
        if review_events[summary["session_number"]] is not None
        else len(summary["events"])
        for summary in summaries
    ) + canon_event_count
    print(f"Wrote {OUT_SQL}")
    print(f"Sessions: {len(summaries)}")
    print(f"Events: {event_count}")
    if reviewed_event_count:
        print(f"Reviewed events: {reviewed_event_count}")
    if canon_event_count:
        print(f"Canon events: {canon_event_count}")
    print(f"Travel logs: {travel_log_count}")
    return OUT_SQL


def apply_sql(sql_path: Path, container: str, user: str, database: str):
    target = f"/tmp/{sql_path.name}"
    subprocess.run(["docker", "cp", str(sql_path), f"{container}:{target}"], check=True)
    subprocess.run(
        ["docker", "exec", container, "psql", "-v", "ON_ERROR_STOP=1", "-U", user, "-d", database, "-f", target],
        check=True,
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Load session summaries into Farrlind Postgres.")
    parser.add_argument("--apply", action="store_true", help="Apply generated SQL through Docker.")
    parser.add_argument("--container", default="farrlind_db")
    parser.add_argument("--user", default="admin")
    parser.add_argument("--database", default="farrlind")
    return parser.parse_args()


def main():
    args = parse_args()
    sql_path = write_sql()

    if args.apply:
        apply_sql(sql_path, args.container, args.user, args.database)


if __name__ == "__main__":
    main()
