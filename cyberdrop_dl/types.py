"""Custom types for type annotations


1. Only add types here if they do NOT depend on any runtime import from `cyberdrop_dl` itself
2. Only add types here if they are going to be used across multiple modules
"""

from __future__ import annotations

import enum
import functools
import inspect
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, Literal, NewType, ParamSpec, TypeAlias, TypeVar, overload

import yarl

P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T")


def copy_signature(target: Callable[P, R]) -> Callable[[Callable[..., T]], Callable[P, T]]:
    """Decorator to make a function mimic the signature of another function,
    but preserve the return type of the decorated function."""

    def decorator(func: Callable[..., T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return func(*args, **kwargs)

        wrapper.__signature__ = inspect.signature(target).replace(  # type: ignore
            return_annotation=inspect.signature(func).return_annotation
        )
        return wrapper

    return decorator


if TYPE_CHECKING:
    from propcache.api import under_cached_property as cached_property
    from yarl._query import Query, QueryVariable

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


Array: TypeAlias = list[T] | tuple[T, ...]
CMD: TypeAlias = Array[str]
U32Int: TypeAlias = int
U32IntArray: TypeAlias = Array[U32Int]
U32IntSequence: TypeAlias = Sequence[U32Int]
AnyDict: TypeAlias = dict[str, Any]

AbsolutePath = NewType("AbsolutePath", Path)
TimeStamp = NewType("TimeStamp", int)

StrMap: TypeAlias = Mapping[str, T]
OneOrTuple: TypeAlias = T | tuple[T, ...]
SupportedPaths: TypeAlias = StrMap[OneOrTuple[str]]
SupportedDomains: TypeAlias = OneOrTuple[str]


EnumMemberT = TypeVar("EnumMemberT", bound=enum.Enum)
EnumBaseT = TypeVar("EnumBaseT")


class ContainerEnumType(Generic[EnumBaseT], enum.EnumType):
    _member_names_: list[str]
    _member_map_: dict[str, enum.Enum]

    def values(cls: type[EnumMemberT]) -> tuple[EnumBaseT, ...]:  # type: ignore[reportGeneralTypeIssues]
        return tuple(member.value for member in cls)

    if sys.version_info < (3, 12):

        def __contains__(cls: type[EnumMemberT], member: object) -> bool:  # type: ignore[reportGeneralTypeIssues]
            if isinstance(member, cls):
                return True
            try:
                cls(member)
                return True
            except ValueError:
                return False

        def __iter__(cls: type[EnumMemberT]) -> Iterator[EnumMemberT]:  # type: ignore[reportGeneralTypeIssues]
            return (cls._member_map_[name] for name in cls._member_names_)  # type: ignore[reportReturnType]


class Enum(enum.Enum, metaclass=ContainerEnumType[Any]): ...


class IntEnum(enum.IntEnum, metaclass=ContainerEnumType[int]): ...


class StrEnum(enum.StrEnum, metaclass=ContainerEnumType[str]): ...


class MayBeUpperStrEnum(StrEnum):
    @classmethod
    def __missing__(cls: type[EnumMemberT], value: str) -> EnumMemberT:
        return cls[value.upper()]
