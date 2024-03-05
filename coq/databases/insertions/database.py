from contextlib import closing, suppress
from dataclasses import dataclass
from sqlite3 import Connection, OperationalError
from typing import Iterator, Mapping

from ...consts import INSERT_DB
from ...shared.sql import init_db
from ..types import DB
from .sql import sql


@dataclass(frozen=True)
class Statistics:
    source: str
    interrupted: int
    inserted: int

    avg_duration: float
    q10_duration: float
    q50_duration: float
    q95_duration: float
    q99_duration: float

    avg_items: float
    q50_items: int
    q99_items: int


def _init() -> Connection:
    conn = Connection(INSERT_DB, isolation_level=None)
    init_db(conn)
    conn.executescript(sql("create", "pragma"))
    conn.executescript(sql("create", "tables"))
    return conn


class IDB(DB):
    def __init__(self) -> None:
        self._conn = _init()

    def new_source(self, source: str) -> None:
        # MUST OK
        with self._conn, closing(self._conn.cursor()) as cursor:
            cursor.execute(sql("insert", "source"), {"name": source})

    def new_batch(self, batch_id: bytes) -> None:
        # MUST OK
        with self._conn, closing(self._conn.cursor()) as cursor:
            cursor.execute(sql("insert", "batch"), {"rowid": batch_id})

    def new_instance(self, instance: bytes, source: str, batch_id: bytes) -> None:
        # MUST OK
        with self._conn, closing(self._conn.cursor()) as cursor:
            cursor.execute(
                sql("insert", "instance"),
                {"rowid": instance, "source_id": source, "batch_id": batch_id},
            )

    def new_stat(
        self, instance: bytes, interrupted: bool, duration: float, items: int
    ) -> None:
        # MUST OK
        with self._conn, closing(self._conn.cursor()) as cursor:
            cursor.execute(
                sql("insert", "instance_stat"),
                {
                    "instance_id": instance,
                    "interrupted": interrupted,
                    "duration": duration,
                    "items": items,
                },
            )

    def insertion_order(self, n_rows: int) -> Mapping[str, int]:
        # can interrupt
        with suppress(OperationalError):
            with self._conn, closing(self._conn.cursor()) as cursor:
                cursor.execute(sql("select", "inserted"), {"limit": n_rows})
                order = {
                    row["sort_by"]: row["insert_order"] for row in cursor.fetchall()
                }
                return order
        return {}

    def inserted(self, instance_id: bytes, sort_by: str) -> None:
        # MUST OK
        with self._conn, closing(self._conn.cursor()) as cursor:
            cursor.execute(
                sql("insert", "inserted"),
                {"instance_id": instance_id, "sort_by": sort_by},
            )

    def stats(self) -> Iterator[Statistics]:
        # MUST OK
        with self._conn, closing(self._conn.cursor()) as cursor:
            cursor.execute(sql("select", "summaries"), ())

            for row in cursor:
                stat = Statistics(
                    source=row["source"],
                    interrupted=row["interrupted"],
                    inserted=row["inserted"],
                    avg_duration=row["avg_duration"],
                    avg_items=row["avg_items"],
                    q10_duration=row["q10_duration"],
                    q50_duration=row["q50_duration"],
                    q95_duration=row["q95_duration"],
                    q99_duration=row["q99_duration"],
                    q50_items=row["q50_items"],
                    q99_items=row["q99_items"],
                )
                yield stat
