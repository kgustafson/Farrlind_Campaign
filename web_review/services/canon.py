import re
from datetime import date
from pathlib import Path
from typing import Any, Optional

import yaml
from sqlalchemy.exc import SQLAlchemyError

from web_review import db


class CanonReadError(RuntimeError):
    pass


class CanonWriteError(RuntimeError):
    pass


REPO_ROOT = Path(__file__).resolve().parents[2]
CANON_DECISIONS_PATH = REPO_ROOT / "knowledge" / "Faban" / "canon_decisions.yaml"
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


def artifact_types() -> list[dict[str, Any]]:
    return _fetch("SELECT id, type_name FROM artifact_type ORDER BY type_name;")


def entity_statuses() -> list[dict[str, Any]]:
    return _fetch("SELECT id, status_code, description FROM entity_status ORDER BY status_code;")


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
            l.first_visited_session,
            l.notes
        FROM location l
        LEFT JOIN location_type lt ON lt.id = l.location_type_id
        LEFT JOIN location parent ON parent.id = l.parent_location_id
        ORDER BY l.name;
    """)


def location_detail(location_id: int) -> Optional[dict[str, Any]]:
    rows = _fetch("""
        SELECT
            id,
            name,
            location_type_id,
            parent_location_id,
            description,
            is_underwater,
            is_feywild,
            first_visited_session,
            notes
        FROM location
        WHERE id = :id;
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
            :is_underwater, :is_feywild, :first_visited_session, :notes
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
            first_visited_session = :first_visited_session,
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


def delete_lookup_value(lookup_key: str, lookup_id: int) -> None:
    definition = lookup_definition(lookup_key)
    _ensure_custom_lookup_table(definition)
    _execute(f"DELETE FROM {definition['table']} WHERE id = :id;", {"id": lookup_id})


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
        encounter["enemies"].append({
            "name": row["enemy_name"],
            "enemy_type": row["enemy_type"],
            "quantity": quantity,
            "outcome": row["enemy_outcome"],
            "confidence": row["enemy_confidence"],
            "notes": row["enemy_notes"],
        })
    return list(encounters.values())


def murder_hobo_count(encounters: list[dict[str, Any]]) -> dict[str, Any]:
    kill_outcomes = {"killed", "defeated"}
    total = 0
    unknown_rows = 0
    for encounter in encounters:
        for enemy in encounter.get("enemies", []):
            if (enemy.get("outcome") or "").lower() not in kill_outcomes:
                continue
            if enemy.get("quantity") is None:
                unknown_rows += 1
                continue
            total += enemy["quantity"]
    return {
        "total": total,
        "unknown_rows": unknown_rows,
        "label": f"{total}+ unknown" if unknown_rows else str(total),
    }


def campaign_timeline() -> dict[str, Any]:
    sessions = _fetch("""
        SELECT
            s.id,
            s.session_number,
            s.session_date,
            s.in_game_date,
            s.title,
            s.summary,
            l.name AS primary_location
        FROM session s
        LEFT JOIN location l ON l.id = s.location_id
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
            "primary_location": session["primary_location"],
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
            "current_location": last_session["primary_location"] if last_session else None,
        },
        "rows": rows,
    }


def songbook_rows() -> list[dict[str, Any]]:
    rows = _fetch("""
        SELECT
            song_number,
            title,
            style,
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
            lyrics_url
        FROM v_songbook
        ORDER BY song_number;
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
            song_number,
            title,
            style,
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
            lyrics_url
        FROM v_songbook
        WHERE song_number = :song_number;
    """, {"song_number": song_number})
    if not rows:
        return None
    row = rows[0]
    row["has_local_audio"] = bool(row.get("mp3_local_path") and _safe_repo_path(row["mp3_local_path"]).exists())
    row["has_local_lyrics"] = bool(row.get("lyrics_local_path") and _safe_repo_path(row["lyrics_local_path"]).exists())
    return row


def _safe_repo_path(path_value: str) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = REPO_ROOT / path
    resolved = path.resolve()
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
