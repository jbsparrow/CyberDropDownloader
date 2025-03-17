from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


VIDEO_SELECTOR = "div.video_player video"


class VidplyCrawler(Crawler):
    SUPPORTED_SITES: ClassVar[dict[str, list]] = {
        "vidply.com": ["vidply.com", "dood.re", "doodstream", "doodcdn", "doodstream.co"]
    }
    primary_base_domain = URL("https://vidply.com/")

    def __init__(self, manager: Manager, _=None) -> None:
        super().__init__(manager, "vidply.com", "vidply")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        scrape_item.url = scrape_item.url.with_host("vidply.com")
        await self.video(scrape_item)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        title: str = soup.select_one("title").text  # type: ignore
        title = title.split("- DoodStream")[0].strip()

        video = soup.select_one(VIDEO_SELECTOR)
        link_str: str = video.get("src")  # type: ignore
        link = self.parse_url(link_str)
        filename, ext = get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)
