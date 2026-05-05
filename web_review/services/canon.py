from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from web_review import db


class CanonReadError(RuntimeError):
    pass


def _fetch(sql: str) -> list[dict[str, Any]]:
    try:
        return db.fetch_all(sql)
    except SQLAlchemyError as exc:
        raise CanonReadError(str(exc)) from exc


def locations() -> list[str]:
    rows = _fetch("SELECT name FROM location ORDER BY name;")
    return [row["name"] for row in rows]


def event_types() -> list[str]:
    rows = _fetch("SELECT type_name FROM event_type ORDER BY type_name;")
    return [row["type_name"] for row in rows]
