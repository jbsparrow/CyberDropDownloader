import calendar
import datetime
from functools import lru_cache
from typing import TYPE_CHECKING, Literal, TypeAlias, TypeVar

import dateparser.date
import dateutil
import dateutil.parser

if TYPE_CHECKING:
    from cyberdrop_dl.types import TimeStamp
else:
    TimeStamp = int

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


if __name__ == "__main__":
    print(parse_date("today at noon"))  # noqa: T201
    print(parse_date("today"))  # noqa: T201
