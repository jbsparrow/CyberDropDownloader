from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.twitter_images import TwimgCrawler
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.crawlers.crawler import SupportedDomains
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class Selectors:
    NEXT = "li > a:-soup-contains('»')"
    VIDEO = "video.video-js > source"
    PHOTO = "img.thumb__img"
    TITLE = "h1.user-page"
    HASHTAGS = "h1.tag-page"
    BLOCK_TITLE = "h1.block__title"
    THUMBS = "div.block-thumbs a.thumb__link"


_SELECTORS = Selectors()

TITLE_TRASH = "'s pics and videos"


class TwPornstarsCrawler(TwimgCrawler):
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = (
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
    )
    PRIMARY_URL: ClassVar = AbsoluteHttpURL("https://www.twpornstars.com")
    NEXT_PAGE_SELECTOR: ClassVar = _SELECTORS.NEXT
    DOMAIN: ClassVar = "twpornstars"
    FOLDER_DOMAIN: ClassVar = "TWPornStars"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "p" in scrape_item.url.parts:
            return await self.media(scrape_item)
        if len(scrape_item.url.parts) >= 2:
            return await self.collection(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def media(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return
        soup = await self.request_soup(scrape_item.url)
        if url := soup.select_one(_SELECTORS.PHOTO):
            url = self.parse_url(css.get_attr(url, "src").replace(":large", ""))
            await self.photo(scrape_item, url)
        elif url := soup.select_one(_SELECTORS.VIDEO):
            url = self.parse_url(css.get_attr(url, "src")).with_query(None)
            await self.direct_file(scrape_item, url)
        else:
            raise ScrapeError(404)

    @error_handling_wrapper
    async def collection(self, scrape_item: ScrapeItem) -> None:
        title_created: bool = False
        async for soup in self.web_pager(scrape_item.url):
            if not title_created:
                title_tag = (
                    soup.select_one(_SELECTORS.TITLE)
                    or soup.select_one(_SELECTORS.HASHTAGS)
                    or soup.select_one(_SELECTORS.BLOCK_TITLE)
                )
                assert title_tag
                title = self.create_title(title_tag.get_text(strip=True).replace(TITLE_TRASH, ""))
                scrape_item.setup_as_album(title)
                title_created = True
            for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.THUMBS):
                self.create_task(self.run(new_scrape_item))
