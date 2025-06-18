from __future__ import annotations

import enum
import sys
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Iterator

T = TypeVar("T")


if sys.version_info < (3, 12):
    _EnumMemberT = TypeVar("_EnumMemberT", bound=enum.Enum)

    class _ContainerEnumType(enum.EnumType):
        _member_names_: list[str]
        _member_map_: dict[str, enum.Enum]

        def __contains__(cls: type[_EnumMemberT], member: object) -> bool:  # type: ignore[reportGeneralTypeIssues]
            if isinstance(member, cls):
                return True
            try:
                cls(member)
                return True
            except ValueError:
                return False

        def __iter__(cls: type[_EnumMemberT]) -> Iterator[_EnumMemberT]:  # type: ignore[reportGeneralTypeIssues]
            return (cls._member_map_[name] for name in cls._member_names_)  # type: ignore[reportReturnType]

    class Enum(enum.Enum, metaclass=_ContainerEnumType): ...

    class IntEnum(enum.IntEnum, metaclass=_ContainerEnumType): ...

    class StrEnum(enum.StrEnum, metaclass=_ContainerEnumType): ...


else:
    Enum = enum.Enum
    IntEnum = enum.IntEnum
    StrEnum = enum.StrEnum


class MayBeUpperStrEnum(StrEnum):
    @classmethod
    def __missing__(cls: type[_EnumMemberT], value: str) -> _EnumMemberT:
        return cls[value.upper()]
