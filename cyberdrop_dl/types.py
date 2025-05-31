"""Custom types for type annotations


1. Only add types here if they do NOT depend on any runtime import from `cyberdrop_dl` itself, except utils
2. Only add types here if they are going to be used across multiple modules
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Literal, NewType, ParamSpec, TypeAlias, TypeVar, overload

import yarl

P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T")


if TYPE_CHECKING:
    import functools
    import inspect

    from propcache.api import under_cached_property as cached_property
    from yarl._query import Query, QueryVariable

    def copy_signature(target: Callable[P, R]) -> Callable[[Callable[..., T]], Callable[P, T]]:
        def decorator(func: Callable[..., T]) -> Callable[P, T]:
            @functools.wraps(func)
            def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                return func(*args, **kwargs)

            wrapper.__signature__ = inspect.signature(target).replace(  # type: ignore
                return_annotation=inspect.signature(func).return_annotation
            )
            return wrapper

        return decorator

    class AbsoluteHttpURL(yarl.URL):
        @copy_signature(yarl.URL.__new__)
        def __new__(cls) -> AbsoluteHttpURL: ...

        @copy_signature(yarl.URL.__truediv__)
        def __truediv__(self) -> AbsoluteHttpURL: ...

        @copy_signature(yarl.URL.__mod__)
        def __mod__(self) -> AbsoluteHttpURL: ...

        @cached_property
        def host(self) -> str: ...

        @cached_property
        def scheme(self) -> Literal["http", "https"]: ...

        @cached_property
        def absolute(self) -> Literal[True]: ...

        @cached_property
        def parent(self) -> AbsoluteHttpURL: ...

        @copy_signature(yarl.URL.with_path)
        def with_path(self) -> AbsoluteHttpURL: ...

        @copy_signature(yarl.URL.with_host)
        def with_host(self) -> AbsoluteHttpURL: ...

        @copy_signature(yarl.URL.origin)
        def origin(self) -> AbsoluteHttpURL: ...

        @overload
        def with_query(self, query: Query) -> AbsoluteHttpURL: ...

        @overload
        def with_query(self, **kwargs: QueryVariable) -> AbsoluteHttpURL: ...

        @copy_signature(yarl.URL.with_query)
        def with_query(self) -> AbsoluteHttpURL: ...

        @overload
        def extend_query(self, query: Query) -> AbsoluteHttpURL: ...

        @overload
        def extend_query(self, **kwargs: QueryVariable) -> AbsoluteHttpURL: ...

        @copy_signature(yarl.URL.extend_query)
        def extend_query(self) -> AbsoluteHttpURL: ...

        @overload
        def update_query(self, query: Query) -> AbsoluteHttpURL: ...

        @overload
        def update_query(self, **kwargs: QueryVariable) -> AbsoluteHttpURL: ...

        @copy_signature(yarl.URL.update_query)
        def update_query(self) -> AbsoluteHttpURL: ...

        @copy_signature(yarl.URL.without_query_params)
        def without_query_params(self) -> AbsoluteHttpURL: ...

        @copy_signature(yarl.URL.with_fragment)
        def with_fragment(self) -> AbsoluteHttpURL: ...

        @copy_signature(yarl.URL.with_name)
        def with_name(self) -> AbsoluteHttpURL: ...

        @copy_signature(yarl.URL.with_suffix)
        def with_suffix(self) -> AbsoluteHttpURL: ...

        @copy_signature(yarl.URL.join)
        def join(self) -> AbsoluteHttpURL: ...

        @copy_signature(yarl.URL.joinpath)
        def joinpath(self) -> AbsoluteHttpURL: ...

else:
    AbsoluteHttpURL = yarl.URL


AnyURL = TypeVar("AnyURL", yarl.URL, AbsoluteHttpURL)


Array: TypeAlias = list[T] | tuple[T, ...]
CMD: TypeAlias = Array[str]
U32Int: TypeAlias = int
U32IntArray: TypeAlias = Array[U32Int]
U32IntSequence: TypeAlias = Sequence[U32Int]
AnyDict: TypeAlias = dict[str, Any]

HashValue = NewType("HashValue", str)
TimeStamp = NewType("TimeStamp", int)

StrMap: TypeAlias = Mapping[str, T]
OneOrTuple: TypeAlias = T | tuple[T, ...]
SupportedPaths: TypeAlias = StrMap[OneOrTuple[str]]
SupportedDomains: TypeAlias = OneOrTuple[str]
