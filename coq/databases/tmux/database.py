from contextlib import suppress
from dataclasses import dataclass
from itertools import islice
from sqlite3 import Connection, OperationalError
from typing import AbstractSet, Iterator, Mapping, MutableMapping, Optional

from std2.sqlite3 import with_transaction

from ...consts import TMUX_DB
from ...shared.executor import SingleThreadExecutor
from ...shared.parse import coalesce
from ...shared.settings import MatchOptions
from ...shared.sql import BIGGEST_INT, init_db, like_esc
from ...tmux.parse import Pane
from ..types import Interruptible
from .sql import sql


@dataclass(frozen=True)
class TmuxWord:
    text: str
    session_name: str
    window_index: int
    window_name: str
    pane_index: int
    pane_title: str


def _init() -> Connection:
    conn = Connection(TMUX_DB, isolation_level=None)
    init_db(conn)
    conn.executescript(sql("create", "pragma"))
    conn.executescript(sql("create", "tables"))
    return conn


def _tokenize(
    tokenization_limit: int,
    unifying_chars: AbstractSet[str],
    include_syms: bool,
    text: str,
) -> Iterator[str]:
    words = coalesce(text, unifying_chars=unifying_chars, include_syms=include_syms)
    return islice(words, tokenization_limit)


class TMDB(Interruptible):
    def __init__(
        self,
        tokenization_limit: int,
        unifying_chars: AbstractSet[str],
        include_syms: bool,
    ) -> None:
        self._ex = SingleThreadExecutor()
        self._current: Optional[Pane] = None
        self._tokenization_limit = tokenization_limit
        self._unifying_chars = unifying_chars
        self._include_syms = include_syms
        self._cache: MutableMapping[str, str] = {}
        self._conn: Connection = self._ex.ssubmit(_init)

    async def periodical(
        self, current: Optional[Pane], panes: Mapping[Pane, str]
    ) -> None:
        self._current = current
        live_panes = {pane.uid for pane in panes}
        self._cache = {
            pane_id: text
            for pane_id, text in self._cache.items()
            if pane_id in live_panes
        }
        not_cached = {
            pane: text
            for pane, text in panes.items()
            if pane != current and text != self._cache.get(pane.uid)
        }

        def m1(existing: AbstractSet[str]) -> Iterator[Mapping]:
            for uid in existing - live_panes:
                yield {"pane_id": uid}

        def m2() -> Iterator[Mapping]:
            for pane in not_cached:
                yield {
                    "pane_id": pane.uid,
                    "session_name": pane.session_name,
                    "window_index": pane.window_index,
                    "window_name": pane.window_name,
                    "pane_index": pane.pane_index,
                    "pane_title": pane.pane_title,
                }

        def m3() -> Iterator[Mapping]:
            for pane, text in not_cached.items():
                for word in _tokenize(
                    self._tokenization_limit,
                    unifying_chars=self._unifying_chars,
                    include_syms=self._include_syms,
                    text=text,
                ):
                    yield {
                        "pane_id": pane.uid,
                        "word": word,
                    }
                else:
                    self._cache[pane.uid] = text

        def cont() -> None:
            with suppress(OperationalError):
                with with_transaction(self._conn.cursor()) as cursor:
                    cursor.execute(sql("select", "panes"))
                    existing = {row["pane_id"] for row in cursor.fetchall()}
                    cursor.executemany(sql("delete", "pane"), m1(existing))
                    cursor.executemany(sql("insert", "pane"), m2())
                    cursor.executemany(sql("insert", "word"), m3())
                    cursor.execute("PRAGMA optimize", ())

        await self._ex.submit(cont)

    async def select(
        self, opts: MatchOptions, word: str, sym: str, limitless: int
    ) -> Iterator[TmuxWord]:
        def cont() -> Iterator[TmuxWord]:
            try:
                with with_transaction(self._conn.cursor()) as cursor:
                    cursor.execute(
                        sql("select", "words"),
                        {
                            "cut_off": opts.fuzzy_cutoff,
                            "look_ahead": opts.look_ahead,
                            "limit": BIGGEST_INT if limitless else opts.max_results,
                            "pane_id": self._current.uid if self._current else None,
                            "word": word,
                            "sym": sym,
                            "like_word": like_esc(word[: opts.exact_matches]),
                            "like_sym": like_esc(sym[: opts.exact_matches]),
                        },
                    )
                    rows = cursor.fetchall()
                    return (
                        TmuxWord(
                            text=row["word"],
                            session_name=row["session_name"],
                            window_index=row["window_index"],
                            window_name=row["window_name"],
                            pane_index=row["pane_index"],
                            pane_title=row["pane_title"],
                        )
                        for row in rows
                    )
            except OperationalError:
                return iter(())

        with self._interruption():
            return await self._ex.submit(cont)
