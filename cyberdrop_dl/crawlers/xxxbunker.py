from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css, open_graph
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class Selector:
    VIDEOS = ".videolist a[data-anim]"
    VIDEO_IFRAME = "div.player-frame iframe"
    NEXT_PAGE = "div.page-list a:-soup-contains('Next')"


class XXXBunkerCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": "/<video_id>",
        "Search": "/search/<video_id>",
        "Category": "/categories/<category>",
        "User Favorites": "/<username>/favoritevideos",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://xxxbunker.com")
    DOMAIN: ClassVar[str] = "xxxbunker"
    FOLDER_DOMAIN: ClassVar[str] = "XXXBunker"
    NEXT_PAGE_SELECTOR = Selector.NEXT_PAGE
    _DOWNLOAD_SLOTS: ClassVar[int | None] = 2
    _RATE_LIMIT = 1, 6

    async def async_startup(self) -> None:
        self.update_cookies({"ageconfirm": "True"})

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["search" | "categories" as type_, name]:
                return await self.playlist(scrape_item, name, type_)
            case [username, "favoritevideos" as type_]:
                return await self.playlist(scrape_item, f"user {username}", type_)
            case [_]:
                await self.video(scrape_item)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        soup = await self.request_soup(scrape_item.url)
        _check_video_is_available(soup)
        title = open_graph.title(soup)
        iframe_url = self.parse_url(css.select_one_get_attr(soup, Selector.VIDEO_IFRAME, "data-src"))
        iframe_soup = await self.request_soup(iframe_url)
        src = self.parse_url(css.select_one_get_attr(iframe_soup, "source", "src"))
        video_id = iframe_url.name
        custom_filename = self.create_custom_filename(title, ".mp4", file_id=video_id)
        await self.handle_file(
            iframe_url, scrape_item, f"{video_id}.mp4", custom_filename=custom_filename, debrid_link=src
        )

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem, name: str, type_: str) -> None:
        title: str = ""
        async for soup in self.web_pager(scrape_item.url):
            if not title:
                name = name.replace("+", " ")
                category = {"search": "search", "categories": "category", "favoritevideos": "favorites"}[type_]
                title = self.create_title(f"{name} [{category}]")
                scrape_item.setup_as_album(title)

            for _, new_scrape_item in self.iter_children(scrape_item, soup, Selector.VIDEOS):
                self.create_task(self.run(new_scrape_item))


def _check_video_is_available(soup: BeautifulSoup):
    soup_text = soup.text
    if "TRAFFIC VERIFICATION" in soup_text:
        raise ScrapeError(429)

    if "VIDEO NOT AVAILABLE" in soup_text:
        raise ScrapeError(404)
