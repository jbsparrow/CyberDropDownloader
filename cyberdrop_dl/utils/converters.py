"""
Functions to use with `AfterValidator`, `field_validator(mode="after")` or `model_validator(mode="after")`
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import TYPE_CHECKING

from pydantic import AnyUrl, ByteSize, TypeAdapter

from cyberdrop_dl.exceptions import InvalidURLError
from cyberdrop_dl.utils.utilities import parse_url

if TYPE_CHECKING:
    from pathlib import Path

    import yarl

DATE_PATTERN_REGEX = r"(\d+)\s*(second|seconds|minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)"
DATE_PATTERN = re.compile(DATE_PATTERN_REGEX, re.IGNORECASE)

byte_size_adapter = TypeAdapter(ByteSize)


def convert_byte_size_to_str(value: ByteSize) -> str:
    if not isinstance(value, ByteSize):
        value = ByteSize(value)
    return value.human_readable(decimal=True)


def convert_to_yarl(value: AnyUrl | str, *args, **kwargs) -> yarl.URL:
    try:
        return parse_url(str(value), *args, **kwargs)
    except (InvalidURLError, TypeError) as e:
        raise ValueError(str(e)) from e


def change_path_suffix(value: Path, suffix: str) -> Path:
    return value.with_suffix(suffix)


def convert_to_byte_size(value: ByteSize | str | int) -> ByteSize:
    return byte_size_adapter.validate_python(value)


def convert_str_to_timedelta(input_date: str) -> timedelta:
    time_str = input_date.casefold()
    matches: list[str] = re.findall(DATE_PATTERN, time_str)
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
