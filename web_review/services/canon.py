from typing import Any, Optional

from sqlalchemy.exc import SQLAlchemyError

from web_review import db


class CanonReadError(RuntimeError):
    pass


class CanonWriteError(RuntimeError):
    pass


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


def event_types() -> list[str]:
    rows = _fetch("SELECT type_name FROM event_type ORDER BY type_name;")
    return [row["type_name"] for row in rows]
