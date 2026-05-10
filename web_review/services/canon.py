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


def event_types() -> list[str]:
    rows = _fetch("SELECT type_name FROM event_type ORDER BY type_name;")
    return [row["type_name"] for row in rows]
