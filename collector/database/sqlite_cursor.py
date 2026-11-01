"""Async cursor interface for the collector's SQLite queries."""

import asyncio
import re
import sqlite3
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from database.sqlite_values import decode_value, encode_value


async def run_sqlite(operation: Callable, *args: Any) -> Any:
    """Finish an outstanding SQLite operation before releasing its connection."""
    task = asyncio.create_task(asyncio.to_thread(operation, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


def bind_query(query: str, parameters: Mapping | Sequence | None) -> tuple:
    """Bind the shared DB-API parameter notation without interpolating values."""
    if isinstance(parameters, Mapping):
        query = re.sub(r"%\((\w+)\)s", r":\1", query)
        return query, {key: encode_value(value) for key, value in parameters.items()}
    return query.replace("%s", "?"), tuple(encode_value(v) for v in parameters or ())


class SQLiteCursor:
    """Hold a SQLite cursor and expose the async methods used by collectors."""

    def __init__(self, connection: sqlite3.Connection, as_dict: bool) -> None:
        self._cursor = connection.cursor()
        self._as_dict = as_dict

    async def __aenter__(self) -> "SQLiteCursor":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        await run_sqlite(self._cursor.close)

    async def execute(
        self, query: str, parameters: Mapping | Sequence | None = None
    ) -> None:
        """Execute a parameterized SQLite storage query."""
        sql, values = bind_query(query, parameters)
        await run_sqlite(self._cursor.execute, sql, values)

    async def executemany(self, query: str, parameters: Iterable[Mapping]) -> None:
        """Write a batch within the surrounding transaction."""
        batches = [bind_query(query, row) for row in parameters]
        if batches:
            await run_sqlite(
                self._cursor.executemany, batches[0][0], [b[1] for b in batches]
            )

    def _decode_row(self, row: tuple | None) -> dict | tuple | None:
        if row is None:
            return None
        names = [column[0] for column in self._cursor.description]
        values = [decode_value(name, value) for name, value in zip(names, row)]
        return dict(zip(names, values)) if self._as_dict else tuple(values)

    async def fetchone(self) -> dict | tuple | None:
        """Read one row using the requested row shape."""
        return self._decode_row(await run_sqlite(self._cursor.fetchone))

    async def fetchall(self) -> list:
        """Read all remaining rows using the requested row shape."""
        return [
            self._decode_row(row) for row in await run_sqlite(self._cursor.fetchall)
        ]
