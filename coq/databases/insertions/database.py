from asyncio.exceptions import CancelledError
from concurrent.futures import Executor
from dataclasses import dataclass
from json import loads
from sqlite3 import Connection, OperationalError
from threading import Lock
from typing import Iterator, Mapping, Optional

from std2.asyncio import to_thread
from std2.sqlite3 import with_transaction

from ...consts import INSERT_DB
from ...shared.executor import SingleThreadExecutor
from ...shared.sql import init_db
from ...shared.timeit import timeit
from .sql import sql


@dataclass(frozen=True)
class Statistics:
    source: str
    interrupted: int
    inserted: int

    avg_duration: float
    q0_duration: float
    q50_duration: float
    q95_duration: float
    q100_duration: float

    avg_items: float
    q50_items: int
    q100_items: int


def _init() -> Connection:
    conn = Connection(INSERT_DB, isolation_level=None)
    init_db(conn)
    conn.executescript(sql("create", "pragma"))
    conn.executescript(sql("create", "tables"))
    return conn


class IDB:
    def __init__(self, pool: Executor) -> None:
        self._lock = Lock()
        self._ex = SingleThreadExecutor(pool)
        self._conn: Connection = self._ex.submit(_init)

    def _interrupt(self) -> None:
        with self._lock:
            self._conn.interrupt()

    def new_source(self, source: str) -> None:
        def cont() -> None:
            with self._lock, with_transaction(self._conn.cursor()) as cursor:
                cursor.execute(sql("insert", "source"), {"name": source})

        self._ex.submit(cont)

    async def new_batch(self, batch_id: bytes) -> None:
        def cont() -> None:
            with self._lock, with_transaction(self._conn.cursor()) as cursor:
                cursor.execute(sql("insert", "batch"), {"rowid": batch_id})

        await self._ex.asubmit(cont)

    async def new_instance(self, instance: bytes, source: str, batch_id: bytes) -> None:
        def cont(_: None = None) -> None:
            with self._lock, with_transaction(self._conn.cursor()) as cursor:
                cursor.execute(
                    sql("insert", "instance"),
                    {"rowid": instance, "source_id": source, "batch_id": batch_id},
                )

        await self._ex.asubmit(cont)

    async def new_stat(
        self, instance: bytes, interrupted: bool, duration: float, items: int
    ) -> None:
        def cont() -> None:
            with self._lock, with_transaction(self._conn.cursor()) as cursor:
                cursor.execute(
                    sql("insert", "instance_stat"),
                    {
                        "instance_id": instance,
                        "interrupted": interrupted,
                        "duration": duration,
                        "items": items,
                    },
                )

        await self._ex.asubmit(cont)

    async def insertion_order(self, n_rows: int) -> Mapping[str, int]:
        def cont() -> Mapping[str, int]:
            try:
                with with_transaction(self._conn.cursor()) as cursor:
                    cursor.execute(sql("select", "inserted"), {"limit": n_rows})
                    order = {
                        row["sort_by"]: row["insert_order"] for row in cursor.fetchall()
                    }
                    return order
            except OperationalError:
                return {}

        await to_thread(self._interrupt)
        try:
            return await self._ex.asubmit(cont)
        except CancelledError:
            with timeit("INTERRUPT !! INSERTED"):
                await to_thread(self._interrupt)
            raise

    def inserted(self, instance_id: bytes, sort_by: str) -> None:
        def cont() -> None:
            with self._lock, with_transaction(self._conn.cursor()) as cursor:
                cursor.execute(
                    sql("insert", "inserted"),
                    {"instance_id": instance_id, "sort_by": sort_by},
                )

        self._ex.submit(cont)

    def stats(self) -> Iterator[Statistics]:
        def cont() -> Iterator[Statistics]:
            with self._lock, with_transaction(self._conn.cursor()) as cursor:
                cursor.execute(sql("select", "stats"), ())
                rows = cursor.fetchall()

            def c1() -> Iterator[Statistics]:
                for row in rows:
                    q_duration: Mapping[str, Optional[float]] = loads(row["q_duration"])
                    q_items: Mapping[str, Optional[int]] = loads(row["q_items"])
                    stat = Statistics(
                        source=row["source"],
                        interrupted=row["interrupted"],
                        inserted=row["inserted"],
                        avg_duration=row["avg_duration"],
                        avg_items=row["avg_items"],
                        q0_duration=q_duration.get("q0") or 0,
                        q50_duration=q_duration.get("q50") or 0,
                        q95_duration=q_duration.get("q95") or 0,
                        q100_duration=q_duration.get("q100") or 0,
                        q50_items=q_items.get("q50") or 0,
                        q100_items=q_items.get("q100") or 0,
                    )
                    yield stat

            return c1()

        return self._ex.submit(cont)
