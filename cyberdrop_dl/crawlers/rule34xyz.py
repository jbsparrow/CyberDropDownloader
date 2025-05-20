from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.crawlers.rule34vault import Rule34VaultCrawler
from cyberdrop_dl.types import AbsoluteHttpURL, OneOrTupleStrMapping


class Rule34XYZCrawler(Rule34VaultCrawler):
    SUPPORTED_PATHS: ClassVar[OneOrTupleStrMapping] = {
        "File page": "/post/...",
        "Tag": "/...",
    }
    primary_base_domain = AbsoluteHttpURL("https://rule34.xyz")
    DOMAIN = "rule34.xyz"
    FOLDER_DOMAIN = "Rule34XYZ"
