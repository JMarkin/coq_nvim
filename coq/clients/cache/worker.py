from dataclasses import dataclass, replace
from itertools import chain
from typing import (
    AbstractSet,
    Awaitable,
    Iterable,
    Iterator,
    Mapping,
    MutableMapping,
    MutableSet,
    Optional,
    Tuple,
)
from uuid import UUID, uuid4

from ...databases.cache.database import Database
from ...shared.fuzzy import multi_set_ratio
from ...shared.parse import coalesce
from ...shared.repeat import sanitize
from ...shared.runtime import Supervisor
from ...shared.settings import MatchOptions
from ...shared.timeit import timeit
from ...shared.types import Completion, Context


@dataclass(frozen=True)
class _CacheCtx:
    change_id: UUID
    commit_id: UUID
    buf_id: int
    row: int
    syms_before: str


def _use_cache(match: MatchOptions, cache: _CacheCtx, ctx: Context) -> bool:
    row, _ = ctx.position
    use_cache = (
        not ctx.manual
        and cache.commit_id == ctx.commit_id
        and ctx.buf_id == cache.buf_id
        and row == cache.row
        and multi_set_ratio(
            ctx.syms_before, cache.syms_before, look_ahead=match.look_ahead
        )
        >= match.fuzzy_cutoff
    )
    return use_cache


def sanitize_cached(comp: Completion, sort_by: Optional[str]) -> Completion:
    edit = sanitize(comp.primary_edit)
    cached = replace(
        comp,
        primary_edit=edit,
        secondary_edits=(),
        sort_by=sort_by or comp.sort_by,
    )
    return cached


class CacheWorker:
    def __init__(self, supervisor: Supervisor) -> None:
        self._supervisor = supervisor
        self._db = Database(supervisor.pool)
        self._cache_ctx = _CacheCtx(
            change_id=uuid4(),
            commit_id=uuid4(),
            buf_id=-1,
            row=-1,
            syms_before="",
        )
        self._clients: MutableSet[str] = set()
        self._cached: MutableMapping[bytes, Completion] = {}

    async def set_cache(
        self,
        items: Mapping[Optional[str], Iterable[Completion]],
    ) -> None:
        new_comps = {
            comp.uid.bytes: comp for comp in chain.from_iterable(items.values())
        }

        def cont() -> Iterator[Tuple[bytes, str]]:
            for key, val in new_comps.items():
                if self._supervisor.comp.smart:
                    for word in coalesce(
                        val.sort_by,
                        unifying_chars=self._supervisor.match.unifying_chars,
                    ):
                        yield key, word
                else:
                    yield key, val.sort_by

        await self._db.insert(cont())

        for client in items:
            if client:
                self._clients.add(client)
        self._cached.update(new_comps)

    def apply_cache(
        self, context: Context
    ) -> Tuple[bool, AbstractSet[str], Awaitable[Tuple[Iterator[Completion], int]]]:
        cache_ctx = self._cache_ctx
        row, _ = context.position
        self._cache_ctx = _CacheCtx(
            change_id=context.change_id,
            commit_id=context.commit_id,
            buf_id=context.buf_id,
            row=row,
            syms_before=context.syms_before,
        )

        use_cache = _use_cache(
            self._supervisor.match, cache=cache_ctx, ctx=context
        ) and bool(self._cached)
        cached_clients = {*self._clients}

        if not use_cache:
            self._clients.clear()
            self._cached.clear()

        async def get() -> Tuple[Iterator[Completion], int]:
            with timeit("CACHE -- GET"):
                keys, length = await self._db.select(
                    not use_cache,
                    opts=self._supervisor.match,
                    word=context.words,
                    sym=context.syms,
                    limitless=context.manual,
                )
                comps = (
                    sanitize_cached(comp, sort_by=sort_by)
                    for key, sort_by in keys
                    if (comp := self._cached.get(key))
                )
                return comps, length

        return use_cache, cached_clients, get()
