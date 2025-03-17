from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


VIDEO_PROPERTY = "og:video"
RESOLUTION_PROPERTY = "og:video:height"


class PMVHavenCrawler(Crawler):
    primary_base_domain = URL("https://pmvhaven.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "pmvhaven", "PMVHaven")

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        return await self.video(scrape_item)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        title: str = soup.select_one("title").text.split("|")[1].strip()
        res: str = soup.find("meta", property=RESOLUTION_PROPERTY)["content"]
        video_src = soup.find("meta", property=VIDEO_PROPERTY)["content"]
        if not video_src:
            raise ScrapeError(422, message="No video source found")
        link = self.parse_url(video_src)  # type: ignore

        res = f"{res}p" if res else "Unknown"

        filename, ext = get_filename_and_ext(link.name)
        custom_filename, _ = get_filename_and_ext(f"{title} [{res}]{link.suffix}")
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)
