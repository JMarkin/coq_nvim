from __future__ import annotations

from abc import abstractmethod
from asyncio import (
    AbstractEventLoop,
    CancelledError,
    Condition,
    Task,
    as_completed,
    wait,
)
from concurrent.futures import Executor
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Generic,
    MutableSequence,
    Optional,
    Protocol,
    Sequence,
    TypeVar,
)
from uuid import UUID, uuid4
from weakref import WeakSet

from pynvim import Nvim
from pynvim_pp.lib import go
from pynvim_pp.logging import with_suppress
from std2.aitertools import aenumerate
from std2.asyncio import cancel

from .settings import BaseClient, CompleteOptions, Limits, MatchOptions, Weights
from .timeit import TracingLocker, timeit
from .types import Completion, Context

_T = TypeVar("_T")
_T_co = TypeVar("_T_co", contravariant=True)
_O_co = TypeVar("_O_co", contravariant=True, bound=BaseClient)


@dataclass(frozen=True)
class Metric:
    instance: UUID
    comp: Completion
    weight_adjust: float
    weight: Weights
    label_width: int
    kind_width: int


class PReviewer(Protocol[_T]):
    def register(self, assoc: BaseClient) -> None:
        ...

    async def begin(self, context: Context) -> _T:
        ...

    async def s_begin(self, token: _T, assoc: BaseClient, instance: UUID) -> None:
        ...

    def trans(self, token: _T, instance: UUID, completion: Completion) -> Metric:
        ...

    async def s_end(
        self, instance: UUID, interrupted: bool, elapsed: float, items: int
    ) -> None:
        ...


class Supervisor:
    def __init__(
        self,
        pool: Executor,
        nvim: Nvim,
        vars_dir: Path,
        match: MatchOptions,
        comp: CompleteOptions,
        limits: Limits,
        reviewer: PReviewer,
    ) -> None:
        self.pool = pool
        self.vars_dir = vars_dir
        self.match, self.comp, self.limits = match, comp, limits
        self.nvim, self._reviewer = nvim, reviewer

        self.idling = Condition()
        self._workers: WeakSet[Worker] = WeakSet()

        self._lock = TracingLocker(name="Supervisor", force=True)
        self._work_task: Optional[Task] = None

    def register(self, worker: Worker, assoc: BaseClient) -> None:
        self._reviewer.register(assoc)
        self._workers.add(worker)

    def notify_idle(self) -> None:
        async def cont() -> None:
            async with self.idling:
                self.idling.notify_all()

        go(self.nvim, aw=cont())

    async def interrupt(self) -> None:
        task = self._work_task
        self._work_task = None
        if task:
            await cancel(task)

    def collect(self, context: Context) -> Awaitable[Sequence[Metric]]:
        loop: AbstractEventLoop = self.nvim.loop
        now = monotonic()
        timeout = (
            self.limits.completion_manual_timeout
            if context.manual
            else self.limits.completion_auto_timeout
        )

        async def cont(prev: Optional[Task]) -> Sequence[Metric]:
            with timeit("CANCEL -- ALL"):
                if prev:
                    await cancel(prev)

            with with_suppress(), timeit("COLLECTED -- ALL"):
                async with self._lock:
                    acc: MutableSequence[Metric] = []

                    token = await self._reviewer.begin(context)
                    tasks = tuple(
                        worker.supervised(context, token=token, now=now, acc=acc)
                        for worker in self._workers
                    )

                    _, pending = await wait(tasks, timeout=timeout)
                    if not acc:
                        for fut in as_completed(pending):
                            await fut
                            if acc:
                                break

                    await cancel(*pending)
                    return acc

        self._work_task = task = loop.create_task(cont(self._work_task))
        return task


class Worker(Generic[_O_co, _T_co]):
    def __init__(self, supervisor: Supervisor, options: _O_co, misc: _T_co) -> None:
        self._work_task: Optional[Task] = None
        self._work_lock = TracingLocker(name=options.short_name, force=True)
        self._supervisor, self._options, self._misc = supervisor, options, misc
        self._supervisor.register(self, assoc=options)

    @abstractmethod
    def work(self, context: Context) -> AsyncIterator[Completion]:
        ...

    def supervised(
        self,
        context: Context,
        token: Any,
        now: float,
        acc: MutableSequence[Metric],
    ) -> Task:
        loop: AbstractEventLoop = self._supervisor.nvim.loop
        prev = self._work_task

        async def cont() -> None:
            instance, items = uuid4(), 0
            interrupted = False

            with timeit(f"CANCEL WORKER -- {self._options.short_name}"):
                if prev:
                    await cancel(prev)

            with with_suppress(), timeit(f"WORKER -- {self._options.short_name}"):
                await self._supervisor._reviewer.s_begin(
                    token, assoc=self._options, instance=instance
                )
                try:
                    async for items, completion in aenumerate(
                        self.work(context), start=1
                    ):
                        metric = self._supervisor._reviewer.trans(
                            token, instance=instance, completion=completion
                        )
                        acc.append(metric)
                except CancelledError:
                    interrupted = True
                    raise
                finally:
                    elapsed = monotonic() - now
                    await self._supervisor._reviewer.s_end(
                        instance,
                        interrupted=interrupted,
                        elapsed=elapsed,
                        items=items,
                    )

        self._work_task = task = loop.create_task(cont())
        return task
