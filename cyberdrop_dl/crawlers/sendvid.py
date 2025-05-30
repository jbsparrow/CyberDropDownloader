from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper, remove_parts

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager


VIDEO_SRC_SELECTOR = "video > source#video_source"
TITLE_SELECTOR = "p.video-title"
REQUIRED_QUERY_PARAMS = "validfrom", "validto", "rate", "ip", "hash"
MAIN_HOST = "sendvid.com"


class SendVidCrawler(Crawler):
    primary_base_domain = URL("https://sendvid.com/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "sendvid", "SendVid")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        scrape_item.url = self.get_streaming_url(scrape_item.url)
        await self.video(scrape_item)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a video page."""
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        title = soup.select_one(TITLE_SELECTOR).get_text()  # type: ignore
        try:
            link_str: str = soup.select_one(VIDEO_SRC_SELECTOR).get("src")  # type: ignore
            link = self.parse_url(link_str)
        except AttributeError:
            raise ScrapeError(422, "Couldn't find video source") from None
        await self.handle_direct_link(scrape_item, link, title)

    async def handle_direct_link(self, scrape_item: ScrapeItem, link: URL | None = None, title: str = "") -> None:
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

    def get_streaming_url(self, url: URL) -> URL:
        if is_cdn(url):
            video_id = url.name.split(".", 1)[0]
            return self.primary_base_domain.with_path(video_id)

        if "embed" in url.parts:
            return remove_parts(url, "embed")
        return url


def is_cdn(url: URL) -> bool:
    return bool(url.host and all(p in url.host for p in (MAIN_HOST, ".")))
