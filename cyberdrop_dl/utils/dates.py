import datetime
import email.utils
import re
from functools import lru_cache
from typing import Literal, NewType, TypeAlias, TypeVar

import dateparser.date

TimeStamp = NewType("TimeStamp", int)
MIDNIGHT_TIME = datetime.time.min
DATE_NOT_FOUND = dateparser.date.DateData(date_obj=None, period="day")
DateOrder: TypeAlias = Literal["DMY", "DYM", "MDY", "MYD", "YDM", "YMD"]
ParserKind: TypeAlias = Literal["timestamp", "relative-time", "custom-formats", "absolute-time", "no-spaces-time"]
DEFAULT_PARSERS: list[ParserKind] = ["relative-time", "custom-formats", "absolute-time", "no-spaces-time"]
DEFAULT_DATE_ORDER = "MDY"
DATEPARSER_PATCHED = False

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

    Parsed dates are guaranteed to be in the past with time at midnight (if unknown)

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
            languages=["en"],
            try_previous_locales=True,
            settings={
                "DATE_ORDER": date_order,
                "PREFER_DAY_OF_MONTH": "first",
                "PREFER_DATES_FROM": "past",
                "REQUIRE_PARTS": ["month"],
                "RETURN_TIME_AS_PERIOD": True,
                "PARSERS": parsers,
            },
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
        self, date_string: str, date_formats: list[str] | str
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


def parse_human_date(
    date_string: str,
    date_formats: list[str] | str | None = None,
    /,
    parser_kind: ParserKind | None = None,
    date_order: DateOrder | None = None,
) -> datetime.datetime | None:
    parser = get_parser(parser_kind, date_order)
    if date_formats and (parsed_date := parser.parse_possible_incomplete_date(date_string, date_formats)):
        return parsed_date
    return parser.parse_human_date(date_string, date_formats)


def to_timestamp(date: datetime.datetime) -> TimeStamp:
    return TimeStamp(int(date.timestamp()))


@lru_cache(maxsize=10)
def get_parser(parser_kind: ParserKind | None = None, date_order: DateOrder | None = None) -> DateParser:
    return DateParser(parser_kind, date_order)


def parse_aware_iso_datetime(value: str) -> datetime.datetime | None:
    try:
        parsed_date = datetime.datetime.fromisoformat(value)
        return ensure_tz(parsed_date)
    except Exception:
        return


def ensure_tz(date_time: datetime.datetime) -> datetime.datetime:
    if date_time.tzinfo is None:
        return date_time.replace(tzinfo=datetime.UTC)
    return date_time


def parse_http_date(date: str) -> int:
    """parse rfc 2822 or an "HTTP-date" format as defined by RFC 9110"""
    date_time = email.utils.parsedate_to_datetime(date)
    return to_timestamp(ensure_tz(date_time))


def _prepare_format(date_string: str, og_format: str) -> tuple[str, str]:
    # Adapted from std lib: https://github.com/python/cpython/blob/e34a5e33049ce845de646cf24a498766a2da3586/Lib/_strptime.py#L448
    format = re.sub(r"([\\.^$*+?\(\){}\[\]|])", r"\\\1", og_format)
    format = re.sub(r"\s+", r"\\s+", format)
    format = re.sub(r"'", "['\u02bc]", format)
    year_in_format = False
    day_of_month_in_format = False

    def repl(m: re.Match[str]) -> str:
        format_char = m[1]
        if format_char in ("Y", "y", "G"):
            nonlocal year_in_format
            year_in_format = True
        elif format_char in "d":
            nonlocal day_of_month_in_format
            day_of_month_in_format = True

        return ""

    _ = re.sub(r"%[-_0^#]*[0-9]*([OE]?\\?.?)", repl, format)
    if day_of_month_in_format and not year_in_format:
        current_year = datetime.datetime.today().year
        return f"{current_year} {date_string}", f"%Y {og_format}"
    return date_string, og_format


def _patch_dateparser() -> None:
    global DATEPARSER_PATCHED
    if DATEPARSER_PATCHED:
        return

    import dateparser.parser
    import dateparser.utils.strptime

    og_strptime = dateparser.utils.strptime.strptime

    def _strptime(date_string: str, format: str) -> datetime.datetime:
        return og_strptime(*_prepare_format(date_string, format))

    dateparser.utils.strptime.strptime = _strptime
    dateparser.parser.strptime = _strptime
    DATEPARSER_PATCHED = True


if __name__ == "__main__":
    print(parse_human_date("today at noon"))  # noqa: T201
    print(parse_human_date("today"))  # noqa: T201
