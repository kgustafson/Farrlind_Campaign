import os
from collections.abc import Mapping
from typing import Any, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from raglib.campaign import campaign_database_url

DEFAULT_DATABASE_URL = campaign_database_url()


def database_url() -> str:
    return os.environ.get("FARRLIND_DATABASE_URL", DEFAULT_DATABASE_URL)


def make_engine(url: Optional[str] = None) -> Engine:
    return create_engine(url or database_url(), pool_pre_ping=True)


def fetch_all(sql: str, params: Optional[Mapping[str, Any]] = None, engine: Optional[Engine] = None) -> list[dict[str, Any]]:
    active_engine = engine or make_engine()
    with active_engine.connect() as connection:
        result = connection.execute(text(sql), params or {})
        return [dict(row._mapping) for row in result]


def execute(sql: str, params: Optional[Mapping[str, Any]] = None, engine: Optional[Engine] = None) -> None:
    active_engine = engine or make_engine()
    with active_engine.begin() as connection:
        connection.execute(text(sql), params or {})
