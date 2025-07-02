from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

from ._wordpress import WordPressMediaCrawler


class BestPrettyGirlCrawler(WordPressMediaCrawler):
    DOMAIN: ClassVar[str] = "bestprettygirl.com"
    FOLDER_DOMAIN: ClassVar[str] = "BestPrettyGirl"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://bestprettygirl.com/")
