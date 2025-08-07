from __future__ import annotations

from typing import ClassVar

from aiolimiter import AsyncLimiter

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

from ._chevereto import CheveretoCrawler


class JPG5Crawler(CheveretoCrawler):
    SUPPORTED_DOMAINS = "selti-delivery.ru", "jpg6.su"
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
        url = super().transform_url(url)
        if cls.is_subdomain(url):
            # old jpg5 subdomains are still valid. ex: simp4.jpg5.su
            return url.with_host(url.host.replace("jpg6.su", "jpg5.su"))
        return url


def fix_db_referer(referer: str) -> str:
    url = AbsoluteHttpURL(referer)
    return str(JPG5Crawler.transform_url(url))
