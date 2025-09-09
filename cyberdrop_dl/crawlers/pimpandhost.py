from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

ALBUM_TITLE_SELECTOR = "span[class=author-header__album-name]"
DATE_SELECTOR = "span[class=date-time]"
FILES_SELECTOR = 'a[class*="image-wrapper center-cropped im-wr"]'
IMAGE_SELECTOR = ".main-image-wrapper"
DATE_FORMAT = "%A, %B %d, %Y %I:%M:%S%p %Z"

PRIMARY_URL = AbsoluteHttpURL("https://pimpandhost.com/")


class PimpAndHostCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"Album": "/album/...", "Image": "/image/..."}
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    NEXT_PAGE_SELECTOR: ClassVar[str] = "li[class=next] a"
    DOMAIN: ClassVar[str] = "pimpandhost"
    FOLDER_DOMAIN: ClassVar[str] = "PimpAndHost"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "album" in scrape_item.url.parts:
            return await self.album(scrape_item)
        await self.image(scrape_item)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        title: str = ""
        async for soup in self.web_pager(scrape_item.url):
            if not title:
                album_id = scrape_item.url.parts[2]
                title_portion = css.select_one(soup, ALBUM_TITLE_SELECTOR).text
                title = self.create_title(title_portion, album_id)
                scrape_item.setup_as_album(title, album_id=album_id)

                if date_tag := soup.select_one(DATE_SELECTOR):
                    scrape_item.possible_datetime = self.parse_date(css.get_attr(date_tag, "title"), DATE_FORMAT)

            for _, new_scrape_item in self.iter_children(scrape_item, soup, FILES_SELECTOR):
                self.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        soup = await self.request_soup(scrape_item.url)

        link_str: str = css.select_one_get_attr(soup, IMAGE_SELECTOR, "data-src")
        link = self.parse_url(link_str)
        date_str: str = css.select_one_get_attr(soup, DATE_SELECTOR, "title")
        scrape_item.possible_datetime = self.parse_date(date_str, DATE_FORMAT)
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)
