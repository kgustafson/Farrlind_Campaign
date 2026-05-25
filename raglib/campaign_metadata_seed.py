from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from raglib.campaign import campaign_metadata_path, campaign_path


NPC_HINT_TERMS = {
    "lord",
    "vampire",
    "burgomaster",
    "father",
    "daughter",
    "son",
    "familiar",
    "imp",
    "npc",
    "companion",
    "enemy",
    "ally",
    "mentor",
}
NON_NPC_TERMS = {
    "campaign world",
    "domain",
    "location",
    "place",
    "city",
    "town",
    "village",
    "road",
    "tavern",
    "inn",
    "realm",
    "settlement",
    "party nickname",
}


def sql_quote(value: Any) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def normalized_text(value: Any) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def glossary_entry_is_npc(entry: dict[str, Any]) -> bool:
    text = normalized_text(f"{entry.get('term', '')} {entry.get('note', '')}")
    if any(term in text for term in NON_NPC_TERMS):
        return False
    return any(term in text for term in NPC_HINT_TERMS)


def load_campaign_metadata(path: Path | None = None) -> dict[str, Any]:
    metadata_path = path or campaign_metadata_path()
    if not metadata_path.exists():
        return {}
    return yaml.safe_load(metadata_path.read_text(encoding="utf-8")) or {}


def aliases_sql_array(aliases: list[str]) -> str:
    cleaned = [alias for alias in aliases if alias]
    if not cleaned:
        return "ARRAY[]::text[]"
    return "ARRAY[" + ", ".join(sql_quote(alias) for alias in cleaned) + "]"


def npc_seed_sql(entry: dict[str, Any]) -> str:
    name = (entry.get("term") or "").strip()
    aliases = [str(alias) for alias in entry.get("aliases", []) or [] if alias]
    note = (entry.get("note") or "").strip()
    alias_text = ", ".join(aliases)
    return f"""
WITH incoming AS (
    SELECT
        {sql_quote(name)}::text AS name,
        {sql_quote(alias_text)}::text AS alias,
        {sql_quote(note)}::text AS description,
        {aliases_sql_array(aliases)} AS aliases
),
matched AS (
    SELECT n.id
    FROM npc n, incoming i
    WHERE lower(n.name) = lower(i.name)
       OR lower(n.name) = ANY(SELECT lower(unnest(i.aliases)))
       OR lower(i.name) = ANY(SELECT lower(unnest(string_to_array(COALESCE(n.alias, ''), ', '))))
    ORDER BY n.id
    LIMIT 1
),
updated AS (
    UPDATE npc n
    SET
        alias = COALESCE(NULLIF(n.alias, ''), i.alias),
        description = COALESCE(NULLIF(n.description, ''), i.description),
        entity_status_id = COALESCE(n.entity_status_id, (SELECT id FROM entity_status WHERE status_code = 'unknown' LIMIT 1)),
        notes = CASE
            WHEN n.notes IS NULL OR n.notes = '' THEN 'Seeded from campaign.yaml.'
            WHEN n.notes NOT LIKE '%Seeded from campaign.yaml.%' THEN n.notes || E'\\nSeeded from campaign.yaml.'
            ELSE n.notes
        END
    FROM incoming i, matched m
    WHERE n.id = m.id
    RETURNING n.id
)
INSERT INTO npc (
    name, alias, entity_status_id, description, is_named, notes
)
SELECT
    i.name,
    i.alias,
    (SELECT id FROM entity_status WHERE status_code = 'unknown' LIMIT 1),
    i.description,
    TRUE,
    'Seeded from campaign.yaml.'
FROM incoming i
WHERE NOT EXISTS (SELECT 1 FROM matched);
""".strip()


def player_character_seed_sql(member: dict[str, Any]) -> str:
    name = (member.get("full_name") or member.get("character_name") or "").strip()
    if not name:
        return ""
    character_class = (member.get("class") or "").strip()
    race = (member.get("race") or "").strip()
    player_name = (member.get("player_name") or "").strip()
    notes = (member.get("notes") or "").strip()
    aliases = ", ".join(str(alias) for alias in member.get("aliases", []) or [] if alias)
    full_notes = notes
    if aliases:
        full_notes = f"{full_notes} Aliases: {aliases}.".strip()
    return f"""
INSERT INTO character_class (class_name)
SELECT {sql_quote(character_class)}
WHERE {sql_quote(character_class)} <> ''
  AND NOT EXISTS (SELECT 1 FROM character_class WHERE lower(class_name) = lower({sql_quote(character_class)}));

INSERT INTO character_race (race_name)
SELECT {sql_quote(race)}
WHERE {sql_quote(race)} <> ''
  AND NOT EXISTS (SELECT 1 FROM character_race WHERE lower(race_name) = lower({sql_quote(race)}));

UPDATE player_character
SET
    player_name = COALESCE(NULLIF({sql_quote(player_name)}, ''), player_name),
    character_class_id = COALESCE((SELECT id FROM character_class WHERE lower(class_name) = lower({sql_quote(character_class)}) LIMIT 1), character_class_id),
    character_race_id = COALESCE((SELECT id FROM character_race WHERE lower(race_name) = lower({sql_quote(race)}) LIMIT 1), character_race_id),
    notes = COALESCE(NULLIF({sql_quote(full_notes)}, ''), notes)
WHERE lower(name) = lower({sql_quote(name)});

INSERT INTO player_character (
    name, player_name, character_class_id, character_race_id, is_active, notes
)
SELECT
    {sql_quote(name)},
    {sql_quote(player_name)},
    (SELECT id FROM character_class WHERE lower(class_name) = lower({sql_quote(character_class)}) LIMIT 1),
    (SELECT id FROM character_race WHERE lower(race_name) = lower({sql_quote(race)}) LIMIT 1),
    TRUE,
    {sql_quote(full_notes)}
WHERE NOT EXISTS (SELECT 1 FROM player_character WHERE lower(name) = lower({sql_quote(name)}));
""".strip()


def build_campaign_metadata_seed_sql(metadata: dict[str, Any]) -> str:
    statements = [
        "-- Generated from campaign.yaml by raglib.campaign_metadata_seed.",
        "-- Seeds campaign-specific player characters and known NPC glossary entries.",
        "",
    ]
    for member in metadata.get("party", []) or []:
        statement = player_character_seed_sql(member)
        if statement:
            statements.append(statement)
            statements.append("")
    for entry in metadata.get("glossary", []) or []:
        if glossary_entry_is_npc(entry):
            statements.append(npc_seed_sql(entry))
            statements.append("")
    return "\n".join(statements)


def write_campaign_metadata_seed_sql(
    metadata_path: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    metadata = load_campaign_metadata(metadata_path)
    target = output_path or campaign_path("init/15_campaign_metadata_seed.sql")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build_campaign_metadata_seed_sql(metadata), encoding="utf-8")
    return target
