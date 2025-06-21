from __future__ import annotations

from typing import ClassVar

from aiolimiter import AsyncLimiter

from cyberdrop_dl.crawlers.vbulletin._vbulletin import vBulletinCrawler
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL


class ViperGirlsCrawler(vBulletinCrawler):
    login_required = False
    VBULLETIN_LOGIN_COOKIE_NAME = "vg_password"
    PRIMARY_URL = AbsoluteHttpURL("https://vipergirls.to")
    DOMAIN = "vipergirls.to"
    FOLDER_DOMAIN = "ViperGirls"
    SUPPORTED_DOMAINS: ClassVar = "viper.click", "vipergirls.to"
    VBULLETIN_API_ENDPOINT: ClassVar = AbsoluteHttpURL("https://viper.click/vr.php")

    def __post_init__(self) -> None:
        super().__post_init__()
        self.request_limiter = AsyncLimiter(4, 1)
