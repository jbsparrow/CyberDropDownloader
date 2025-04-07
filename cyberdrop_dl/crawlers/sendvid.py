from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


class SendVidCrawler(Crawler):
    primary_base_domain = URL("https://sendvid.com/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "sendvid", "SendVid")
        self.video_src_selector = "video > source#video_source"
        self.title_selector = "p.video-title"
        self.required_query_parameters = "validfrom", "validto", "rate", "ip", "hash"

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

        title = soup.select_one(self.title_selector).get_text()
        try:
            link_str: str = soup.select_one(self.video_src_selector).get("src")
            link = self.parse_url(link_str)
        except AttributeError:
            raise ScrapeError(422, "Couldn't find video source") from None
        await self.handle_direct_link(scrape_item, link, title)

    async def handle_direct_link(
        self, scrape_item: ScrapeItem, link: URL | None = None, title: str | None = None
    ) -> None:
        link = link or scrape_item.url
        canonical_url = link.with_query(None)

        if not all(q in link.query for q in self.required_query_parameters):
            msg = f"URL is missing some of the required parameters: {self.required_query_parameters}"
            raise ScrapeError(401, msg)

        filename, ext = self.get_filename_and_ext(link.name)
        custom_filename = None
        if title:
            custom_filename, _ = self.get_filename_and_ext(f"{title}{ext}")
        await self.handle_file(
            canonical_url, scrape_item, filename, ext, debrid_link=link, custom_filename=custom_filename
        )

    def is_cdn(self, url: URL) -> bool:
        return all(p in url.host for p in (self.primary_base_domain.host, "."))

    def get_streaming_url(self, url: URL) -> URL:
        if self.is_cdn(url):
            video_id = url.name.split(".", 1)[0]
            return self.primary_base_domain.with_path(video_id)

        if "embed" in url.parts:
            new_parts = (p for p in url.parts if p not in ("/", "embed"))
            new_path = "/".join(new_parts)
            return url.with_path(new_path)
        return url
