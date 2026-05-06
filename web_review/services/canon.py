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


def event_types() -> list[str]:
    rows = _fetch("SELECT type_name FROM event_type ORDER BY type_name;")
    return [row["type_name"] for row in rows]
