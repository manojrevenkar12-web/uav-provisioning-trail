"""PostgreSQL access for the traceability server."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from importlib import resources
from typing import Any

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import Connection

from ..config import database_url


@lru_cache
def engine() -> Engine:
    return create_engine(database_url(), pool_pre_ping=True, pool_size=10, max_overflow=10)


def reset_engine() -> None:
    engine.cache_clear()


@contextmanager
def begin() -> Iterator[Connection]:
    with engine().begin() as c:
        yield c


def bootstrap() -> None:
    ddl = resources.files("uavtrail.server").joinpath("schema.sql").read_text(encoding="utf-8")
    with begin() as c:
        c.exec_driver_sql("select pg_advisory_xact_lock(7342)")
        # through the driver without parameters, so the '%' in the PL/pgSQL messages is not read as a placeholder
        c.connection.driver_connection.execute(ddl)  # type: ignore[union-attr]


def rows(sql: str, **params: Any) -> list[dict[str, Any]]:
    with engine().connect() as c:
        return [dict(r._mapping) for r in c.execute(text(sql), params)]


def scalar(sql: str, **params: Any) -> Any:
    with engine().connect() as c:
        return c.execute(text(sql), params).scalar()


def reset() -> None:
    """Drops everything the server holds. For the emulated line and tests only."""
    with begin() as c:
        c.exec_driver_sql(
            "drop table if exists trail, stations, claims, units, attempts, recoveries, issue_actions cascade; "
            "drop function if exists trail_append_only cascade"
        )
    bootstrap()
