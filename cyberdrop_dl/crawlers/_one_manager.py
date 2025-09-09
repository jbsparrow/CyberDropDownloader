"""An index and manager of Onedrive based on serverless.

Gitlab: https://git.hit.edu.cn/ysun/OneManager-php
Github: https://github.com/qkqpttgf/OneManager-php
Gitee: https://gitee.com/qkqpttgf/OneManager-php
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler
from cyberdrop_dl.exceptions import InvalidContentTypeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import Tag

    from cyberdrop_dl.crawlers.crawler import SupportedPaths
    from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, ScrapeItem


class Selectors:
    TABLE = "table#list-table"
    FILE_LINK = "a.download"
    FOLDER_LINK = "a[name='folderlist']"
    FILE = f"tr:has({FILE_LINK})"
    FOLDER = f"tr:has({FOLDER_LINK})"
    DATE = "td.updated_at"
    README = "div#head.markdown-body"


_SELECTORS = Selectors()


class OneManagerCrawler(Crawler, is_abc=True):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"Any path": "/..."}
    SKIP_PRE_CHECK = True

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        scrape_item.url = scrape_item.url.with_query(None)
        if self.PRIMARY_URL not in scrape_item.parent_threads:
            self.init_item(scrape_item)
        await self.process_path(scrape_item)

    async def async_startup(self) -> None:
        self.manager.client_manager.download_slots.update({self.DOMAIN: 2})

    @error_handling_wrapper
    async def process_path(self, scrape_item: ScrapeItem) -> None:
        try:
            soup = await self.request_soup(scrape_item.url)
        except InvalidContentTypeError:  # This is a file, not html
            scrape_item.parent_title = scrape_item.parent_title.rsplit("/", 1)[0]
            link = scrape_item.url
            scrape_item.url = link.parent
            return await self._process_file(scrape_item, link)

        # TODO: save readme as a sidecard
        if soup.select_one(_SELECTORS.README):
            pass

        # href are not actual links, they only have the name of the new part
        table = css.select_one(soup, _SELECTORS.TABLE)
        for file in css.iselect(table, _SELECTORS.FILE):
            await self.process_file(scrape_item, file)
            scrape_item.add_children()

        for folder in css.iselect(table, _SELECTORS.FOLDER):
            link = scrape_item.url / css.select_one_get_attr(folder, _SELECTORS.FOLDER_LINK, "href")
            new_scrape_item = scrape_item.create_child(link, new_title_part=link.name)
            self.create_task(self.run(new_scrape_item))
            scrape_item.add_children()

    @error_handling_wrapper
    async def process_file(self, scrape_item: ScrapeItem, file: Tag) -> None:
        datetime = self.parse_date(css.select_one_get_text(file, _SELECTORS.DATE))
        link = scrape_item.url / css.select_one_get_attr(file, _SELECTORS.FILE_LINK, "href")
        await self._process_file(scrape_item, link, datetime)

    async def _process_file(self, scrape_item: ScrapeItem, link: AbsoluteHttpURL, datetime: int | None = None) -> None:
        preview_url = link.with_query("preview")  # The query param needs to be `?preview` exactly, with no value or `=`
        new_scrape_item = scrape_item.create_child(preview_url, possible_datetime=datetime)
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, new_scrape_item, filename, ext)

    def init_item(self, scrape_item: ScrapeItem) -> None:
        scrape_item.setup_as_album(self.FOLDER_DOMAIN, album_id=self.DOMAIN)
        for part in scrape_item.url.parts[1:]:
            scrape_item.add_to_parent_title(part)

        # smugle url as as sentinel
        scrape_item.parent_threads.add(self.PRIMARY_URL)
