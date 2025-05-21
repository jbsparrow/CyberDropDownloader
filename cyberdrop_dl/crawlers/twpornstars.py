from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager


class Selectors:
    NEXT = "li > a:contains('»')"
    VIDEO = "video.video-js > source"
    PHOTO = "img.thumb__img"
    TITLE = "h1.user-page"
    HASHTAGS = "h1.tag-page"
    THUMBS = "div.block-thumbs a.thumb__link"


_SELECTORS = Selectors()

SUPPORTED_DOMAINS = [
    "www.twgays.com",
    "www.twmilf.com",
    "www.twlesbian.com",
    "www.twteens.com",
    "www.twonfans.com",
    "www.twtiktoks.com",
    "www.twgaymuscle.com",
    "www.twanal.com",
    "www.indiantw.com",
    "www.twpornstars.com",
]

TITLE_TRASH = "'s pics and videos"


class TwPornstarsCrawler(Crawler):
    SUPPORTED_SITES: ClassVar[dict[str, list]] = {"twpornstars": SUPPORTED_DOMAINS}
    primary_base_domain = URL("https://www.twpornstars.com")
    next_page_selector = _SELECTORS.NEXT

    def __init__(self, manager: Manager, _=None) -> None:
        super().__init__(manager, "twpornstars", "TWPornStars")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "p" in scrape_item.url.parts:
            return await self.media(scrape_item)
        if len(scrape_item.url.parts) >= 2:
            return await self.collection(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def media(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        if url := soup.select_one(_SELECTORS.PHOTO):
            new_scrape_item = scrape_item.create_new(URL(url.get("src").replace("///", "//").replace(":large", "")))
            self.handle_external_links(new_scrape_item)
            scrape_item.add_children()
        else:
            url = soup.select_one(_SELECTORS.VIDEO)
            if not url:
                raise ValueError(404)
            url = URL(url.get("src")).with_query(None)
            filename, ext = self.get_filename_and_ext(url.name)
            await self.handle_file(scrape_item.url, scrape_item, filename, ext, debrid_link=url)

    @error_handling_wrapper
    async def collection(self, scrape_item: ScrapeItem) -> None:
        title_created: bool = False
        async for soup in self.web_pager(scrape_item.url):
            if not title_created:
                title_tag = soup.select_one(_SELECTORS.TITLE) or soup.select_one(_SELECTORS.HASHTAGS)
                title: str = title_tag.get_text(strip=True)
                title = title.replace(TITLE_TRASH, "")
                title = self.create_title(title)
                scrape_item.setup_as_album(title)
                title_created = True
            for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.THUMBS):
                self.manager.task_group.create_task(self.run(new_scrape_item))
