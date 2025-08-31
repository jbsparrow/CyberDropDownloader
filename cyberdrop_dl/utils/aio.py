"""Async versions of builtins and some path operations"""

from __future__ import annotations

import asyncio
import builtins
from collections.abc import AsyncIterable, Awaitable, Sized
from typing import TYPE_CHECKING, ParamSpec, TypeVar, cast

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable, Iterable

    _P = ParamSpec("_P")
    _T = TypeVar("_T")
    _R = TypeVar("_R")


async def enumerate(
    iterable: Iterable[_T],
    batch_size: int = 200,
    start: int = 0,
) -> AsyncIterable[tuple[int, _T]]:
    """Asynchronously enumerates a normal iterable.

    Calls `asyncio.sleep(0)` after a batch of `batch_size` items have been processed.
    """

    if isinstance(iterable, Sized):
        size = len(iterable)
        if size == 0:
            return
        elif size <= batch_size:
            for pair in builtins.enumerate(iterable, start):
                yield pair
            return

    for index, value in builtins.enumerate(iterable, start):
        yield index, value
        if (index + 1) % batch_size == 0:
            await asyncio.sleep(0)


async def iter(iterable: Iterable[_T], batch_size: int = 200) -> AsyncIterable[_T]:
    """Asynchronously yield values from a normal iterable.

    Calls `asyncio.sleep(0)` after a batch of `batch_size` items have been processed.
    """
    async for _, value in enumerate(iterable, batch_size):
        yield value


async def filterfalse(
    predicate: Callable[[_T], bool], iterable: Iterable[_T], batch_size: int = 200
) -> AsyncIterable[_T]:
    """Like itertool.filterfase, yields those items for which the predicate is `False`.

    Calls `asyncio.sleep(0)` after a batch of `batch_size` items have been processed.
    """

    async for value in iter(iterable, batch_size):
        skip = predicate(value)
        if skip:
            continue

        yield value


async def gather(*coros: Awaitable[_T], batch_size: int = 10) -> list[_T]:
    """Like `asyncio.gather`, but creates tasks lazily to minimize event loop overhead.

    This function ensures there are never more than `batch_size` tasks created at any given time.

    If any exception is raised within a task, all currently running tasks
    are cancelled and any remaning task in the queue will be ignored.
    """

    # TODO: Use this function for HLS downloads to prevent creating thousands of tasks
    # for each segment (most of them wait forever becuase they use the same semaphore)

    semaphore = asyncio.BoundedSemaphore(batch_size)
    results: list[_T] = cast("list[_T]", [None] * len(coros))

    async def worker(index: int, coro: Awaitable[_T]):
        try:
            result = await coro
            results[index] = result
        finally:
            semaphore.release()

    async with asyncio.TaskGroup() as tg:
        for index, coro in builtins.enumerate(coros):
            await semaphore.acquire()
            tg.create_task(worker(index, coro))

    return results


async def stat(path: pathlib.Path):
    return await asyncio.to_thread(path.stat)


async def is_dir(path: pathlib.Path) -> bool:
    return await asyncio.to_thread(path.is_dir)


async def is_file(path: pathlib.Path) -> bool:
    return await asyncio.to_thread(path.is_file)


async def exists(path: pathlib.Path) -> bool:
    return await asyncio.to_thread(path.exists)


async def unlink(path: pathlib.Path, missing_ok: bool = False) -> None:
    return await asyncio.to_thread(path.unlink, missing_ok)


async def get_size(path: pathlib.Path) -> int | None:
    """If path exists and is a file, returns its size. Returns `None` otherwise"""

    def size_():
        if path.is_file():
            return path.stat().st_size

    return await asyncio.to_thread(size_)
