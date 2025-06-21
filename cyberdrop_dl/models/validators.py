from __future__ import annotations

import re
from datetime import timedelta
from functools import singledispatch
from typing import (
    TYPE_CHECKING,
    Any,
    Concatenate,
    ParamSpec,
    SupportsIndex,
    SupportsInt,
    TypeAlias,
    TypedDict,
    TypeVar,
    overload,
)

from pydantic import AnyUrl, ByteSize, HttpUrl, TypeAdapter

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import yarl


_DATE_PATTERN_REGEX = r"(\d+)\s*(second|seconds|minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)"
_DATE_PATTERN = re.compile(_DATE_PATTERN_REGEX, re.IGNORECASE)
_BYTE_SIZE_ADAPTER = TypeAdapter(ByteSize)
_ConvertibleToInt: TypeAlias = str | SupportsInt | SupportsIndex
P = ParamSpec("P")
T = TypeVar("T")
R = TypeVar("R")


def bytesize_to_str(value: _ConvertibleToInt) -> str:
    if not isinstance(value, ByteSize):
        value = ByteSize(value)
    return value.human_readable(decimal=True)


def to_yarl_url(value: AnyUrl | str, *args, **kwargs) -> yarl.URL:
    from cyberdrop_dl.utils.utilities import parse_url

    try:
        return parse_url(str(value), *args, **kwargs)
    except Exception as e:
        raise ValueError(str(e)) from e


def to_yarl_url_w_pydantyc_validation(value: str) -> yarl.URL:
    url = HttpUrl(value)
    return to_yarl_url(url)


def to_bytesize(value: ByteSize | str | int) -> ByteSize:
    return _BYTE_SIZE_ADAPTER.validate_python(value)


def change_path_suffix(suffix: str) -> Callable[[Path], Path]:
    def with_suffix(value: Path) -> Path:
        return value.with_suffix(suffix)

    return with_suffix


def str_to_timedelta(input_date: str) -> timedelta:
    time_str = input_date.casefold()
    matches: list[str] = re.findall(_DATE_PATTERN, time_str)
    seen_units = set()
    time_dict = {"days": 0}

    for value, unit in matches:
        value = int(value)
        unit = unit.lower()
        normalized_unit = unit.rstrip("s")
        plural_unit = normalized_unit + "s"
        if normalized_unit in seen_units:
            msg = f"Duplicate time unit detected: '{unit}' conflicts with another entry"
            raise ValueError(msg)
        seen_units.add(normalized_unit)

        if "day" in unit:
            time_dict["days"] += value
        elif "month" in unit:
            time_dict["days"] += value * 30
        elif "year" in unit:
            time_dict["days"] += value * 365
        else:
            time_dict[plural_unit] = value

    if not matches:
        msg = f"Unable to convert '{input_date}' to timedelta object"
        raise ValueError(msg)
    return timedelta(**time_dict)


def to_timedelta(input_date: timedelta | str | int) -> timedelta:
    """Parses `datetime.timedelta`, `str` or `int` into a timedelta format.

    For `str`, the expected format is `<value> <unit>`, ex: `5 days`, `10 minutes`, `1 year`

    Valid units:
        `year(s)`, `week(s)`, `day(s)`, `hour(s)`, `minute(s)`, `second(s)`, `millisecond(s)`, `microsecond(s)`

    For `int`, `input_date` is assumed as `days`
    """
    return falsy_as(input_date, timedelta(0), _parse_as_timedelta)


@singledispatch
def _parse_as_timedelta(input_date: timedelta) -> timedelta | str:
    return input_date


@_parse_as_timedelta.register
def _(input_date: int) -> timedelta:
    return timedelta(days=input_date)


@_parse_as_timedelta.register
def _(input_date: str, raise_error: bool = False) -> timedelta | str:
    try:
        return str_to_timedelta(input_date)
    except ValueError:
        if raise_error:
            raise
    return input_date


@overload
def falsy_as(value: T, falsy_value: T | None, func: None = None) -> T | None: ...


@overload
def falsy_as(
    value: T, falsy_value: T | None, func: Callable[Concatenate[T, P], R], *args: P.args, **kwargs: P.kwargs
) -> R | None: ...


def falsy_as(
    value: T,
    falsy_value: T | None,
    func: Callable[Concatenate[T, P], R] | None = None,
    *args: P.args,
    **kwargs: P.kwargs,
) -> T | R | None:
    """If `value` is falsy, returns `falsy_value`

    If `value` is NOT falsy AND `func` is provided, returns `func(value, *args, **kwargs)`

    Returns `value` otherwise
    """
    value_ = value
    if isinstance(value_, str) and value_.casefold() in ("none", "null"):
        value_ = None
    if not value_:
        return falsy_value
    if not func:
        return value_
    return func(value_, *args, **kwargs)


def falsy_as_list(value: Any) -> Any:
    return falsy_as(value, [])


def falsy_as_none(value: Any) -> Any:
    return falsy_as(value, None)


def falsy_as_dict(value: Any) -> Any:
    return falsy_as(value, {})


class AppriseURLDict(TypedDict):
    url: str
    tags: set[str]


@singledispatch
def to_apprise_url_dict(value: yarl.URL) -> AppriseURLDict:
    return {"url": str(value), "tags": set()}


@to_apprise_url_dict.register
def _(value: dict) -> AppriseURLDict:
    tags = value.get("tags") or set()
    url = str(value.get("url", ""))
    if not tags:
        return to_apprise_url_dict(url)

    return {"url": url, "tags": tags}


@to_apprise_url_dict.register
def _(value: str) -> AppriseURLDict:
    tags = set()
    url = value
    parts = url.split("://", 1)[0].split("=", 1)
    if len(parts) == 2:
        tags = set(parts[0].split(","))
        url: str = url.split("=", 1)[-1]

    return {"url": url, "tags": tags}
