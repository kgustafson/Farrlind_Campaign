import re
from datetime import date
from pathlib import Path
from typing import Any, Optional

import yaml
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from raglib.campaign import campaign_path
from web_review import db


class CanonReadError(RuntimeError):
    pass


class CanonWriteError(RuntimeError):
    pass


REPO_ROOT = Path(__file__).resolve().parents[2]
CANON_DECISIONS_PATH = campaign_path("canon_decisions.yaml")
LOOKUP_OVERRIDES_PATH = campaign_path("lookup_overrides.yaml")
LOOKUP_OVERRIDES_SQL_PATH = campaign_path("init") / "20_lookup_overrides.sql"
FARRLIND_MONTH_ORDER = {
    "Sha'al": 1,
    "Amoral": 2,
    "Yugal": 3,
    "Klasal": 4,
    "Wurral": 5,
    "Runal": 6,
    "Eeral": 7,
    "Apollal": 8,
    "Namal": 9,
    "Hephal": 10,
    "Sial": 11,
    "Lunal": 12,
}


def _fetch(sql: str, params: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    try:
        return db.fetch_all(sql, params)
    except SQLAlchemyError as exc:
        raise CanonReadError(str(exc)) from exc


def _execute(sql: str, params: dict[str, Any]) -> None:
    try:
        db.execute(sql, params)
    except SQLAlchemyError as exc:
        raise CanonWriteError(str(exc)) from exc


def _fetch_one_write(sql: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        engine = db.make_engine()
        with engine.begin() as connection:
            result = connection.execute(text(sql), params)
            row = result.first()
            return dict(row._mapping) if row else {}
    except SQLAlchemyError as exc:
        raise CanonWriteError(str(exc)) from exc


def _execute_transaction(statements: list[tuple[str, dict[str, Any]]]) -> None:
    try:
        engine = db.make_engine()
        with engine.begin() as connection:
            for sql, params in statements:
                connection.execute(text(sql), params)
    except SQLAlchemyError as exc:
        raise CanonWriteError(str(exc)) from exc


def timeline_in_game_date_bounds(value: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    if not value:
        return None, None

    parsed_dates: list[tuple[tuple[int, int, int], str]] = []
    pattern = re.compile(
        r"(?P<year>\d{3,4})\s+AS\s+(?:[—-]\s*)?"
        r"(?P<month>[A-Za-z']+)\s+"
        r"(?P<start>\d{1,2})(?:\s*-\s*(?P<end>\d{1,2}))?"
    )
    for match in pattern.finditer(value):
        year = int(match.group("year"))
        month = match.group("month")
        month_order = FARRLIND_MONTH_ORDER.get(month, 99)
        start_day = int(match.group("start"))
        end_day = int(match.group("end") or start_day)
        parsed_dates.append(((year, month_order, start_day), f"{year} AS {month} {start_day}"))
        parsed_dates.append(((year, month_order, end_day), f"{year} AS {month} {end_day}"))

    if not parsed_dates:
        return value, value

    parsed_dates.sort(key=lambda item: item[0])
    return parsed_dates[0][1], parsed_dates[-1][1]


def timeline_in_game_date_display(value: Optional[str]) -> str:
    earliest, latest = timeline_in_game_date_bounds(value)
    if not earliest:
        return ""
    if earliest == latest:
        return earliest
    return f"{earliest} thru {latest}"


def locations() -> list[str]:
    rows = _fetch("SELECT name FROM location ORDER BY name;")
    return [row["name"] for row in rows]


def location_types() -> list[dict[str, Any]]:
    return _fetch("SELECT id, type_name FROM location_type ORDER BY type_name;")


def song_styles() -> list[dict[str, Any]]:
    return _fetch("SELECT id, style_name FROM song_style ORDER BY style_name;")


def song_categories() -> list[dict[str, Any]]:
    return _fetch("SELECT id, category_name FROM song_category ORDER BY category_name;")


def location_type_id(type_name: Optional[str]) -> Optional[int]:
    if not type_name:
        return None
    rows = _fetch(
        "SELECT id FROM location_type WHERE lower(type_name) = lower(:type_name) LIMIT 1;",
        {"type_name": type_name},
    )
    return rows[0]["id"] if rows else None


def artifact_types() -> list[dict[str, Any]]:
    return _fetch("SELECT id, type_name FROM artifact_type ORDER BY type_name;")


def artifact_type_id(type_name: Optional[str]) -> Optional[int]:
    if not type_name:
        return None
    rows = _fetch(
        "SELECT id FROM artifact_type WHERE lower(type_name) = lower(:type_name) LIMIT 1;",
        {"type_name": type_name},
    )
    return rows[0]["id"] if rows else None


def lore_categories() -> list[str]:
    rows = _fetch("""
        SELECT DISTINCT category
        FROM lore_item
        WHERE category IS NOT NULL AND category <> ''
        ORDER BY category;
    """)
    categories = [row["category"] for row in rows]
    defaults = [
        "well_knowledge",
        "history",
        "divine",
        "cosmology",
        "faction_lore",
        "location_lore",
        "culture",
        "magic",
        "threat",
        "prophecy",
        "artifact_lore",
        "canon_ambiguity",
    ]
    return sorted({*categories, *defaults})


def entity_statuses() -> list[dict[str, Any]]:
    return _fetch("SELECT id, status_code, description FROM entity_status ORDER BY status_code;")


def entity_status_id(status_code: Optional[str]) -> Optional[int]:
    if not status_code:
        return None
    rows = _fetch(
        "SELECT id FROM entity_status WHERE lower(status_code) = lower(:status_code) LIMIT 1;",
        {"status_code": status_code},
    )
    return rows[0]["id"] if rows else None


def factions() -> list[dict[str, Any]]:
    return _fetch("SELECT id, name FROM faction ORDER BY name;")


OPEN_THREAD_STATUSES = [
    {"code": "open", "label": "open"},
    {"code": "resolved", "label": "resolved"},
    {"code": "superseded", "label": "superseded"},
    {"code": "unknown", "label": "unknown"},
]


OPEN_THREAD_TYPES = [
    "lore_mystery",
    "active_threat",
    "unresolved_promise",
    "pending_quest",
    "character_hook",
    "faction_tension",
    "canon_ambiguity",
    "dm_foreshadowing",
]


LOOKUP_TABLES: dict[str, dict[str, Any]] = {
    "artifact-types": {
        "key": "artifact-types",
        "label": "Artifact Types",
        "table": "artifact_type",
        "value_column": "type_name",
        "description_column": None,
        "seed": [],
        "custom": False,
    },
    "location-types": {
        "key": "location-types",
        "label": "Location Types",
        "table": "location_type",
        "value_column": "type_name",
        "description_column": None,
        "seed": [],
        "custom": False,
    },
    "combat-outcomes": {
        "key": "combat-outcomes",
        "label": "Combat Outcomes",
        "table": "combat_outcome",
        "value_column": "outcome_code",
        "description_column": "description",
        "seed": [
            ("defeated", "Enemy or encounter was overcome."),
            ("killed", "Enemy was killed."),
            ("captured", "Enemy was captured."),
            ("escaped", "Enemy escaped the encounter."),
            ("fled", "Enemy fled the encounter."),
            ("summoned", "Enemy was summoned or appeared."),
            ("unknown", "Outcome has not been established."),
        ],
        "custom": True,
    },
    "npc-status": {
        "key": "npc-status",
        "label": "NPC Status",
        "table": "entity_status",
        "value_column": "status_code",
        "description_column": "description",
        "seed": [],
        "custom": False,
    },
    "workflow-status-states": {
        "key": "workflow-status-states",
        "label": "Workflow Status States",
        "table": "workflow_status_state",
        "value_column": "status_code",
        "description_column": "description",
        "seed": [
            ("initialized", "Workflow has been created but not started."),
            ("pending", "Step is waiting to run."),
            ("running", "Step is currently running."),
            ("completed", "Step or workflow completed successfully."),
            ("partially_completed", "Workflow has completed some but not all steps."),
            ("blocked", "Step cannot proceed until a blocker is cleared."),
            ("needs_attention", "Human attention is required."),
            ("failed", "Step or workflow failed."),
            ("skipped", "Step was intentionally skipped."),
        ],
        "custom": True,
    },
    "artifact-flags": {
        "key": "artifact-flags",
        "label": "Artifact Flags",
        "table": "artifact_flag",
        "value_column": "flag_code",
        "description_column": "description",
        "seed": [
            ("sentient", "Artifact has awareness or agency."),
            ("cursed", "Artifact carries a harmful curse."),
            ("infernal", "Artifact has infernal origin, influence, or binding."),
        ],
        "custom": True,
    },
    "factions": {
        "key": "factions",
        "label": "Factions",
        "table": "faction",
        "value_column": "name",
        "description_column": "description",
        "seed": [],
        "custom": False,
    },
}


def location_rows() -> list[dict[str, Any]]:
    return _fetch("""
        SELECT
            l.id,
            l.name,
            lt.type_name AS location_type,
            parent.name AS parent_location,
            l.description,
            l.is_underwater,
            l.is_feywild,
            fs.session_number AS first_visited_session,
            l.notes
        FROM location l
        LEFT JOIN location_type lt ON lt.id = l.location_type_id
        LEFT JOIN location parent ON parent.id = l.parent_location_id
        LEFT JOIN session fs ON fs.id = l.first_visited_session
        ORDER BY l.name;
    """)


def session_rows() -> list[dict[str, Any]]:
    return _fetch("""
        SELECT session_number, title
        FROM session
        ORDER BY session_number;
    """)


def session_timeline_detail(session_number: int) -> Optional[dict[str, Any]]:
    rows = _fetch("""
        SELECT
            s.session_number,
            s.title,
            s.session_date,
            s.in_game_date,
            p.name AS primary_location,
            sl.name AS start_location,
            el.name AS end_location,
            s.summary,
            s.notes
        FROM session s
        LEFT JOIN location p ON p.id = s.location_id
        LEFT JOIN location sl ON sl.id = s.start_location_id
        LEFT JOIN location el ON el.id = s.end_location_id
        WHERE s.session_number = :session_number;
    """, {"session_number": session_number})
    return rows[0] if rows else None


def update_session_timeline(session_number: int, values: dict[str, Any]) -> None:
    params = {**values, "session_number": session_number}
    _execute("""
        UPDATE session
        SET
            title = :title,
            session_date = :session_date,
            in_game_date = :in_game_date,
            location_id = :primary_location_id,
            start_location_id = :start_location_id,
            end_location_id = :end_location_id,
            summary = :summary,
            notes = :notes
        WHERE session_number = :session_number;
    """, params)


def location_id(name: Optional[str]) -> Optional[int]:
    if not name:
        return None
    rows = _fetch(
        "SELECT id FROM location WHERE lower(name) = lower(:name) LIMIT 1;",
        {"name": name},
    )
    return rows[0]["id"] if rows else None


def location_detail(location_id: int) -> Optional[dict[str, Any]]:
    rows = _fetch("""
        SELECT
            l.id,
            l.name,
            l.location_type_id,
            l.parent_location_id,
            l.description,
            l.is_underwater,
            l.is_feywild,
            fs.session_number AS first_visited_session,
            l.notes
        FROM location l
        LEFT JOIN session fs ON fs.id = l.first_visited_session
        WHERE l.id = :id;
    """, {"id": location_id})
    return rows[0] if rows else None


def create_location(values: dict[str, Any]) -> None:
    _execute("""
        INSERT INTO location (
            name, location_type_id, parent_location_id, description,
            is_underwater, is_feywild, first_visited_session, notes
        )
        VALUES (
            :name, :location_type_id, :parent_location_id, :description,
            :is_underwater,
            :is_feywild,
            (SELECT id FROM session WHERE session_number = :first_visited_session),
            :notes
        );
    """, values)


def update_location(location_id: int, values: dict[str, Any]) -> None:
    params = {**values, "id": location_id}
    _execute("""
        UPDATE location
        SET
            name = :name,
            location_type_id = :location_type_id,
            parent_location_id = :parent_location_id,
            description = :description,
            is_underwater = :is_underwater,
            is_feywild = :is_feywild,
            first_visited_session = (SELECT id FROM session WHERE session_number = :first_visited_session),
            notes = :notes
        WHERE id = :id;
    """, params)


def delete_location(location_id: int) -> None:
    _execute("DELETE FROM location WHERE id = :id;", {"id": location_id})


def npc_rows() -> list[dict[str, Any]]:
    return _fetch("""
        SELECT
            n.id,
            n.name,
            n.alias,
            f.name AS faction,
            es.status_code AS status,
            l.name AS last_known_location,
            fs.session_number AS first_seen_session,
            n.description,
            n.is_named,
            n.notes
        FROM npc n
        LEFT JOIN faction f ON f.id = n.faction_id
        LEFT JOIN entity_status es ON es.id = n.entity_status_id
        LEFT JOIN location l ON l.id = n.last_known_location_id
        LEFT JOIN session fs ON fs.id = n.first_seen_session
        ORDER BY COALESCE(fs.session_number, 9999), n.name;
    """)


def npc_detail(npc_id: int) -> Optional[dict[str, Any]]:
    rows = _fetch("""
        SELECT
            n.id,
            n.name,
            n.alias,
            n.faction_id,
            n.entity_status_id,
            n.last_known_location_id,
            fs.session_number AS first_seen_session,
            n.description,
            n.is_named,
            n.notes
        FROM npc n
        LEFT JOIN session fs ON fs.id = n.first_seen_session
        WHERE n.id = :id;
    """, {"id": npc_id})
    return rows[0] if rows else None


def create_npc(values: dict[str, Any]) -> None:
    _execute("""
        INSERT INTO npc (
            name, alias, faction_id, entity_status_id, last_known_location_id,
            first_seen_session, description, is_named, notes
        )
        VALUES (
            :name, :alias, :faction_id, :entity_status_id, :last_known_location_id,
            (SELECT id FROM session WHERE session_number = :first_seen_session),
            :description, :is_named, :notes
        );
    """, values)


def update_npc(npc_id: int, values: dict[str, Any]) -> None:
    params = {**values, "id": npc_id}
    _execute("""
        UPDATE npc
        SET
            name = :name,
            alias = :alias,
            faction_id = :faction_id,
            entity_status_id = :entity_status_id,
            last_known_location_id = :last_known_location_id,
            first_seen_session = (SELECT id FROM session WHERE session_number = :first_seen_session),
            description = :description,
            is_named = :is_named,
            notes = :notes
        WHERE id = :id;
    """, params)


def delete_npc(npc_id: int) -> None:
    _execute("DELETE FROM npc WHERE id = :id;", {"id": npc_id})


def artifact_rows() -> list[dict[str, Any]]:
    return _fetch("""
        SELECT
            a.id,
            a.name,
            at.type_name AS artifact_type,
            ds.session_number AS discovered_session,
            a.description,
            a.lore_significance,
            a.is_sentient,
            a.is_cursed,
            a.is_infernal,
            holder.holder_name AS current_holder,
            NULLIF(a.notes, 'None') AS notes
        FROM artifact a
        LEFT JOIN artifact_type at ON at.id = a.artifact_type_id
        LEFT JOIN session ds ON ds.id = a.discovered_session
        LEFT JOIN LATERAL (
            SELECT COALESCE(pc.name, n.name, 'Unknown or lost') AS holder_name
            FROM artifact_custody ac
            LEFT JOIN player_character pc ON pc.id = ac.character_id
            LEFT JOIN npc n ON n.id = ac.npc_id
            WHERE ac.artifact_id = a.id
            ORDER BY ac.session_id DESC, ac.id DESC
            LIMIT 1
        ) holder ON TRUE
        ORDER BY COALESCE(ds.session_number, 9999), a.name;
    """)


def artifact_detail(artifact_id: int) -> Optional[dict[str, Any]]:
    rows = _fetch("""
        SELECT
            a.id,
            a.name,
            a.artifact_type_id,
            ds.session_number AS discovered_session,
            a.description,
            a.lore_significance,
            a.is_sentient,
            a.is_cursed,
            a.is_infernal,
            NULLIF(a.notes, 'None') AS notes
        FROM artifact a
        LEFT JOIN session ds ON ds.id = a.discovered_session
        WHERE a.id = :id;
    """, {"id": artifact_id})
    return rows[0] if rows else None


def create_artifact(values: dict[str, Any]) -> None:
    _execute("""
        INSERT INTO artifact (
            name, artifact_type_id, discovered_session, description,
            lore_significance, is_sentient, is_cursed, is_infernal, notes
        )
        VALUES (
            :name, :artifact_type_id,
            (SELECT id FROM session WHERE session_number = :discovered_session),
            :description, :lore_significance,
            :is_sentient, :is_cursed, :is_infernal, :notes
        );
    """, values)


def update_artifact(artifact_id: int, values: dict[str, Any]) -> None:
    params = {**values, "id": artifact_id}
    _execute("""
        UPDATE artifact
        SET
            name = :name,
            artifact_type_id = :artifact_type_id,
            discovered_session = (SELECT id FROM session WHERE session_number = :discovered_session),
            description = :description,
            lore_significance = :lore_significance,
            is_sentient = :is_sentient,
            is_cursed = :is_cursed,
            is_infernal = :is_infernal,
            notes = :notes
        WHERE id = :id;
    """, params)


def delete_artifact(artifact_id: int) -> None:
    _execute("DELETE FROM artifact WHERE id = :id;", {"id": artifact_id})


def lore_item_rows() -> list[dict[str, Any]]:
    return _fetch("""
        SELECT
            li.id,
            li.title,
            li.category,
            li.description,
            n.name AS source_npc,
            ds.session_number AS discovered_session,
            li.is_confirmed,
            li.notes
        FROM lore_item li
        LEFT JOIN npc n ON n.id = li.source_npc_id
        LEFT JOIN session ds ON ds.id = li.discovered_session
        ORDER BY
            CASE WHEN li.is_confirmed THEN 1 ELSE 0 END DESC,
            COALESCE(ds.session_number, 9999),
            COALESCE(li.category, ''),
            li.title;
    """)


def lore_item_detail(lore_item_id: int) -> Optional[dict[str, Any]]:
    rows = _fetch("""
        SELECT
            li.id,
            li.title,
            li.category,
            li.description,
            li.source_npc_id,
            ds.session_number AS discovered_session,
            li.is_confirmed,
            li.notes
        FROM lore_item li
        LEFT JOIN session ds ON ds.id = li.discovered_session
        WHERE li.id = :id;
    """, {"id": lore_item_id})
    return rows[0] if rows else None


def create_lore_item(values: dict[str, Any]) -> None:
    _execute("""
        INSERT INTO lore_item (
            title, category, description, source_npc_id,
            discovered_session, is_confirmed, notes
        )
        VALUES (
            :title, :category, :description, :source_npc_id,
            (SELECT id FROM session WHERE session_number = :discovered_session),
            :is_confirmed, :notes
        );
    """, values)


def update_lore_item(lore_item_id: int, values: dict[str, Any]) -> None:
    params = {**values, "id": lore_item_id}
    _execute("""
        UPDATE lore_item
        SET
            title = :title,
            category = :category,
            description = :description,
            source_npc_id = :source_npc_id,
            discovered_session = (SELECT id FROM session WHERE session_number = :discovered_session),
            is_confirmed = :is_confirmed,
            notes = :notes
        WHERE id = :id;
    """, params)


def delete_lore_item(lore_item_id: int) -> None:
    _execute("DELETE FROM lore_item WHERE id = :id;", {"id": lore_item_id})


def open_thread_statuses() -> list[dict[str, str]]:
    return OPEN_THREAD_STATUSES


def open_thread_types() -> list[str]:
    return OPEN_THREAD_TYPES


def lookup_definitions() -> list[dict[str, Any]]:
    return [
        {
            "key": definition["key"],
            "label": definition["label"],
            "description_column": definition["description_column"],
        }
        for definition in LOOKUP_TABLES.values()
    ]


def lookup_definition(lookup_key: str) -> dict[str, Any]:
    if lookup_key not in LOOKUP_TABLES:
        raise CanonReadError("Unknown lookup table.")
    return LOOKUP_TABLES[lookup_key]


def sql_quote(value: Any) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def _ensure_custom_lookup_table(definition: dict[str, Any]) -> None:
    if not definition.get("custom"):
        return
    table = definition["table"]
    value_column = definition["value_column"]
    description_column = definition["description_column"]
    _execute(f"""
        CREATE TABLE IF NOT EXISTS {table} (
            id SERIAL PRIMARY KEY,
            {value_column} VARCHAR(80) NOT NULL UNIQUE,
            {description_column} TEXT
        );
    """, {})
    for value, description in definition["seed"]:
        _execute(f"""
            INSERT INTO {table} ({value_column}, {description_column})
            VALUES (:value, :description)
            ON CONFLICT ({value_column}) DO NOTHING;
        """, {"value": value, "description": description})


def lookup_rows(lookup_key: str) -> list[dict[str, Any]]:
    definition = lookup_definition(lookup_key)
    _ensure_custom_lookup_table(definition)
    table = definition["table"]
    value_column = definition["value_column"]
    description_column = definition["description_column"]
    description_select = f"{description_column} AS description" if description_column else "NULL AS description"
    return _fetch(f"""
        SELECT id, {value_column} AS value, {description_select}
        FROM {table}
        ORDER BY {value_column};
    """)


def lookup_override_snapshot() -> dict[str, Any]:
    lookups: dict[str, Any] = {}
    for key, definition in LOOKUP_TABLES.items():
        rows = lookup_rows(key)
        values = []
        for row in rows:
            item = {"value": row["value"]}
            if definition["description_column"]:
                item["description"] = row.get("description") or ""
            values.append(item)
        lookups[key] = {
            "table": definition["table"],
            "value_column": definition["value_column"],
            "description_column": definition["description_column"],
            "values": values,
        }
    return {
        "description": "Campaign lookup values exported from Project Utilities. This file is used to regenerate init/20_lookup_overrides.sql after lookup edits.",
        "lookups": lookups,
    }


def lookup_override_sql(snapshot: dict[str, Any]) -> str:
    lines = [
        "-- Generated from campaign lookup_overrides.yaml by web_review.services.canon.",
        "-- Intended for fresh campaign database initialization after generic lookup seeds.",
        "",
    ]
    for key, payload in snapshot.get("lookups", {}).items():
        definition = LOOKUP_TABLES.get(key)
        if not definition:
            continue
        table = definition["table"]
        value_column = definition["value_column"]
        description_column = definition["description_column"]
        values = payload.get("values") or []
        quoted_values = ", ".join(sql_quote(item.get("value")) for item in values if item.get("value"))
        lines.append(f"-- {definition['label']}")
        if quoted_values:
            lines.append(f"DELETE FROM {table} WHERE {value_column} NOT IN ({quoted_values});")
        else:
            lines.append(f"DELETE FROM {table};")
        for item in values:
            value = item.get("value")
            if not value:
                continue
            if description_column:
                lines.append(
                    f"INSERT INTO {table} ({value_column}, {description_column}) "
                    f"VALUES ({sql_quote(value)}, {sql_quote(item.get('description') or '')}) "
                    f"ON CONFLICT ({value_column}) DO UPDATE SET {description_column} = EXCLUDED.{description_column};"
                )
            else:
                lines.append(
                    f"INSERT INTO {table} ({value_column}) "
                    f"VALUES ({sql_quote(value)}) "
                    f"ON CONFLICT ({value_column}) DO NOTHING;"
                )
        lines.append("")
    return "\n".join(lines)


def persist_lookup_overrides() -> None:
    snapshot = lookup_override_snapshot()
    LOOKUP_OVERRIDES_PATH.write_text(
        yaml.safe_dump(snapshot, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    LOOKUP_OVERRIDES_SQL_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOOKUP_OVERRIDES_SQL_PATH.write_text(lookup_override_sql(snapshot), encoding="utf-8")


def lookup_detail(lookup_key: str, lookup_id: int) -> Optional[dict[str, Any]]:
    definition = lookup_definition(lookup_key)
    _ensure_custom_lookup_table(definition)
    table = definition["table"]
    value_column = definition["value_column"]
    description_column = definition["description_column"]
    description_select = f"{description_column} AS description" if description_column else "NULL AS description"
    rows = _fetch(f"""
        SELECT id, {value_column} AS value, {description_select}
        FROM {table}
        WHERE id = :id;
    """, {"id": lookup_id})
    return rows[0] if rows else None


def create_lookup_value(lookup_key: str, value: str, description: str = "") -> None:
    definition = lookup_definition(lookup_key)
    _ensure_custom_lookup_table(definition)
    table = definition["table"]
    value_column = definition["value_column"]
    description_column = definition["description_column"]
    if description_column:
        _execute(f"""
            INSERT INTO {table} ({value_column}, {description_column})
            VALUES (:value, :description);
        """, {"value": value, "description": description})
    else:
        _execute(f"""
            INSERT INTO {table} ({value_column})
            VALUES (:value);
        """, {"value": value})
    persist_lookup_overrides()


def update_lookup_value(lookup_key: str, lookup_id: int, value: str, description: str = "") -> None:
    definition = lookup_definition(lookup_key)
    _ensure_custom_lookup_table(definition)
    table = definition["table"]
    value_column = definition["value_column"]
    description_column = definition["description_column"]
    if description_column:
        _execute(f"""
            UPDATE {table}
            SET {value_column} = :value,
                {description_column} = :description
            WHERE id = :id;
        """, {"id": lookup_id, "value": value, "description": description})
    else:
        _execute(f"""
            UPDATE {table}
            SET {value_column} = :value
            WHERE id = :id;
        """, {"id": lookup_id, "value": value})
    persist_lookup_overrides()


def delete_lookup_value(lookup_key: str, lookup_id: int) -> None:
    definition = lookup_definition(lookup_key)
    _ensure_custom_lookup_table(definition)
    _execute(f"DELETE FROM {definition['table']} WHERE id = :id;", {"id": lookup_id})
    persist_lookup_overrides()


def open_thread_rows() -> list[dict[str, Any]]:
    return _fetch("""
        SELECT
            ot.id,
            ot.title,
            ot.thread_type,
            ot.status,
            fs.session_number AS first_session,
            ls.session_number AS last_session,
            l.name AS related_location,
            ot.description,
            ot.resolution,
            ot.notes
        FROM open_thread ot
        LEFT JOIN session fs ON fs.id = ot.first_session_id
        LEFT JOIN session ls ON ls.id = ot.last_session_id
        LEFT JOIN location l ON l.id = ot.related_location_id
        ORDER BY
            CASE ot.status
                WHEN 'open' THEN 1
                WHEN 'unknown' THEN 2
                WHEN 'superseded' THEN 3
                WHEN 'resolved' THEN 4
                ELSE 5
            END,
            COALESCE(fs.session_number, 9999),
            ot.title;
    """)


def open_thread_detail(thread_id: int) -> Optional[dict[str, Any]]:
    rows = _fetch("""
        SELECT
            ot.id,
            ot.title,
            ot.thread_type,
            ot.status,
            fs.session_number AS first_session,
            ls.session_number AS last_session,
            ot.related_location_id,
            ot.description,
            ot.resolution,
            ot.notes
        FROM open_thread ot
        LEFT JOIN session fs ON fs.id = ot.first_session_id
        LEFT JOIN session ls ON ls.id = ot.last_session_id
        WHERE ot.id = :id;
    """, {"id": thread_id})
    return rows[0] if rows else None


def create_open_thread(values: dict[str, Any]) -> None:
    _unsuppress_open_thread_title(values["title"])
    _execute("""
        INSERT INTO open_thread (
            title, thread_type, status, first_session_id, last_session_id,
            related_location_id, description, resolution, notes
        )
        VALUES (
            :title, :thread_type, :status,
            (SELECT id FROM session WHERE session_number = :first_session),
            (SELECT id FROM session WHERE session_number = :last_session),
            :related_location_id, :description, :resolution, :notes
        );
    """, values)


def update_open_thread(thread_id: int, values: dict[str, Any]) -> None:
    _unsuppress_open_thread_title(values["title"])
    params = {**values, "id": thread_id}
    _execute("""
        UPDATE open_thread
        SET
            title = :title,
            thread_type = :thread_type,
            status = :status,
            first_session_id = (SELECT id FROM session WHERE session_number = :first_session),
            last_session_id = (SELECT id FROM session WHERE session_number = :last_session),
            related_location_id = :related_location_id,
            description = :description,
            resolution = :resolution,
            notes = :notes
        WHERE id = :id;
    """, params)


def delete_open_thread(thread_id: int) -> None:
    detail = open_thread_detail(thread_id)
    _execute("DELETE FROM open_thread WHERE id = :id;", {"id": thread_id})
    if detail and detail.get("title"):
        _suppress_open_thread_title(detail["title"])


def _load_canon_decisions() -> dict[str, Any]:
    if not CANON_DECISIONS_PATH.exists():
        return {}
    return yaml.safe_load(CANON_DECISIONS_PATH.read_text(encoding="utf-8")) or {}


def _save_canon_decisions(data: dict[str, Any]) -> None:
    CANON_DECISIONS_PATH.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _suppress_open_thread_title(title: str) -> None:
    title = title.strip()
    if not title:
        return
    data = _load_canon_decisions()
    suppressed = data.setdefault("suppressed_open_threads", [])
    for item in suppressed:
        if item.get("title") == title:
            item["status"] = "deleted"
            item["applied_on"] = date.today().isoformat()
            _save_canon_decisions(data)
            return
    suppressed.append({
        "title": title,
        "status": "deleted",
        "reason": "Deleted from Open Threads UI; prevent canonical seed reload from resurrecting it.",
        "decided_from": "web_review",
        "applied_on": date.today().isoformat(),
    })
    _save_canon_decisions(data)


def _unsuppress_open_thread_title(title: str) -> None:
    title = title.strip()
    if not title or not CANON_DECISIONS_PATH.exists():
        return
    data = _load_canon_decisions()
    suppressed = data.get("suppressed_open_threads") or []
    filtered = [item for item in suppressed if item.get("title") != title]
    if len(filtered) == len(suppressed):
        return
    data["suppressed_open_threads"] = filtered
    _save_canon_decisions(data)


def _session_span_label(session_number: int, outcome: str) -> str:
    match = re.search(r"continues_into_session(\d+)", outcome or "")
    if not match:
        return f"Session {session_number:02d}"
    return f"Session {session_number:02d} -> Session {int(match.group(1)):02d}"


def combat_encounter_rows() -> list[dict[str, Any]]:
    rows = _fetch("""
        SELECT
            c.id,
            s.session_number,
            s.title AS session_title,
            c.title,
            c.subtype,
            l.name AS location,
            c.participants,
            c.outcome,
            c.confidence,
            c.notes,
            e.name AS enemy_name,
            e.enemy_type,
            ee.quantity,
            ee.quantity_killed,
            ee.outcome AS enemy_outcome,
            ee.confidence AS enemy_confidence,
            ee.notes AS enemy_notes
        FROM encounter c
        JOIN session s ON s.id = c.session_id
        LEFT JOIN location l ON l.id = c.location_id
        LEFT JOIN event_enemy ee ON ee.event_id = c.event_id
        LEFT JOIN enemy e ON e.id = ee.enemy_id
        WHERE c.encounter_type = 'combat'
        ORDER BY s.session_number, c.id, e.name;
    """)
    encounters: dict[int, dict[str, Any]] = {}
    for row in rows:
        encounter = encounters.setdefault(row["id"], {
            "id": row["id"],
            "session_number": row["session_number"],
            "session_title": row["session_title"],
            "session_span": _session_span_label(row["session_number"], row.get("outcome") or ""),
            "title": row["title"],
            "subtype": row["subtype"],
            "location": row["location"],
            "participants": row["participants"],
            "outcome": row["outcome"],
            "confidence": row["confidence"],
            "notes": row["notes"],
            "known_enemy_total": 0,
            "has_unknown_quantity": False,
            "enemies": [],
        })
        if not row.get("enemy_name"):
            continue
        quantity = row.get("quantity")
        if quantity is None:
            encounter["has_unknown_quantity"] = True
        else:
            encounter["known_enemy_total"] += quantity
        quantity_killed = row.get("quantity_killed")
        encounter["enemies"].append({
            "name": row["enemy_name"],
            "enemy_type": row["enemy_type"],
            "quantity": quantity,
            "quantity_killed": quantity_killed,
            "outcome": row["enemy_outcome"],
            "confidence": row["enemy_confidence"],
            "notes": row["enemy_notes"],
        })
    return list(encounters.values())


def combat_encounter_detail(encounter_id: int) -> Optional[dict[str, Any]]:
    rows = _fetch("""
        SELECT
            c.id,
            s.session_number,
            c.event_id,
            c.title,
            c.subtype,
            c.location_id,
            c.participants,
            c.outcome,
            c.confidence,
            c.notes
        FROM encounter c
        JOIN session s ON s.id = c.session_id
        WHERE c.id = :id;
    """, {"id": encounter_id})
    if not rows:
        return None
    detail = rows[0]
    detail["enemies"] = _fetch("""
        SELECT
            e.name,
            e.enemy_type,
            ee.quantity,
            ee.quantity_killed,
            ee.outcome,
            ee.confidence,
            ee.notes
        FROM event_enemy ee
        JOIN enemy e ON e.id = ee.enemy_id
        WHERE ee.event_id = :event_id
        ORDER BY e.name;
    """, {"event_id": detail["event_id"]}) if detail.get("event_id") else []
    return detail


def _create_combat_event(values: dict[str, Any]) -> int:
    row = _fetch_one_write("""
        INSERT INTO session_event (
            session_id, event_type_id, sequence_order, location_id,
            description, significance, notes
        )
        SELECT
            s.id,
            (SELECT id FROM event_type WHERE type_name = 'combat' LIMIT 1),
            COALESCE((SELECT MAX(sequence_order) + 1 FROM session_event WHERE session_id = s.id), 1),
            :location_id,
            :title,
            3,
            :event_notes
        FROM session s
        WHERE s.session_number = :session_number
        RETURNING id;
    """, {
        "session_number": values["session_number"],
        "location_id": values.get("location_id"),
        "title": values["title"],
        "event_notes": "Created from Combat Encounters UI.",
    })
    if not row.get("id"):
        raise CanonWriteError("Could not create combat event. Session may not exist.")
    return int(row["id"])


def _ensure_enemy(enemy: dict[str, Any], session_number: int) -> int:
    name = (enemy.get("name") or "").strip()
    if not name:
        raise CanonWriteError("Enemy name is required.")
    rows = _fetch("SELECT id FROM enemy WHERE lower(name) = lower(:name) ORDER BY id LIMIT 1;", {"name": name})
    if rows:
        enemy_id = int(rows[0]["id"])
        _execute("""
            UPDATE enemy
            SET
                enemy_type = COALESCE(NULLIF(:enemy_type, ''), enemy.enemy_type),
                first_encountered_session = COALESCE(enemy.first_encountered_session, (SELECT id FROM session WHERE session_number = :session_number))
            WHERE id = :id;
        """, {"id": enemy_id, "enemy_type": enemy.get("enemy_type") or "", "session_number": session_number})
        return enemy_id
    row = _fetch_one_write("""
        INSERT INTO enemy (
            name, enemy_type, threat_level_id, entity_status_id,
            first_encountered_session, description, notes
        )
        VALUES (
            :name,
            :enemy_type,
            (SELECT id FROM threat_level WHERE level_code = 'minor' LIMIT 1),
            (SELECT id FROM entity_status WHERE status_code = 'unknown' LIMIT 1),
            (SELECT id FROM session WHERE session_number = :session_number),
            :description,
            :notes
        )
        RETURNING id;
    """, {
        "name": name,
        "enemy_type": enemy.get("enemy_type") or "",
        "session_number": session_number,
        "description": "Generic or encounter-level enemy tracked from Combat Encounters UI.",
        "notes": "Created from Combat Encounters UI.",
    })
    if not row.get("id"):
        raise CanonWriteError("Could not create enemy row.")
    return int(row["id"])


def _replace_combat_enemies(event_id: int, session_number: int, enemies: list[dict[str, Any]]) -> None:
    _execute("DELETE FROM event_enemy WHERE event_id = :event_id;", {"event_id": event_id})
    for enemy in enemies:
        if not (enemy.get("name") or "").strip():
            continue
        enemy_id = _ensure_enemy(enemy, session_number)
        _execute("""
            INSERT INTO event_enemy (
                event_id, enemy_id, outcome, quantity, quantity_killed, confidence, notes
            )
            VALUES (
                :event_id, :enemy_id, :outcome, :quantity, :quantity_killed, :confidence, :notes
            )
            ON CONFLICT (event_id, enemy_id) DO UPDATE SET
                outcome = EXCLUDED.outcome,
                quantity = EXCLUDED.quantity,
                quantity_killed = EXCLUDED.quantity_killed,
                confidence = EXCLUDED.confidence,
                notes = EXCLUDED.notes;
        """, {
            "event_id": event_id,
            "enemy_id": enemy_id,
            "outcome": enemy.get("outcome") or "unknown",
            "quantity": enemy.get("quantity"),
            "quantity_killed": enemy.get("quantity_killed"),
            "confidence": enemy.get("confidence") or "medium",
            "notes": enemy.get("notes") or "",
        })


def create_combat_encounter(values: dict[str, Any], enemies: list[dict[str, Any]]) -> None:
    event_id = _create_combat_event(values)
    _execute("""
        INSERT INTO encounter (
            session_id, event_id, encounter_type, subtype, location_id,
            title, participants, outcome, confidence, notes
        )
        SELECT
            s.id, :event_id, 'combat', :subtype, :location_id,
            :title, :participants, :outcome, :confidence, :notes
        FROM session s
        WHERE s.session_number = :session_number;
    """, {**values, "event_id": event_id})
    _replace_combat_enemies(event_id, int(values["session_number"]), enemies)


def update_combat_encounter(encounter_id: int, values: dict[str, Any], enemies: list[dict[str, Any]]) -> None:
    detail = combat_encounter_detail(encounter_id)
    if not detail:
        raise CanonWriteError("Combat encounter not found.")
    event_id = detail.get("event_id") or _create_combat_event(values)
    _execute("""
        UPDATE session_event
        SET
            session_id = (SELECT id FROM session WHERE session_number = :session_number),
            location_id = :location_id,
            description = :title
        WHERE id = :event_id;
    """, {**values, "event_id": event_id})
    _execute("""
        UPDATE encounter
        SET
            session_id = (SELECT id FROM session WHERE session_number = :session_number),
            event_id = :event_id,
            subtype = :subtype,
            location_id = :location_id,
            title = :title,
            participants = :participants,
            outcome = :outcome,
            confidence = :confidence,
            notes = :notes
        WHERE id = :id;
    """, {**values, "id": encounter_id, "event_id": event_id})
    _replace_combat_enemies(event_id, int(values["session_number"]), enemies)


def delete_combat_encounter(encounter_id: int) -> None:
    detail = combat_encounter_detail(encounter_id)
    if not detail:
        return
    if detail.get("event_id"):
        _execute("DELETE FROM event_enemy WHERE event_id = :event_id;", {"event_id": detail["event_id"]})
    _execute("DELETE FROM encounter WHERE id = :id;", {"id": encounter_id})


def murder_hobo_count(encounters: list[dict[str, Any]]) -> dict[str, Any]:
    total = 0
    unknown_rows = 0
    for encounter in encounters:
        for enemy in encounter.get("enemies", []):
            quantity_killed = enemy.get("quantity_killed")
            if quantity_killed is not None:
                total += quantity_killed
                continue
            if (enemy.get("outcome") or "").lower() == "killed":
                unknown_rows += 1
    return {
        "total": total,
        "unknown_rows": unknown_rows,
        "label": f"{total}+ unknown" if unknown_rows else str(total),
    }


def campaign_timeline() -> dict[str, Any]:
    session_columns = {
        row["column_name"]
        for row in _fetch(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'session';
            """
        )
    }
    start_location_join = ""
    end_location_join = ""
    start_location_select = "NULL AS start_location"
    end_location_select = "NULL AS end_location"
    if "start_location_id" in session_columns:
        start_location_select = "sl.name AS start_location"
        start_location_join = "LEFT JOIN location sl ON sl.id = s.start_location_id"
    if "end_location_id" in session_columns:
        end_location_select = "el.name AS end_location"
        end_location_join = "LEFT JOIN location el ON el.id = s.end_location_id"

    sessions = _fetch(f"""
        SELECT
            s.id,
            s.session_number,
            s.session_date,
            s.in_game_date,
            s.title,
            s.summary,
            s.notes,
            l.name AS primary_location,
            {start_location_select},
            {end_location_select}
        FROM session s
        LEFT JOIN location l ON l.id = s.location_id
        {start_location_join}
        {end_location_join}
        ORDER BY s.session_number;
    """)
    events = _fetch("""
        SELECT
            e.session_id,
            e.sequence_order,
            et.type_name AS event_type,
            l.name AS location,
            e.description,
            e.significance
        FROM session_event e
        LEFT JOIN event_type et ON et.id = e.event_type_id
        LEFT JOIN location l ON l.id = e.location_id
        WHERE e.significance >= 4
        ORDER BY e.session_id, e.sequence_order, e.id;
    """)
    travels = _fetch("""
        SELECT
            tr.session_id,
            fl.name AS from_location,
            tl.name AS to_location,
            tr.travel_method,
            tr.duration_days,
            tr.duration_confidence,
            tr.duration_basis,
            tr.notes
        FROM travel_log tr
        LEFT JOIN location fl ON fl.id = tr.from_location_id
        LEFT JOIN location tl ON tl.id = tr.to_location_id
        ORDER BY tr.session_id, tr.id;
    """)

    events_by_session: dict[int, list[dict[str, Any]]] = {}
    for event in events:
        events_by_session.setdefault(event["session_id"], []).append(event)

    travel_by_session: dict[int, list[dict[str, Any]]] = {}
    for travel in travels:
        travel_by_session.setdefault(travel["session_id"], []).append(travel)

    rows: list[dict[str, Any]] = []
    total_travel_days = 0
    known_travel_segments = 0
    for session in sessions:
        session_travel = travel_by_session.get(session["id"], [])
        for travel in session_travel:
            if travel.get("duration_days") is not None:
                total_travel_days += travel["duration_days"]
                known_travel_segments += 1
        session_events = events_by_session.get(session["id"], [])
        in_game_date_display = timeline_in_game_date_display(session["in_game_date"])
        in_game_date_earliest, in_game_date_latest = timeline_in_game_date_bounds(session["in_game_date"])
        rows.append({
            "session_number": session["session_number"],
            "session_label": f"Session {session['session_number']:02d}",
            "session_date": session["session_date"],
            "in_game_date": session["in_game_date"],
            "in_game_date_display": in_game_date_display or session["in_game_date"],
            "in_game_date_earliest": in_game_date_earliest,
            "in_game_date_latest": in_game_date_latest,
            "title": session["title"],
            "summary": session["summary"],
            "notes": session["notes"],
            "primary_location": session["primary_location"],
            "start_location": session["start_location"],
            "end_location": session["end_location"],
            "travel": session_travel,
            "key_events": session_events,
            "event_count": len(session_events),
        })

    first_session = rows[0] if rows else None
    last_session = rows[-1] if rows else None
    return {
        "stats": {
            "session_count": len(rows),
            "total_travel_days": total_travel_days,
            "known_travel_segments": known_travel_segments,
            "first_in_game_date": first_session["in_game_date_earliest"] if first_session else None,
            "latest_in_game_date": last_session["in_game_date_latest"] if last_session else None,
            "current_location": (last_session["end_location"] or last_session["primary_location"]) if last_session else None,
        },
        "rows": rows,
    }


def ensure_songbook_schema() -> None:
    _execute("ALTER TABLE song ADD COLUMN IF NOT EXISTS tempo VARCHAR(60);", {})
    _execute("ALTER TABLE song ADD COLUMN IF NOT EXISTS order_number INTEGER;", {})
    _execute("UPDATE song SET order_number = song_number WHERE order_number IS NULL;", {})
    _execute("DROP VIEW IF EXISTS v_songbook;", {})
    _execute("ALTER TABLE song ALTER COLUMN musical_key TYPE VARCHAR(120);", {})
    _execute("ALTER TABLE song ALTER COLUMN meter TYPE VARCHAR(120);", {})
    _execute("ALTER TABLE song ALTER COLUMN tempo TYPE VARCHAR(120);", {})
    _execute("""
        CREATE VIEW v_songbook AS
            SELECT
                s.id,
                s.song_number,
                s.order_number,
                s.title,
                s.style_id,
                ss.style_name AS style,
                s.category_id,
                sc.category_name AS category,
                s.song_type,
                s.short_description,
                s.long_description,
                s.summary,
                s.suno_prompt,
                s.musical_key,
                s.meter,
                s.tempo,
                s.instrumentation,
                s.lyrics_local_path,
                s.mp3_local_path,
                s.mp3_url,
                s.lyrics_url,
                ws.session_number AS written_session,
                s.in_world_context,
                s.is_performed
            FROM song s
            LEFT JOIN song_style ss ON s.style_id = ss.id
            LEFT JOIN song_category sc ON s.category_id = sc.id
            LEFT JOIN session ws ON ws.id = s.written_session;
    """, {})


def songbook_rows() -> list[dict[str, Any]]:
    rows = _fetch("""
        SELECT
            id,
            song_number,
            order_number,
            title,
            style_id,
            style,
            category_id,
            category,
            song_type,
            short_description,
            long_description,
            summary,
            suno_prompt,
            musical_key,
            meter,
            tempo,
            instrumentation,
            lyrics_local_path,
            mp3_local_path,
            mp3_url,
            lyrics_url,
            written_session,
            in_world_context,
            is_performed
        FROM v_songbook
        ORDER BY COALESCE(order_number, song_number), song_number;
    """)
    for row in rows:
        row["has_local_audio"] = bool(row.get("mp3_local_path") and _safe_repo_path(row["mp3_local_path"]).exists())
        row["has_local_lyrics"] = bool(row.get("lyrics_local_path") and _safe_repo_path(row["lyrics_local_path"]).exists())
    return rows


def songbook_foreword() -> dict[str, str]:
    rows = _fetch("""
        SELECT title, foreword_path, foreword_text, notes
        FROM songbook_front_matter
        ORDER BY id
        LIMIT 1;
    """)
    if not rows:
        return {"title": "", "text": "", "path": "", "notes": ""}

    row = rows[0]
    text = row.get("foreword_text") or ""
    path = row.get("foreword_path") or ""
    if path:
        foreword_path = _safe_repo_path(path)
        if foreword_path.exists():
            text = foreword_path.read_text(encoding="utf-8-sig")

    return {
        "title": row.get("title") or "",
        "text": text.strip(),
        "path": path,
        "notes": row.get("notes") or "",
    }


def songbook_detail(song_number: int) -> Optional[dict[str, Any]]:
    rows = _fetch("""
        SELECT
            id,
            song_number,
            order_number,
            title,
            style_id,
            style,
            category_id,
            category,
            song_type,
            short_description,
            long_description,
            summary,
            suno_prompt,
            musical_key,
            meter,
            tempo,
            instrumentation,
            lyrics_local_path,
            mp3_local_path,
            mp3_url,
            lyrics_url,
            written_session,
            in_world_context,
            is_performed
        FROM v_songbook
        WHERE song_number = :song_number;
    """, {"song_number": song_number})
    if not rows:
        return None
    row = rows[0]
    row["has_local_audio"] = bool(row.get("mp3_local_path") and _safe_repo_path(row["mp3_local_path"]).exists())
    row["has_local_lyrics"] = bool(row.get("lyrics_local_path") and _safe_repo_path(row["lyrics_local_path"]).exists())
    return row


def next_song_number() -> int:
    ensure_songbook_schema()
    rows = _fetch("SELECT COALESCE(MAX(song_number), 0) + 1 AS value FROM song;")
    return int(rows[0]["value"])


def next_song_order_number() -> int:
    ensure_songbook_schema()
    rows = _fetch("SELECT COALESCE(MAX(order_number), MAX(song_number), 0) + 1 AS value FROM song;")
    return int(rows[0]["value"])


def create_song(values: dict[str, Any]) -> None:
    ensure_songbook_schema()
    if not values.get("title"):
        raise CanonWriteError("Song title is required.")
    values = {
        **values,
        "song_number": values.get("song_number") or next_song_number(),
        "order_number": values.get("order_number") or next_song_order_number(),
    }
    _execute("""
        INSERT INTO song (
            song_number, order_number, title, style_id, category_id,
            summary, lyrics_url, mp3_url, mp3_local_path, written_session,
            in_world_context, is_performed, song_type, short_description,
            long_description, suno_prompt, musical_key, meter,
            instrumentation, lyrics_local_path, tempo
        )
        VALUES (
            :song_number, :order_number, :title, :style_id, :category_id,
            :summary, :lyrics_url, :mp3_url, :mp3_local_path,
            (SELECT id FROM session WHERE session_number = :written_session),
            :in_world_context, :is_performed, :song_type, :short_description,
            :long_description, :suno_prompt, :musical_key, :meter,
            :instrumentation, :lyrics_local_path, :tempo
        );
    """, values)
    normalize_song_order()


def update_song(song_number: int, values: dict[str, Any]) -> None:
    ensure_songbook_schema()
    if not values.get("title"):
        raise CanonWriteError("Song title is required.")
    _execute("""
        UPDATE song
        SET
            order_number = :order_number,
            title = :title,
            style_id = :style_id,
            category_id = :category_id,
            summary = :summary,
            lyrics_url = :lyrics_url,
            mp3_url = :mp3_url,
            mp3_local_path = :mp3_local_path,
            written_session = (SELECT id FROM session WHERE session_number = :written_session),
            in_world_context = :in_world_context,
            is_performed = :is_performed,
            song_type = :song_type,
            short_description = :short_description,
            long_description = :long_description,
            suno_prompt = :suno_prompt,
            musical_key = :musical_key,
            meter = :meter,
            instrumentation = :instrumentation,
            lyrics_local_path = :lyrics_local_path,
            tempo = :tempo
        WHERE song_number = :song_number;
    """, {**values, "song_number": song_number})
    normalize_song_order()


def delete_song(song_number: int) -> None:
    ensure_songbook_schema()
    _execute("DELETE FROM song WHERE song_number = :song_number;", {"song_number": song_number})
    normalize_song_order()


def normalize_song_order() -> None:
    ensure_songbook_schema()
    rows = _fetch("""
        SELECT id
        FROM song
        ORDER BY COALESCE(order_number, song_number), song_number, id;
    """)
    statements = [
        ("UPDATE song SET order_number = :temporary_order WHERE id = :id;", {"id": row["id"], "temporary_order": -(index + 1)})
        for index, row in enumerate(rows)
    ]
    statements.extend(
        ("UPDATE song SET order_number = :order_number WHERE id = :id;", {"id": row["id"], "order_number": index + 1})
        for index, row in enumerate(rows)
    )
    _execute_transaction(statements)


def move_song(song_number: int, direction: str) -> None:
    ensure_songbook_schema()
    rows = _fetch("""
        SELECT song_number, order_number
        FROM song
        ORDER BY COALESCE(order_number, song_number), song_number;
    """)
    index = next((idx for idx, row in enumerate(rows) if row["song_number"] == song_number), None)
    if index is None:
        raise CanonWriteError("Song not found.")
    target_index = index - 1 if direction == "up" else index + 1
    if target_index < 0 or target_index >= len(rows):
        return
    rows[index], rows[target_index] = rows[target_index], rows[index]
    statements = [
        (
            "UPDATE song SET order_number = :order_number WHERE song_number = :song_number;",
            {"song_number": row["song_number"], "order_number": order_number},
        )
        for order_number, row in enumerate(rows, start=1)
    ]
    _execute_transaction(statements)


def _safe_repo_path(path_value: str) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = REPO_ROOT / path
    resolved = path.resolve()
    if not resolved.exists():
        legacy_prefix = Path("knowledge") / "Faban"
        legacy_path = Path(path_value)
        if not legacy_path.is_absolute() and legacy_path.parts[:2] == legacy_prefix.parts:
            migrated = campaign_path(*legacy_path.parts[2:]).resolve()
            if migrated.exists():
                resolved = migrated
    if REPO_ROOT.resolve() not in [resolved, *resolved.parents]:
        raise CanonReadError("Songbook asset path is outside the repository.")
    return resolved


def songbook_asset_path(song_number: int, asset: str) -> Optional[Path]:
    detail = songbook_detail(song_number)
    if not detail:
        return None
    column = {
        "audio": "mp3_local_path",
        "lyrics": "lyrics_local_path",
    }.get(asset)
    if column is None or not detail.get(column):
        return None
    path = _safe_repo_path(detail[column])
    return path if path.exists() else None


def songbook_lyrics(song_number: int) -> Optional[str]:
    path = songbook_asset_path(song_number, "lyrics")
    if path is None:
        return None
    return path.read_text(encoding="utf-8-sig")


def event_types() -> list[str]:
    rows = _fetch("SELECT type_name FROM event_type ORDER BY type_name;")
    return [row["type_name"] for row in rows]
