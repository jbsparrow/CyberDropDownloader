import datetime
import warnings

import pytest

from cyberdrop_dl.utils import dates

midnight = datetime.time(hour=0, minute=0, second=0, microsecond=0)


def now() -> datetime.datetime:
    return datetime.datetime.now()


def today_at_midnight() -> datetime.datetime:
    return datetime.datetime.combine(now().date(), midnight)


def test_parse_today_at_midnight() -> None:
    expected = today_at_midnight()
    result = dates.parse_human_date("today at midnight")
    assert expected == result


def test_parse_date_with_no_year() -> None:
    def parse() -> None:
        expected = today_at_midnight().replace(month=10, day=14)
        result = dates.parse_human_date("oct 14")
        assert expected == result

    with warnings.catch_warnings(action="error"):
        with pytest.raises(DeprecationWarning):
            parse()

        dates._patch_dateparser()
        parse()
