from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.crawlers.rule34vault import Rule34VaultCrawler
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

PRIMARY_URL = AbsoluteHttpURL("https://rule34.xyz")


class Rule34XYZCrawler(Rule34VaultCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "rule34.xyz"
    FOLDER_DOMAIN: ClassVar[str] = "Rule34XYZ"
