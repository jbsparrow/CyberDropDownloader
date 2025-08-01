from __future__ import annotations

import re
from typing import ClassVar

from aiolimiter import AsyncLimiter

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

from ._chevereto import CheveretoCrawler


class JPG5Crawler(CheveretoCrawler):
    DOMAIN: ClassVar[str] = "jpg5.su"
    FOLDER_DOMAIN: ClassVar[str] = "JPG5"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://jpg6.su")
    CHEVERETO_SUPPORTS_VIDEO: ClassVar[bool] = False
    OLD_DOMAINS: ClassVar[tuple[str, ...]] = (
        "host.church",
        "jpg.homes",
        "jpg.church",
        "jpg.fish",
        "jpg.fishing",
        "jpg.pet",
        "jpeg.pet",
        "jpg1.su",
        "jpg2.su",
        "jpg3.su",
        "jpg4.su",
        "jpg5.su",
    )

    def __post_init__(self) -> None:
        self.request_limiter = AsyncLimiter(1, 1)

    @classmethod
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        assert cls.REPLACE_OLD_DOMAINS_REGEX is not None
        new_host = re.sub(cls.REPLACE_OLD_DOMAINS_REGEX, "jpg5.su", url.host)
        if new_host.removeprefix("www.") == "jpg5.su":
            # replace only if it is matches the second level domain exactly
            # old jpg5 subdomains are still valid. ex: simp4.jpg5.su
            return url.with_host(cls.PRIMARY_URL.host)
        return url.with_host(new_host)


def fix_db_referer(referer: str) -> str:
    url = AbsoluteHttpURL(referer)
    return str(JPG5Crawler.transform_url(url))
