from __future__ import annotations

from cyberdrop_dl.types import AbsoluteHttpURL

from ._yetishare import YetiShareCrawler


class CyberfileCrawler(YetiShareCrawler):
    primary_base_domain = AbsoluteHttpURL("https://cyberfile.me/")
    DOMAIN = "cyberfile"
