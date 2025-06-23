from __future__ import annotations

import pytest

from cyberdrop_dl.crawlers import _forum, vbulletin
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL


@pytest.mark.parametrize(
    ("url", "thread_name_and_id", "result", "canonical_url"),
    [
        [
            "https://vipergirls.to/threads/2783401-Jodie-Comer/page4",
            "2783401-Jodie-Comer",
            (
                2783401,
                "Jodie-Comer",
                4,
                None,
            ),
            "https://vipergirls.to/threads/2783401-Jodie-Comer",
        ],
        [
            "https://vipergirls.to/threads/9046167-Lacey-Evans/page11?p=222377716&viewfull=1#post222377716",
            "9046167-Lacey-Evans",
            (
                9046167,
                "Lacey-Evans",
                11,
                222377716,
            ),
            "https://vipergirls.to/threads/9046167-Lacey-Evans",
        ],
    ],
)
def test_parse_thread(url: str, thread_name_and_id: str, result: tuple[int, str, int, int], canonical_url: str) -> None:
    url_, canonical_url_ = AbsoluteHttpURL(url), AbsoluteHttpURL(canonical_url)
    result_ = _forum.Thread(*result, canonical_url_)
    parsed = vbulletin.vBulletinCrawler.parse_thread(url_, thread_name_and_id)
    assert result_ == parsed
