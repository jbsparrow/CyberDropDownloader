from __future__ import annotations

from typing import Final

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper

from ._chevereto import CheveretoCrawler

CDN: Final = "selti-delivery.ru"


class JPG5Crawler(CheveretoCrawler):
    SUPPORTED_DOMAINS = "selti-delivery.ru", "jpg7.cr", "jpg6.su"
    DOMAIN = "jpg5.su"
    FOLDER_DOMAIN = "JPG5"
    PRIMARY_URL = AbsoluteHttpURL("https://jpg6.su")
    CHEVERETO_SUPPORTS_VIDEO = False
    OLD_DOMAINS = (
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

    _RATE_LIMIT = 2, 1

    @classmethod
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        url = super().transform_url(url)
        if cls.is_subdomain(url):
            # old jpg5 subdomains are still valid. ex: simp4.jpg5.su
            return url.with_host(url.host.replace("jpg6.su", "jpg5.su"))
        return url

    @error_handling_wrapper
    async def direct_file(
        self, scrape_item: ScrapeItem, url: AbsoluteHttpURL | None = None, assume_ext: str | None = None
    ) -> None:
        link = url or scrape_item.url

        if self.is_subdomain(link) and not link.host.endswith(CDN):
            server, *_ = link.host.rsplit(".", 2)
            link = link.with_host(f"{server}.{CDN}")

        await super().direct_file(scrape_item, link, assume_ext)


def fix_db_referer(referer: str) -> str:
    url = AbsoluteHttpURL(referer)
    return str(JPG5Crawler.transform_url(url))
