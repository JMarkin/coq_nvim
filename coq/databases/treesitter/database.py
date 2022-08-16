from asyncio import CancelledError
from concurrent.futures import Executor
from contextlib import suppress
from sqlite3 import Connection, OperationalError
from typing import AbstractSet, Iterable, Iterator, Mapping

from std2.asyncio import to_thread
from std2.sqlite3 import with_transaction

from ...consts import TREESITTER_DB
from ...shared.executor import SingleThreadExecutor
from ...shared.settings import MatchOptions
from ...shared.sql import BIGGEST_INT, init_db, like_esc
from ...shared.timeit import timeit
from ...treesitter.types import Payload, SimplePayload
from .sql import sql


def _init() -> Connection:
    conn = Connection(TREESITTER_DB, isolation_level=None)
    init_db(conn)
    conn.executescript(sql("create", "pragma"))
    conn.executescript(sql("create", "tables"))
    return conn


class TDB:
    def __init__(self, pool: Executor) -> None:
        self._ex = SingleThreadExecutor(pool)
        self._conn: Connection = self._ex.submit(_init)

    def _interrupt(self) -> None:
        self._conn.interrupt()

    async def vacuum(self, buf_ids: AbstractSet[int]) -> None:
        def cont() -> None:
            with suppress(OperationalError):
                with with_transaction(self._conn.cursor()) as cursor:
                    cursor.execute(sql("select", "buffers"), ())
                    existing = {row["rowid"] for row in cursor.fetchall()}
                    cursor.executemany(
                        sql("delete", "buffer"),
                        ({"buffer_id": buf_id} for buf_id in existing - buf_ids),
                    )
                    cursor.execute("PRAGMA optimize", ())

        await self._ex.asubmit(cont)

    async def populate(
        self, buf: int, filetype: str, filename: str, nodes: Iterable[Payload]
    ) -> None:
        def m1() -> Iterator[Mapping]:
            for node in nodes:
                yield {
                    "buffer_id": buf,
                    "word": node.text,
                    "kind": node.kind,
                    "pword": node.parent.text if node.parent else None,
                    "pkind": node.parent.kind if node.parent else None,
                    "gpword": node.grandparent.text if node.grandparent else None,
                    "gpkind": node.grandparent.kind if node.grandparent else None,
                }

        def cont() -> None:
            with suppress(OperationalError):
                with with_transaction(self._conn.cursor()) as cursor:
                    cursor.execute(
                        sql("insert", "buffer"),
                        {"rowid": buf, "filetype": filetype, "filename": filename},
                    )
                    cursor.executemany(sql("insert", "word"), m1())

        await self._ex.asubmit(cont)

    async def select(
        self,
        opts: MatchOptions,
        filetype: str,
        word: str,
        sym: str,
        limitless: int,
    ) -> Iterator[Payload]:
        def cont() -> Iterator[Payload]:
            try:
                with with_transaction(self._conn.cursor()) as cursor:
                    cursor.execute(
                        sql("select", "words"),
                        {
                            "cut_off": opts.fuzzy_cutoff,
                            "look_ahead": opts.look_ahead,
                            "limit": BIGGEST_INT if limitless else opts.max_results,
                            "filetype": filetype,
                            "word": word,
                            "sym": sym,
                            "like_word": like_esc(word[: opts.exact_matches]),
                            "like_sym": like_esc(sym[: opts.exact_matches]),
                        },
                    )
                    rows = cursor.fetchall()

                    def c2() -> Iterator[Payload]:
                        for row in rows:
                            grandparent = (
                                SimplePayload(text=row["gpword"], kind=row["gpkind"])
                                if row["gpword"] and row["gpkind"]
                                else None
                            )
                            parent = (
                                SimplePayload(text=row["pword"], kind=row["pkind"])
                                if row["pword"] and row["pkind"]
                                else None
                            )
                            yield Payload(
                                filename=row["filename"],
                                text=row["word"],
                                kind=row["kind"],
                                parent=parent,
                                grandparent=grandparent,
                            )

                    return c2()
            except OperationalError:
                return iter(())

        await to_thread(self._interrupt)
        try:
            return await self._ex.asubmit(cont)
        except CancelledError:
            with timeit("INTERRUPT !! TREESITTER"):
                await to_thread(self._interrupt)
            raise
