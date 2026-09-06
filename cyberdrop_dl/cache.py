from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import functools
import json
import logging
import time
from typing import TYPE_CHECKING, Any, Protocol, Self, TypedDict, cast, overload

from cyberdrop_dl import __version__
from cyberdrop_dl.constants import MISSING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Coroutine, Generator
    from pathlib import Path
    from types import CoroutineType

    from typing_extensions import Sentinel

logger = logging.getLogger(__name__)
_IN_MEMORY_CACHE: dict[str, Any] = {}


class CachedAsyncFunc[T](Protocol):
    def __call__(self) -> CoroutineType[Any, Any, T]: ...

    def clear(self) -> None: ...

    def get(self) -> T | None: ...


class _CachedValue[T](TypedDict):
    value: T
    ttl: float | None
    created_at: float


def _load_cache(content: str) -> dict[str, Any]:
    if not content:
        return {}
    data = json.loads(content)
    if type(data) is not dict:
        raise TypeError("Cache content should be a JSON map")
    return data


def _dump_cache(cache_file: Path, cache: dict[str, Any]):
    cache["version"] = __version__
    cache_file.write_text(json.dumps(cache, indent=2, ensure_ascii=False, sort_keys=True))


@contextlib.contextmanager
def cache_context(cache_file: Path, cache: dict[str, Any]) -> Generator[None]:
    # TODO: Add a background task to dump cache to disk every 5 minutes
    try:
        content = cache_file.read_text()
    except FileNotFoundError:
        cache_file.parent.mkdir(exist_ok=True, parents=True)
        cache_file.touch()
    else:
        try:
            cache.update(_load_cache(content))
        except (json.JSONDecodeError, TypeError) as e:
            error = RuntimeError(f"Unable to read cache file at '{cache_file}'")
            error.add_note("Cache is corrupted. Run `cyberdrop-dl cache clear` to delete the file")
            raise error from e
    try:
        yield
    finally:
        _dump_cache(cache_file, cache)


@dataclasses.dataclass(slots=True)
class TTLCacheAdapter[T]:
    _cache: dict[str, Any]
    _keys: tuple[str, ...] = ()
    __root: dict[str, _CachedValue[Any]] = dataclasses.field(init=False, repr=False)

    def create_child(self, *keys: str) -> Self:
        if not keys:
            return self
        return type(self)(self._root, keys)

    def _lookup_path(self, *keys: str) -> str:
        return ".".join([*self._keys, *keys])

    @property
    def _root(self) -> dict[str, _CachedValue[Any]]:
        try:
            return self.__root
        except AttributeError:
            root = self._cache
            for key in self._keys:
                try:
                    root = root.setdefault(key, {})
                except (KeyError, TypeError, ValueError, AttributeError):
                    logger.exception(f"Invalid cache entry {self._lookup_path()}, ignoring")
                    root = {}
                    break

            self.__root = root
            return self.__root

    def __getitem__(self, key: str, /) -> T:
        return self._get_value(key)

    def _get_value(self, key: str, ttl: float | None = MISSING) -> T:
        """Same as `self[key]`, but `ttl` (when given) overrides the one stored in the entry."""
        cache_hit = self._get(key, ttl)
        if cache_hit is MISSING:
            raise KeyError(key)
        return cache_hit["value"]

    def _has_expired(self, key: str, cache_hit: _CachedValue[T], ttl: float | Sentinel | None = MISSING) -> bool:
        try:
            return _has_expired(cache_hit, ttl)
        except (KeyError, TypeError, ValueError, AttributeError):
            logger.exception(f"Invalid cache entry {self._lookup_path(key)}, ignoring")
            return True

    def _get(self, key: str, ttl: float | Sentinel | None = MISSING) -> _CachedValue[T] | MISSING:  # pyright: ignore[reportInvalidTypeForm]
        try:
            cache_hit = self._root[key]
        except KeyError:
            return MISSING

        if self._has_expired(key, cache_hit, ttl):
            del self[key]
            return MISSING
        return cache_hit

    def __delitem__(self, key: str) -> None:
        del self._root[key]

    def get(self, key: str, ttl: float | Sentinel | None = MISSING) -> T | None:
        cache_hit = self._get(key, ttl)
        return None if cache_hit is MISSING else cache_hit["value"]

    def save(self, key: str, value: T, *, ttl: float | None = None) -> None:
        """NOTE: cached values MUST be JSON serializable"""
        self._root[key] = {
            "value": value,
            "ttl": ttl,
            "created_at": time.time(),
        }

    def __setitem__(self, name: str, value: T) -> None:
        """NOTE: cached values MUST be JSON serializable"""
        self.save(name, value, ttl=None)

    def discard(self, key: str) -> None:
        try:
            del self[key]
        except KeyError:
            return


def _has_expired(self: _CachedValue[Any], ttl: float | Sentinel | None = MISSING) -> bool:
    """Check expiry against `ttl`, falling back to the TTL stored in the entry.

    Callers that know the current TTL should pass it. The stored value is only a snapshot of
    what the TTL was when the entry was written, so trusting it means a shorter TTL never
    applies to entries that already exist.
    """
    effective_ttl: float | None = self["ttl"] if ttl is MISSING else cast("float | None", ttl)
    if effective_ttl is None:
        return False
    return time.time() - self["created_at"] >= effective_ttl


def _ttl_from_callable[T](fn: Callable[..., Awaitable[T]]) -> TTLCacheAdapter[T]:
    *parts, _ = ".".join([fn.__module__, fn.__qualname__]).split(".")
    return TTLCacheAdapter(_IN_MEMORY_CACHE, tuple(parts))


class _HasTTLCache[T](Protocol):
    @property
    def cache(self) -> TTLCacheAdapter[T]: ...


type _SupportsDiskCacheCallable[T] = Callable[[_HasTTLCache[Any]], Awaitable[T]]


class _CachedMethod[T, R]:
    """Use as a class method decorator."""

    def __init__(self, fn: Callable[[Any], Awaitable[R]], key: tuple[str, ...] | str | None, ttl: float | None) -> None:
        self.wrapped: Callable[[Any], Awaitable[R]] = fn
        self.__doc__ = fn.__doc__
        self.name: str = fn.__name__
        self.key: tuple[str, ...] | str = key or fn.__name__
        self.ttl: float | None = ttl
        self._cached_fn: CachedAsyncFunc[R] | None = None

    def _get_cache(self, inst: T) -> TTLCacheAdapter[R]:  # pyright: ignore[reportUnusedParameter]
        raise NotImplementedError

    @overload
    def __get__(self, inst: None, owner: type[object] | None = None) -> Self: ...

    @overload
    def __get__(self, inst: T, owner: type[object] | None = None) -> CachedAsyncFunc[R]: ...

    def __get__(self, inst: T | None, owner: type[object] | None = None) -> CachedAsyncFunc[R] | Self:
        if inst is None:
            return self

        if self._cached_fn is None:

            async def call_method() -> R:
                return await self.wrapped(inst)

            self._cached_fn = cached_fn(call_method, self._get_cache(inst), key=self.key, ttl=self.ttl)
        return self._cached_fn


class _InMemoryCachedMethod[R](_CachedMethod[object, R]):
    def _get_cache(self, inst: object) -> TTLCacheAdapter[R]:  # noqa: ARG002
        return _ttl_from_callable(self.wrapped)


class _DiskCachedMethod[R](_CachedMethod[_HasTTLCache[Any], R]):
    def _get_cache(self, inst: _HasTTLCache[Any]) -> TTLCacheAdapter[R]:
        return inst.cache


def _normalize_key(key: tuple[str, ...] | str) -> tuple[list[str], str]:
    keys = key
    if isinstance(keys, str):
        keys = keys.split(".")

    *parent_keys, key = keys
    return parent_keys, key


def cached_fn[T](
    fn: Callable[[], Awaitable[T]],
    cache: TTLCacheAdapter[T] | None = None,
    *,
    key: tuple[str, ...] | str | None = None,
    ttl: float | None = None,
) -> CachedAsyncFunc[T]:

    parent_keys, key = _normalize_key(key or fn.__name__)
    cache = cache or _ttl_from_callable(fn)
    cache = cache.create_child(*parent_keys)
    lock = asyncio.Lock()

    @functools.wraps(fn)
    async def wrapper() -> T:
        with contextlib.suppress(KeyError):
            return cache._get_value(key, ttl)

        async with lock:
            with contextlib.suppress(KeyError):
                return cache._get_value(key, ttl)

            value = await fn()
            cache.save(key, value, ttl=ttl)
            return value

    wrapper.clear = lambda: cache.discard(key)  # pyright: ignore[reportAttributeAccessIssue]
    wrapper.get = lambda: cache.get(key, ttl)  # pyright: ignore[reportAttributeAccessIssue]
    return cast("CachedAsyncFunc[T]", cast("object", wrapper))


def cached_method[T](
    key: tuple[str, ...] | str | None = None, *, ttl: float | None = None
) -> Callable[[Callable[[Any], Coroutine[Any, Any, T]]], _InMemoryCachedMethod[T]]:
    """Keep the last result of this method in memory until TTL expires

    TTL == None -> never expires"""

    def wrapper(method: Callable[[object], Awaitable[T]]) -> _InMemoryCachedMethod[T]:
        return _InMemoryCachedMethod(method, key, ttl)

    return wrapper


def disk_cached_method[T](
    key: tuple[str, ...] | str | None = None, *, ttl: float | None = None
) -> Callable[[Callable[[Any], Coroutine[Any, Any, T]]], _DiskCachedMethod[T]]:
    """Keep the last result of this method in memory until TTL expires

    Cached values will persist across runs (saved to cache.json file)"""

    def wrapper(method: _SupportsDiskCacheCallable[T]) -> _DiskCachedMethod[T]:
        return _DiskCachedMethod(method, key, ttl)

    return wrapper
