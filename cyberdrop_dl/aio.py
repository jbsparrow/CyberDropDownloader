"""Async versions of some builtins, itertools and path operations"""

# ruff: noqa: A001
from __future__ import annotations

import asyncio
import builtins
import contextlib
import dataclasses
import sys
from pathlib import Path
from stat import S_ISREG
from typing import IO, TYPE_CHECKING, Any, Self, TypeVar, cast, overload, override
from weakref import WeakValueDictionary

from aiolimiter.leakybucket import AsyncLimiter

from cyberdrop_dl.constants import MISSING

if TYPE_CHECKING:
    from collections.abc import (
        AsyncGenerator,
        AsyncIterable,
        AsyncIterator,
        Awaitable,
        Callable,
        Coroutine,
        Iterable,
        Iterator,
        Mapping,
        Sequence,
    )
    from contextvars import Context
    from types import TracebackType

    from _typeshed import OpenBinaryMode, OpenTextMode


_T_co = TypeVar("_T_co", covariant=True)


class EagerTaskGroup(asyncio.TaskGroup):
    def __init__(self) -> None:
        super().__init__()
        self.done: asyncio.Event = asyncio.Event()

    if sys.version_info < (3, 14, 0):

        @override
        def create_task(
            self,
            coro: Coroutine[Any, Any, _T_co],
            *,
            name: str | None = None,
            context: Context | None = None,
            eager_start: bool | None = None,
        ) -> asyncio.Task[_T_co]:
            if eager_start is False:

                async def lazy() -> _T_co:
                    await asyncio.sleep(0)
                    return await coro

                run = lazy()
            else:
                run = coro

            return super().create_task(run, name=name, context=context)

    async def __aexit__(
        self,
        et: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            return await super().__aexit__(et, exc, tb)
        finally:
            self.done.set()
            et = exc = tb = None  # prevent ref cycles for GC

    def create_lazy_task(
        self,
        coro: Coroutine[Any, Any, _T_co],
        *,
        name: str | None = None,
        context: Context | None = None,
    ) -> asyncio.Task[_T_co]:
        return self.create_task(coro, name=name, context=context, eager_start=False)

    def create_eager_task(
        self,
        coro: Coroutine[Any, Any, _T_co],
        *,
        name: str | None = None,
        context: Context | None = None,
    ) -> asyncio.Task[_T_co]:
        return self.create_task(coro, name=name, context=context, eager_start=True)


@dataclasses.dataclass(frozen=True, slots=True, eq=False)
class TaskManager:
    logs: EagerTaskGroup = dataclasses.field(default_factory=EagerTaskGroup)
    scrape: EagerTaskGroup = dataclasses.field(default_factory=EagerTaskGroup)
    downloads: EagerTaskGroup = dataclasses.field(default_factory=EagerTaskGroup)


class _AsyncChain:
    """Like itertools.chain, but for async iterables"""

    def __repr__(self) -> str:
        return f"{type(self).__name__}"

    def __call__[T](self, *async_iterables: AsyncIterable[T]) -> AsyncGenerator[T]:
        return self.from_iterable(async_iterables)

    @staticmethod
    async def from_iterable[T](async_iterables: Iterable[AsyncIterable[T]]) -> AsyncGenerator[T]:
        for a_iterable in async_iterables:
            async for value in a_iterable:
                yield value

    @staticmethod
    async def yield_this[T](obj: T) -> AsyncGenerator[T]:
        yield obj


chain = _AsyncChain()


async def next[T](async_iterator: AsyncIterator[T]) -> T:
    try:
        return await builtins.anext(async_iterator)
    except StopAsyncIteration as e:
        raise e.__cause__ or e from None


async def peek_first[T](async_iterable: AsyncIterable[T], /) -> tuple[T, AsyncGenerator[T, None]]:
    async_iterator = aiter(async_iterable)
    first = await next(async_iterator)

    return first, chain(chain.yield_this(first), async_iterator)


@dataclasses.dataclass(frozen=True, slots=True, eq=False)
class WeakAsyncLocks[T]:
    """A WeakValueDictionary wrapper for asyncio.Locks.

    Unused locks are automatically garbage collected. When trying to retrieve a
    lock that does not exists, a new lock will be created.
    """

    _locks: WeakValueDictionary[T, asyncio.Lock] = dataclasses.field(init=False, default_factory=WeakValueDictionary)

    def __getitem__(self, key: T, /) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            self._locks[key] = lock = asyncio.Lock()
        return lock


class RateLimiter(AsyncLimiter):
    __slots__ = ()

    async def acquire(self, amount: float = 1) -> None:
        if self.max_rate == 0:
            return
        await super().acquire(amount)

    @classmethod
    def w_no_burst(cls, max_rate: float, time_period: float = 1) -> Self:
        """Create a new instance that prevents acquisitions from bursting through the limit.

        Instead of allowing up to <max_rate> acquisitions over a period of <time_period>,
        spread them evenly across the <time_period> to maintain a steady rate of <max_rate>.
        """
        if max_rate == 0:
            return cls.no_op()
        return cls(max_rate=1, time_period=time_period / max_rate)

    @classmethod
    def no_op(cls) -> Self:
        return cls(max_rate=0, time_period=1)


@dataclasses.dataclass(slots=True, eq=False)
class AsyncIOWrapper[AnyStr: (bytes, str)]:
    """An asynchronous context manager wrapper for a file object."""

    _coro: Awaitable[IO[AnyStr]]
    _io: IO[AnyStr] = dataclasses.field(init=False)

    def __repr__(self) -> str:
        return f"<{type(self).__name__}(io={getattr(self, '_io', None)!r})>"

    async def __aenter__(self) -> Self:
        self._io = await self._coro
        return self

    async def __aexit__(self, *_: object) -> None:
        return await asyncio.to_thread(self._io.close)

    async def __aiter__(self) -> AsyncIterator[AnyStr]:
        while line := await self.readline():
            yield line

    async def read(self, size: int = -1) -> AnyStr:
        return await asyncio.to_thread(self._io.read, size)

    async def readline(self) -> AnyStr:
        return await asyncio.to_thread(self._io.readline)

    async def readlines(self) -> list[AnyStr]:
        return await asyncio.to_thread(self._io.readlines)

    async def write(self, b: AnyStr, /) -> int:
        return await asyncio.to_thread(self._io.write, b)

    async def writelines(self, lines: Iterable[AnyStr], /) -> None:
        return await asyncio.to_thread(self._io.writelines, lines)


@dataclasses.dataclass(slots=True, eq=False)
class AsyncIteratorWrapper[T]:
    _coro: Awaitable[Iterable[T]]
    _iterator: Iterator[T] | None = dataclasses.field(default=None, init=False)

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> T:
        if self._iterator is None:
            self._iterator = iter(await self._coro)
        value = await asyncio.to_thread(builtins.next, self._iterator, MISSING)
        if value is MISSING:
            raise StopAsyncIteration from None

        return cast("T", value)


@overload
async def gather[T1](coro1: Awaitable[T1], /, *, fail_fast: bool = True) -> tuple[T1]: ...


@overload
async def gather[T1, T2](coro1: Awaitable[T1], coro2: Awaitable[T2], /, *, fail_fast: bool = True) -> tuple[T1, T2]: ...


@overload
async def gather[T1, T2, T3](
    coro1: Awaitable[T1], coro2: Awaitable[T2], coro3: Awaitable[T3], /, *, fail_fast: bool = True
) -> tuple[T1, T2, T3]: ...


@overload
async def gather[T1, T2, T3, T4](
    coro1: Awaitable[T1], coro2: Awaitable[T2], coro3: Awaitable[T3], coro4: Awaitable[T4], /, *, fail_fast: bool = True
) -> tuple[T1, T2, T3, T4]: ...


@overload
async def gather[T1, T2, T3, T4, T5](
    coro1: Awaitable[T1],
    coro2: Awaitable[T2],
    coro3: Awaitable[T3],
    coro4: Awaitable[T4],
    coro5: Awaitable[T5],
    /,
    *,
    fail_fast: bool = True,
) -> tuple[T1, T2, T3, T4, T5]: ...


@overload
async def gather[T1, T2, T3, T4, T5, T6](
    coro1: Awaitable[T1],
    coro2: Awaitable[T2],
    coro3: Awaitable[T3],
    coro4: Awaitable[T4],
    coro5: Awaitable[T5],
    coro6: Awaitable[T6],
    /,
    *,
    fail_fast: bool = True,
) -> tuple[T1, T2, T3, T4, T5, T6]: ...


@overload
async def gather[T](*coros: Awaitable[T], fail_fast: bool = True) -> list[T]: ...


async def gather[T](*coros: Awaitable[T], fail_fast: bool = True) -> Sequence[T]:  # pyright: ignore[reportInconsistentOverload]
    """Like asyncio.gather(*coros, return_exceptions=False), but all coros always finish or are cancelled

    if `fail_fast` is `True`, an exception on any coro immediately cancels all pending coros and is re-raised as an ExceptionGroup

    if `fail_fast` is `False`, it waits for all coros to complete. It there was any exception, they are grouped and re-raised as an ExceptionGroup
    in the same order as they were scheduled. This makes errors deterministic.
    """

    if fail_fast:
        results, _ = await _tg_gather(coros, return_exceptions=False)
        return results

    results = await asyncio.gather(*coros, return_exceptions=True)  # noqa: TID251
    errors = tuple(r for r in results if isinstance(r, BaseException))
    if errors:
        raise BaseExceptionGroup("", errors)
    return cast("list[T]", results)


def _values_sorted_by_key[T](results: Mapping[int, T]) -> list[T]:
    return [result for _, result in sorted(results.items())]


async def _tg_gather[T](
    coros: Iterable[Awaitable[T]], *, return_exceptions: bool = False
) -> tuple[list[T], list[Exception]]:
    results: dict[int, T] = {}
    errors: dict[int, Exception] = {}

    async def wrap(idx: int, coro: Awaitable[T]) -> None:
        try:
            results[idx] = await coro
        except Exception as e:
            if not return_exceptions:
                raise
            errors[idx] = e

    async with asyncio.TaskGroup() as tg:
        for idx, coro in enumerate(coros):
            tg.create_task(wrap(idx, coro))

    return _values_sorted_by_key(results), _values_sorted_by_key(errors)


async def map[T, R](
    coro_factory: Callable[[T], Awaitable[R]],
    params: Iterable[T],
    /,
    *,
    task_limit: asyncio.BoundedSemaphore | int | None,
) -> list[R]:
    """Map an async factory over a sequence of arguments with optional concurrency cap.

    If `task_limit` is given, no more than that many coroutines will be “in flight” at the same time,
    limiting memory pressure and event loop overhead"""
    return await map_tuples(coro_factory, ((param,) for param in params), task_limit=task_limit)


async def afilter[T](
    predicate: Callable[[T], Awaitable[Any]],
    params: Iterable[T],
    /,
    *,
    task_limit: asyncio.BoundedSemaphore | int | None = None,
) -> filter[T]:
    ## TODO use queue for lazy iteration with queue.shutdown when dropping python 3.12

    async def fn(value: T) -> T:
        if await predicate(value):
            return value
        return MISSING

    results = await map(fn, params, task_limit=task_limit)
    return filter(lambda x: x is not MISSING, results)


async def afilter_false[T](
    predicate: Callable[[T], Awaitable[Any]],
    params: Iterable[T],
    /,
    *,
    task_limit: asyncio.BoundedSemaphore | int | None = None,
) -> filter[T]:

    async def new_predicate(x: T) -> bool:
        return not await predicate(x)

    return await afilter(new_predicate, params, task_limit=task_limit)


async def map_tuples[*Ts, R](
    coro_factory: Callable[[*Ts], Awaitable[R]],
    params_batched: Iterable[tuple[*Ts]],
    /,
    *,
    task_limit: asyncio.BoundedSemaphore | int | None = None,
) -> list[R]:
    """Map an async factory over a sequence of arguments with optional concurrency cap.

    If `task_limit` is given, no more than that many coroutines will be “in flight” at the same time,
    limiting memory pressure and event loop overhead

    If task_limit is an asyncio.Semaphore, it can be shared across multiple `map_tuples` calls"""

    if task_limit is None:
        return await gather(*(coro_factory(*params) for params in params_batched))

    if isinstance(task_limit, int):
        if task_limit < 1:
            raise ValueError("task limit must be >= 1")
        semaphore = asyncio.BoundedSemaphore(task_limit)
    else:
        semaphore = task_limit

    results: dict[int, R] = {}

    async def run(idx: int, coro: Awaitable[R]) -> None:
        try:
            results[idx] = await coro
        finally:
            semaphore.release()

    async with asyncio.TaskGroup() as tg:
        pending = enumerate(params_batched)
        while True:
            await semaphore.acquire()
            try:
                idx, params = builtins.next(pending)
            except StopIteration:
                semaphore.release()
                break
            else:
                tg.create_task(run(idx, coro_factory(*params)))

    return _values_sorted_by_key(results)


@contextlib.asynccontextmanager
async def as_completed[*Ts, R](
    coro_factory: Callable[[*Ts], Awaitable[R]],
    params_batched: Iterable[tuple[*Ts]],
    /,
    *,
    task_limit: int,
) -> AsyncGenerator[AsyncIterator[R]]:

    # TODO: use queue.shutdown in python 3.13

    if task_limit < 1:
        raise ValueError("task_limit must be positive")

    queue = asyncio.Queue[R]()
    shutdown: asyncio.Event = asyncio.Event()
    params = iter(params_batched)

    async def worker() -> None:
        while not shutdown.is_set():
            try:
                args = builtins.next(params)
            except StopIteration:
                return

            # TODO: How to handle exceptions here? log them?
            # if this fails, the producer taskgroup explodes
            # and the other workers are also cancelled
            result = await coro_factory(*args)
            if shutdown.is_set():
                return
            queue.put_nowait(result)

    async def create_workers() -> None:
        try:
            async with asyncio.TaskGroup() as tg:
                for _ in range(task_limit):
                    tg.create_task(worker())
        finally:
            queue.put_nowait(MISSING)

    async with asyncio.TaskGroup() as tg:
        producer = tg.create_task(create_workers())
        consumer = queue_consumer(queue)
        try:
            yield consumer
        finally:
            shutdown.set()
            producer.cancel()
            await consumer.aclose()


async def queue_consumer[T](queue: asyncio.Queue[T], stop_sentinel: Any = MISSING) -> AsyncGenerator[T]:
    while True:
        result = await queue.get()
        try:
            if result is stop_sentinel:
                return
            yield result
        finally:
            queue.task_done()


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    def loop_factory() -> asyncio.AbstractEventLoop:
        loop = asyncio.new_event_loop()
        loop.set_task_factory(asyncio.eager_task_factory)
        return loop

    with asyncio.Runner(loop_factory=loop_factory) as runner:
        return runner.run(coro)


def to_thread[**P, R](fn: Callable[P, R]) -> Callable[P, Coroutine[None, None, R]]:
    """Convert a blocking callable into an async callable that runs in another thread"""

    async def async_run(*args: P.args, **kwargs: P.kwargs) -> R:
        return await asyncio.to_thread(fn, *args, **kwargs)

    return async_run


@to_thread
def move(src: Path, dst: Path) -> None:
    import shutil

    shutil.move(src, dst)


chmod = to_thread(Path.chmod)
exists = to_thread(Path.exists)
is_dir = to_thread(Path.is_dir)
is_file = to_thread(Path.is_file)
mkdir = to_thread(Path.mkdir)
read_bytes = to_thread(Path.read_bytes)
read_text = to_thread(Path.read_text)
resolve = to_thread(Path.resolve)
stat = to_thread(Path.stat)
touch = to_thread(Path.touch)
unlink = remove = to_thread(Path.unlink)
write_bytes = to_thread(Path.write_bytes)
write_text = to_thread(Path.write_text)
rmdir = to_thread(Path.rmdir)


def glob(path: Path, pattern: str) -> AsyncIterator[Path]:
    coro = asyncio.to_thread(path.glob, pattern)
    return AsyncIteratorWrapper(coro)


def rglob(path: Path, pattern: str) -> AsyncIterator[Path]:
    coro = asyncio.to_thread(path.rglob, pattern)
    return AsyncIteratorWrapper(coro)


def iterdir(path: Path) -> AsyncIterator[Path]:
    coro = asyncio.to_thread(path.iterdir)
    return AsyncIteratorWrapper(coro)


@overload
def open(
    path: Path,
    mode: OpenBinaryMode,
    buffering: int = ...,
    encoding: str | None = ...,
    errors: str | None = ...,
    newline: str | None = ...,
) -> AsyncIOWrapper[bytes]: ...


@overload
def open(
    path: Path,
    mode: OpenTextMode = ...,
    buffering: int = ...,
    encoding: str | None = ...,
    errors: str | None = ...,
    newline: str | None = ...,
) -> AsyncIOWrapper[str]: ...


def open(  # noqa: PLR0913, PLR0917
    path: Path,
    mode: str = "r",
    buffering: int = -1,
    encoding: str | None = None,
    errors: str | None = None,
    newline: str | None = None,
) -> AsyncIOWrapper[Any]:
    coro = asyncio.to_thread(path.open, mode, buffering, encoding, errors, newline)
    return AsyncIOWrapper(coro)


async def get_size(path: Path) -> int | None:
    """If path exists and is a file, returns its size. Returns `None` otherwise"""

    # Manually parse stat result to make sure we only use 1 fs call

    try:
        stat_result = await stat(path)
    except (OSError, ValueError):
        return None
    else:
        if not S_ISREG(stat_result.st_mode):
            raise IsADirectoryError(path)
        return stat_result.st_size


@contextlib.asynccontextmanager
async def temp_dir() -> AsyncGenerator[Path]:
    import tempfile

    temp_dir = await asyncio.to_thread(tempfile.TemporaryDirectory, prefix="cdl_", ignore_cleanup_errors=True)
    try:
        yield Path(temp_dir.name)
    finally:
        await asyncio.to_thread(temp_dir.cleanup)


def periodic_sleep(period: int, /) -> Callable[[], Awaitable[None]]:
    """Yield control to the event loop every n calls

    To use within busy blocking loops"""

    if period <= 0:
        raise ValueError("period must be a positive integer")

    calls = 0

    async def sleep() -> None:
        nonlocal calls
        calls += 1
        if calls % period == 0:
            await asyncio.sleep(0)

    return sleep


@contextlib.asynccontextmanager
async def backgroud_task(
    fn: Callable[[], Awaitable[Any]], *, period: float, name: str | None = None
) -> AsyncGenerator[None]:
    "Run a callable very <period>"
    if period < 0.1:
        raise ValueError(f"{period = } is too low. Must be > 0.1")

    import contextvars

    done: asyncio.Event = asyncio.Event()

    async def run_forever() -> None:
        while True:
            await fn()
            try:
                await asyncio.wait_for(done.wait(), period)
            except TimeoutError:
                continue
            else:
                return

    task = asyncio.create_task(run_forever(), name=name, context=contextvars.copy_context())
    try:
        yield
    finally:
        done.set()
        await discard(task)


def current_task() -> asyncio.Task[Any]:
    task = asyncio.current_task()
    assert task is not None
    return task


def discard(fut: asyncio.Future[Any], /, grace_timeout: float = 0.01) -> asyncio.Future[None]:
    async def wait_or_cancel() -> None:
        if fut.done():
            return

        try:
            async with asyncio.timeout(grace_timeout):
                await fut
        except asyncio.CancelledError:
            if not fut.done() or current_task().cancelling() > 0:
                raise
        except TimeoutError:
            return

    return asyncio.shield(wait_or_cancel())
