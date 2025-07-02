from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper, remove_parts

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

PRIMARY_URL = AbsoluteHttpURL("https://sendvid.com/")
VIDEO_SRC_SELECTOR = "video > source#video_source"
TITLE_SELECTOR = "p.video-title"
REQUIRED_QUERY_PARAMS = "validfrom", "validto", "rate", "ip", "hash"


class SendVidCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Videos": "/...",
        "Embeds": "/embed/...",
        "Direct links": "",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "sendvid"
    FOLDER_DOMAIN: ClassVar[str] = "SendVid"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        scrape_item.url = self.get_streaming_url(scrape_item.url)
        await self.video(scrape_item)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        title = css.select_one_get_text(soup, TITLE_SELECTOR)
        try:
            link_str: str = css.select_one_get_attr(soup, VIDEO_SRC_SELECTOR, "src")
        except AssertionError:
            raise ScrapeError(422, "Couldn't find video source") from None
        link = self.parse_url(link_str)
        await self.handle_direct_link(scrape_item, link, title)

    async def handle_direct_link(
        self, scrape_item: ScrapeItem, link: AbsoluteHttpURL | None = None, title: str = ""
    ) -> None:
        link = link or scrape_item.url
        canonical_url = link.with_query(None)

        if not all(param in link.query for param in REQUIRED_QUERY_PARAMS):
            msg = f"URL is missing some of the required parameters: {REQUIRED_QUERY_PARAMS}"
            raise ScrapeError(401, msg)

        filename, ext = self.get_filename_and_ext(link.name)
        custom_filename = self.get_filename_and_ext(f"{title}{ext}")[0] if title else None
        await self.handle_file(
            canonical_url, scrape_item, filename, ext, debrid_link=link, custom_filename=custom_filename
        )

    def get_streaming_url(self, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        if is_cdn(url):
            video_id = url.name.split(".", 1)[0]
            return PRIMARY_URL.with_path(video_id)

        if "embed" in url.parts:
            return remove_parts(url, "embed")
        return url


def is_cdn(url: AbsoluteHttpURL) -> bool:
    return all(p in url.host for p in (PRIMARY_URL.host, "."))
