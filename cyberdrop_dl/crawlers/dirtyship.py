from __future__ import annotations

import json
from typing import TYPE_CHECKING, NamedTuple

from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


VIDEO_SELECTOR = "video#fp-video-0 > source"
FLOWPLAYER_VIDEO_SELECTOR = "div.freedomplayer"
PLAYLIST_ITEM_SELECTOR = "li.thumi > a"
NEXT_PAGE_SELECTOR = "a.page-next"


class Format(NamedTuple):
    resolution: int | None
    url: URL


class DirtyShipCrawler(Crawler):
    primary_base_domain = URL("https://dirtyship.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "dirtyship", "DirtyShip")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if any(p in scrape_item.url.parts for p in ("tag", "category")):
            return await self.playlist(scrape_item)
        return await self.video(scrape_item)

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem) -> None:
        add_title = True
        async for soup in self.web_pager(scrape_item):
            if add_title:
                title: str = soup.select_one("title").text  # type: ignore
                title = title.split("Archives - DirtyShip")[0]
                title = self.create_title(title)
                scrape_item.setup_as_album(title)
                add_title = False

            for video in soup.select(PLAYLIST_ITEM_SELECTOR):
                link_str: str = video.get("href")  # type: ignore
                link = self.parse_url(link_str)
                new_scrape_item = scrape_item.create_child(link)
                self.manager.task_group.create_task(self.run(new_scrape_item))
                scrape_item.add_children()

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        title: str = soup.select_one("title").text  # type: ignore
        title = title.split(" - DirtyShip")[0]
        videos = soup.select(VIDEO_SELECTOR)
        formats: set[Format] = set()
        for video in videos:
            link_str: str = video.get("src")  # type: ignore
            if link_str.startswith("type="):
                continue
            res: str = video.get("title")  # type: ignore
            link = self.parse_url(link_str)  # type: ignore
            formats.add(Format(int(res), link))

        if not formats:
            formats = self.get_flowplayer_sources(soup)
        if not formats:
            raise ScrapeError(422, message="No video source found")

        res, link = sorted(formats)[-1]  # type: ignore
        res = f"{res}p" if res else "Unknown"

        filename, ext = self.get_filename_and_ext(link.name)
        custom_filename, _ = self.get_filename_and_ext(f"{title} [{res}]{link.suffix}")
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def web_pager(self, scrape_item: ScrapeItem) -> AsyncGenerator[BeautifulSoup]:
        """Generator of website pages."""
        page_url = scrape_item.url
        while True:
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, page_url, origin=scrape_item)
            next_page = soup.select_one(NEXT_PAGE_SELECTOR)
            yield soup
            page_url_str: str | None = next_page.get("href") if next_page else None  # type: ignore
            if not page_url_str:
                break
            page_url = self.parse_url(page_url_str)

    def get_flowplayer_sources(self, soup: BeautifulSoup) -> set[Format]:
        flow_player = soup.select_one(FLOWPLAYER_VIDEO_SELECTOR)
        data_item: str = flow_player.get("data-item") if flow_player else None  # type: ignore
        if not data_item:
            return set()
        data_item = data_item.replace(r"\/", "/")
        json_data = json.loads(data_item)
        sources = json_data["sources"]
        return {Format(None, self.parse_url(s["src"])) for s in sources}
