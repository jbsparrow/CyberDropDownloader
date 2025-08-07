from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from aiolimiter import AsyncLimiter

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css, open_graph
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

PRIMARY_URL = AbsoluteHttpURL("https://xxxbunker.com")
VIDEOS_SELECTOR = "a[data-anim='4']"
VIDEO_IFRAME_SELECTOR = "div.player-frame iframe"
NEXT_PAGE_SELECTOR = "div.page-list a:contains('next')"


class XXXBunkerCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": "/<video_id>",
        "Search": "/search/...",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "xxxbunker"
    FOLDER_DOMAIN: ClassVar[str] = "XXXBunker"
    NEXT_PAGE_SELECTOR = NEXT_PAGE_SELECTOR

    def __post_init__(self) -> None:
        self.rate_limit = self.wait_time = 10
        self.request_limiter = AsyncLimiter(self.rate_limit, 60)
        self.session_cookie = None

    async def async_startup(self) -> None:
        self.update_cookies({"ageconfirm": "True"})

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["search", "categories", "favoritevideos", _]:
                return await self.playlist(scrape_item)
            case [_]:
                await self.video(scrape_item)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        _check_video_is_available(soup)
        title = open_graph.title(soup)
        iframe_url = self.parse_url(css.select_one_get_attr(soup, VIDEO_IFRAME_SELECTOR, "data-src"))

        async with self.request_limiter:
            iframe_soup = await self.client.get_soup(self.DOMAIN, iframe_url)

        src = self.parse_url(css.select_one_get_attr(iframe_soup, "source", "src"))
        video_id = iframe_url.name
        custom_filename = self.create_custom_filename(title, ".mp4", file_id=video_id)
        await self.handle_file(
            iframe_url, scrape_item, f"{video_id}.mp4", custom_filename=custom_filename, debrid_link=src
        )

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem) -> None:
        name = scrape_item.url.parts[2]
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        if "favoritevideos" in scrape_item.url.parts:
            title = self.create_title(f"user {name} [favorites]")
        elif "search" in scrape_item.url.parts:
            title = self.create_title(f"{name.replace('+', ' ')} [search]")
        elif len(scrape_item.url.parts) >= 2:
            title = self.create_title(f"{name} [category]")
        else:
            # Not a valid URL
            raise ScrapeError(400, "Unsupported URL format")

        scrape_item.setup_as_album(title)

        async for soup in self.web_pager(scrape_item.url):
            for _, new_scrape_item in self.iter_children(scrape_item, soup, VIDEOS_SELECTOR):
                self.create_task(self.run(new_scrape_item))


def _check_video_is_available(soup: BeautifulSoup):
    soup_text = soup.text
    if "TRAFFIC VERIFICATION" in soup_text:
        raise ScrapeError(429)

    if "VIDEO NOT AVAILABLE" in soup_text:
        raise ScrapeError(404)
