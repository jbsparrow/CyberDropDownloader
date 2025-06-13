from __future__ import annotations

from typing import ClassVar

from aiolimiter import AsyncLimiter

from cyberdrop_dl.crawlers.vbulletin._vbulletin import vBulletinCrawler
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL


class ViperGirlsCrawler(vBulletinCrawler):
    LOGIN_REQUIRED = False
    LOGIN_COOKIE = "vg_password"

    PRIMARY_URL = AbsoluteHttpURL("https://vipergirls.to/forum.php")
    DOMAIN = "vipergirls.to"
    SUPPORTED_DOMAINS: ClassVar = "viper.click", "vipergirls.to"
    API_ENDPOINT: ClassVar = AbsoluteHttpURL("https://viper.click/vr.php")

    def __post_init__(self) -> None:
        super().__post_init__()
        self.request_limiter = AsyncLimiter(4, 1)
