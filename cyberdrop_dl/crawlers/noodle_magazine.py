from __future__ import annotations

import calendar
import datetime
import itertools
import json
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup
from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext, get_text_between

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


PLAYLIST_SELECTOR = "script:contains('window.playlist')"
METADATA_SELECTOR = "script[type='application/ld+json']"
SEARCH_STRING_SELECTOR = "div.mh_line > h1.c_title"
VIDEOS_SELECTOR = "div#list_videos a.item_link"


class NoodleMagazineCrawler(Crawler):
    primary_base_domain = URL("https://noodlemagazine.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "noodlemagazine", "NoodleMagazine")
        self.request_limiter = AsyncLimiter(1, 3)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "video" in scrape_item.url.parts:
            return await self.search(scrape_item)
        elif "watch" in scrape_item.url.parts:
            return await self.video(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem) -> None:
        title: str = ""
        init_page = int(scrape_item.url.query.get("p") or 1)
        seen_urls: set[URL] = set()
        for page in itertools.count(1, init_page):
            n_videos = 0
            page_url = scrape_item.url.with_query(p=page)
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup_cffi(self.domain, page_url)

            if not title:
                search_string: str = soup.select_one(SEARCH_STRING_SELECTOR).text.strip()  # type: ignore
                title = search_string.rsplit(" videos", 1)[0]
                title = self.create_title(f"{title} [search]")
                scrape_item.setup_as_album(title)

            for _, new_scrape_item in self.iter_children(scrape_item, soup, VIDEOS_SELECTOR):
                if new_scrape_item.url not in seen_urls:
                    seen_urls.add(new_scrape_item.url)
                    n_videos += 1
                    self.manager.task_group.create_task(self.run(new_scrape_item))

            if n_videos < 24:
                break

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup_cffi(self.domain, scrape_item.url)
        metadata_script = soup.select_one(METADATA_SELECTOR)
        metadata = json.loads(metadata_script.text.strip())  # type: ignore
        playlist = soup.select_one(PLAYLIST_SELECTOR)
        if not playlist:
            raise ScrapeError(404)

        playlist_data = json.loads(get_text_between(playlist.text, "window.playlist = ", ";\nwindow.ads"))
        best_source = max(playlist_data["sources"], key=lambda s: int(s["label"]))
        video_id: str = URL(metadata["contentUrl"]).parts[-1].split(".")[0]
        file_name, ext = get_filename_and_ext(metadata["contentUrl"])
        scrape_item.possible_datetime = parse_datetime(metadata["uploadDate"])
        title: str = soup.select_one("title").text.split(" watch online")[0]  # type: ignore
        custom_filename, _ = get_filename_and_ext(
            f"{title} [{video_id}] [{best_source['label']}p].{best_source['type']}"
        )
        link = self.parse_url(best_source["file"])
        await self.handle_file(link, scrape_item, file_name, ext, custom_filename=custom_filename)


"""~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


def parse_datetime(date: str) -> int:
    """Parses a datetime string into a unix timestamp."""
    parsed_date = datetime.datetime.strptime(date, "%Y-%m-%d")
    return calendar.timegm(parsed_date.timetuple())
