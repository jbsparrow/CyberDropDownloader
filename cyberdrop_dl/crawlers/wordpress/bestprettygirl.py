from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

from ._wordpress import WordPressBaseCrawler


class BestPrettyGirlCrawler(WordPressBaseCrawler):
    DOMAIN: ClassVar[str] = "bestprettygirl.com"
    FOLDER_DOMAIN: ClassVar[str] = "BestPrettyGirl"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://bestprettygirl.com/")
