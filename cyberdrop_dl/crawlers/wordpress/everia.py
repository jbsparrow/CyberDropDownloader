from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

from ._wordpress import WordPressHTMLCrawler


class EveriaClubCrawler(WordPressHTMLCrawler):
    DOMAIN: ClassVar[str] = "everia.club"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://everia.club/")
    FOLDER_DOMAIN: ClassVar[str] = "EveriaClub"
    WP_USE_REGEX: ClassVar[bool] = False
