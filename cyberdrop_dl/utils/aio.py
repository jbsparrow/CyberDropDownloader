"""Async versions of builtins and some path operations"""

from __future__ import annotations

import asyncio
import builtins
import pathlib
from stat import S_ISREG
from typing import TYPE_CHECKING, ParamSpec, TypeVar, cast

if TYPE_CHECKING:
    from collections.abc import Awaitable, Sequence

    _P = ParamSpec("_P")
    _T = TypeVar("_T")
    _R = TypeVar("_R")


async def gather(coros: Sequence[Awaitable[_T]], batch_size: int = 10) -> list[_T]:
    """Like `asyncio.gather`, but creates tasks lazily to minimize event loop overhead.

    This function ensures there are never more than `batch_size` tasks created at any given time.

    If any exception is raised within a task, all currently running tasks
    are cancelled and any renaming task in the queue will be ignored.
    """

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

    # Manually parse stat result to make sure we only use 1 fs call

    try:
        stat_result = await stat(path)
    except OSError as e:
        if not pathlib._ignore_error(e):  # type: ignore[reportAttributeAccessIssue]
            raise
        return
    except ValueError:
        return
    else:
        if S_ISREG(stat_result.st_mode):
            return stat_result.st_size
