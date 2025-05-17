"""
Functions to use with `BeforeValidator`, `field_validator(mode="before")` or `model_validator(mode="before")`
"""

from __future__ import annotations

from datetime import timedelta
from functools import singledispatch
from typing import TYPE_CHECKING, Any

from pydantic import HttpUrl

from cyberdrop_dl.utils.converters import convert_str_to_timedelta, convert_to_yarl

if TYPE_CHECKING:
    from collections.abc import Callable

    from yarl import URL


def pydantyc_yarl_url(value: str) -> URL:
    url = HttpUrl(value)
    return convert_to_yarl(url)


def parse_falsy_as(value: Any, falsy_value: Any, func: Callable | None = None, *args, **kwargs) -> Any:
    """If `value` is falsy, returns `falsy_value`

    If `value` is NOT falsy AND `func` is provided, returns `func(value, *args, **kwargs)`

    Returns `value` otherwise
    """
    if isinstance(value, str) and value.casefold() in ("none", "null"):
        value = None
    if not value:
        return falsy_value
    if not func:
        return value
    return func(value, *args, **kwargs)


def parse_duration_as_timedelta(input_date: timedelta | str | int) -> timedelta:
    """Parses `datetime.timedelta`, `str` or `int` into a timedelta format.

    For `str`, the expected format is `<value> <unit>`, ex: `5 days`, `10 minutes`, `1 year`

    Valid units:
        `year(s)`, `week(s)`, `day(s)`, `hour(s)`, `minute(s)`, `second(s)`, `millisecond(s)`, `microsecond(s)`

    For `int`, `input_date` is assumed as `days`
    """
    return parse_falsy_as(input_date, timedelta(0), _parse_as_timedelta)


@singledispatch
def _parse_as_timedelta(input_date: timedelta) -> timedelta | str:
    return input_date


@_parse_as_timedelta.register
def _(input_date: int) -> timedelta:
    return timedelta(days=input_date)


@_parse_as_timedelta.register
def _(input_date: str, raise_error: bool = False) -> timedelta | str:
    try:
        return convert_str_to_timedelta(input_date)
    except ValueError:
        if raise_error:
            raise
    return input_date


def parse_list(value: list):
    return parse_falsy_as(value, [])


def parse_falsy_as_none(value: Any):
    return parse_falsy_as(value, None)


@singledispatch
def parse_apprise_url(value: URL) -> dict:
    return {"url": str(value), "tags": set()}


@parse_apprise_url.register
def _(value: dict) -> dict:
    tags = value.get("tags") or set()
    url = str(value.get("url", ""))
    if not tags:
        return parse_apprise_url(url)

    return {"url": url, "tags": tags}


@parse_apprise_url.register
def _(value: str) -> dict:
    tags = set()
    url = value
    parts = url.split("://", 1)[0].split("=", 1)
    if len(parts) == 2:
        tags = set(parts[0].split(","))
        url: str = url.split("=", 1)[-1]

    return {"url": url, "tags": tags}
