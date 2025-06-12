import asyncio
import calendar
import datetime
import os
import shutil
import subprocess
import sys
from ctypes import wintypes
from functools import lru_cache
from pathlib import Path
from typing import Literal, NewType, TypeAlias, TypeVar

import dateparser.date
import dateutil
import dateutil.parser

WIN_EPOCH_OFFSET = 116444736e9
MAC_OS_SET_FILE = None

if sys.platform == "win32":
    from ctypes import byref, windll, wintypes

    import win32con

elif sys.platform == "darwin":
    # SetFile is non standard in macOS. Only users that have xcode installed will have SetFile
    MAC_OS_SET_FILE = shutil.which("SetFile")

TimeStamp = NewType("TimeStamp", int)
MIDNIGHT_TIME = datetime.time.min
DATE_NOT_FOUND = dateparser.date.DateData(date_obj=None, period="day")
DateOrder: TypeAlias = Literal["DMY", "DYM", "MDY", "MYD", "YDM", "YMD"]
ParserKind: TypeAlias = Literal["timestamp", "relative-time", "custom-formats", "absolute-time", "no-spaces-time"]
DEFAULT_PARSERS: list[ParserKind] = ["relative-time", "custom-formats", "absolute-time", "no-spaces-time"]
DEFAULT_DATE_ORDER = "MDY"

_S = TypeVar("_S", bound=str)


def coerce_to_list(value: _S | set[_S] | list[_S] | tuple[_S, ...] | None) -> list[_S]:
    if value is None:
        return []
    if isinstance(value, tuple | set):
        return list(value)
    if isinstance(value, list):
        return value
    return [value]


class DateParser(dateparser.date.DateDataParser):
    """Parses incomplete dates, but they must have at least a known year and month

    Parsed dates are garantied to be in the past with time at midnight (if unknown)

    It can parse date strings like:

    `relative-time`:
    >>> "Today"
    >>> "Yesterday"
    >>> "1 hour ago"
    >>> "1 year, 2 months ago"
    >>> "3 hours, 50 minutes ago

    `absolute-time`:
    >>> "Fri, 12 Dec 2014 10:55:50"

    `no-spaces-time`:
    >>> "10032022"

    `timestamp`:
    >>> "1747880678"

    `custom-formats`
    """

    def __init__(
        self, parsers: list[ParserKind] | ParserKind | None = None, date_order: DateOrder | None = None
    ) -> None:
        date_order = date_order or DEFAULT_DATE_ORDER
        parsers = coerce_to_list(parsers) or DEFAULT_PARSERS
        super().__init__(
            settings={
                "DATE_ORDER": date_order,
                "PREFER_DAY_OF_MONTH": "first",
                "PREFER_DATES_FROM": "past",
                "REQUIRE_PARTS": ["year", "month"],
                "RETURN_TIME_AS_PERIOD": True,
                "PARSERS": parsers,
            }
        )

    def parse_with_locales(
        self, date_string: str, date_formats: list[str] | str | None = None
    ) -> tuple[datetime.datetime, str] | tuple[None, None]:
        date_string = dateparser.date.sanitize_date(date_string)
        date_formats = coerce_to_list(date_formats)
        parse = dateparser.date._DateLocaleParser.parse
        for locale in self._get_applicable_locales(date_string):
            date_data = parse(locale, date_string, date_formats, settings=self._settings)
            if not date_data or not date_data.date_obj:
                continue

            return date_data.date_obj, date_data.period or ""
        return None, None

    def parse_possible_incomplete_date(
        self, date_string: str, date_formats: list[str] | str | None = None
    ) -> datetime.datetime | None:
        date_formats = coerce_to_list(date_formats)
        date_data = dateparser.date.parse_with_formats(date_string, date_formats, self._settings)
        return date_data.date_obj

    def parse_human_date(
        self, date_string: str, date_formats: list[str] | str | None = None
    ) -> datetime.datetime | None:
        parsed_date, period = self.parse_with_locales(date_string, date_formats)
        if parsed_date:
            date_had_time = period == "time"
            if date_had_time:
                return parsed_date
            return remove_time_if_not_midnight(parsed_date)


def remove_time_if_not_midnight(date: datetime.datetime) -> datetime.datetime:
    if date.time() != MIDNIGHT_TIME:
        date_at_midnight = datetime.datetime.combine(date.date(), MIDNIGHT_TIME)
        return date_at_midnight
    return date


def parse_date(
    date_string: str,
    date_formats: list[str] | str | None = None,
    /,
    parser_kind: ParserKind | None = None,
    date_order: DateOrder | None = None,
) -> datetime.datetime | None:
    parser = get_parser(parser_kind, date_order)
    date = parser.parse_possible_incomplete_date(date_string, date_formats)
    return date or parser.parse_human_date(date_string, date_formats)


def parse_concrete_date(date_string: str, date_format: str) -> datetime.datetime | None:
    try:
        if date_format:
            parsed_date = datetime.datetime.strptime(date_string, date_format)
        else:
            parsed_date = dateutil.parser.parse(date_string)
    except (ValueError, TypeError, dateutil.parser.ParserError):
        pass
    else:
        return parsed_date


def to_timestamp(date: datetime.datetime) -> TimeStamp:
    return TimeStamp(calendar.timegm(date.timetuple()))


@lru_cache(maxsize=10)
def get_parser(parser_kind: ParserKind | None = None, date_order: DateOrder | None = None) -> DateParser:
    return DateParser(parser_kind, date_order)


async def set_file_datetime(datetime_or_timestamp: datetime.datetime | TimeStamp, file: Path) -> None:
    if isinstance(datetime_or_timestamp, datetime.datetime):
        timestamp = to_timestamp(datetime_or_timestamp)
    else:
        timestamp = datetime_or_timestamp
    try:
        if sys.platform == "win32":
            await _set_win_time(timestamp, file)

        elif sys.platform == "darwin":
            await _set_macos_time(timestamp, file)

    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, ValueError):
        pass

    # 2. try setting modification and access date
    try:
        await asyncio.to_thread(os.utime, file, (timestamp, timestamp))
    except OSError:
        pass


async def _set_macos_time(timestamp: TimeStamp, file: Path) -> None:
    if not MAC_OS_SET_FILE:
        return
    date_string = datetime.datetime.fromtimestamp(timestamp).strftime("%m/%d/%Y %H:%M:%S")
    cmd = ["-d", date_string, file]
    process = await asyncio.subprocess.create_subprocess_exec(
        MAC_OS_SET_FILE, *cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    _ = await process.wait()


async def _set_win_time(timestamp: TimeStamp, file: Path) -> None:
    def set_win_time() -> None:
        nano_ts: float = timestamp * 1e7  # Windows uses nano seconds for dates
        win_timestamp = int(nano_ts + WIN_EPOCH_OFFSET)

        # Windows dates are 64bits, split into 2 32bits unsigned ints (dwHighDateTime , dwLowDateTime)
        # XOR to get the date as bytes, then shift to get the first 32 bits (dwHighDateTime)
        ctime = wintypes.FILETIME(win_timestamp & 0xFFFFFFFF, win_timestamp >> 32)
        access_mode = 256  # FILE_WRITE_ATTRIBUTES
        sharing_mode = 0  # Exclusive access
        security_mode = None  # Use default security attributes
        creation_disposition = win32con.OPEN_EXISTING

        # FILE_FLAG_BACKUP_SEMANTICS allows access to directories
        flags = win32con.FILE_ATTRIBUTE_NORMAL | win32con.FILE_FLAG_BACKUP_SEMANTICS
        template_file = None

        params = (
            access_mode,
            sharing_mode,
            security_mode,
            creation_disposition,
            flags,
            template_file,
        )

        handle = windll.kernel32.CreateFileW(str(file), *params)
        windll.kernel32.SetFileTime(
            handle,
            byref(ctime),  # Creation time
            None,  # Access time
            None,  # Modification time
        )
        windll.kernel32.CloseHandle(handle)

    await asyncio.to_thread(set_win_time)


if __name__ == "__main__":
    print(parse_date("today at noon"))  # noqa: T201
    print(parse_date("today"))  # noqa: T201
