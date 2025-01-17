import re
from datetime import timedelta

DATE_PATTERN = re.compile(
    r"(\d+)\s*(second|seconds|minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)", re.IGNORECASE
)


def parse_duration_to_timedelta(input_date: timedelta | str | int) -> timedelta:
    """Parses `datetime.timedelta`, `str` or `int` into a timedelta format.

    for `str`, the expected format is `value unit`, ex: `5 days`, `10 minutes`, `1 year`

    valid units:
        year(s), week(s), day(s), hour(s), minute(s), second(s), millisecond(s), microsecond(s)

    for `int`, value is assumed as `days`
    """
    if not input_date:
        return 0
    parsed_timedelta = input_date
    if isinstance(input_date, int):
        parsed_timedelta = timedelta(days=input_date)
    if isinstance(input_date, str):
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
                raise ValueError(f"Duplicate time unit detected: '{unit}' conflicts with another entry.")
            seen_units.add(normalized_unit)

            if "day" in unit:
                time_dict["days"] += value
            elif "month" in unit:
                time_dict["days"] += value * 30
            elif "year" in unit:
                time_dict["days"] += value * 365
            else:
                time_dict[plural_unit] = value

        if matches:
            parsed_timedelta = timedelta(**time_dict)

    return parsed_timedelta
