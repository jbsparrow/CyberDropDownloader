from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.dates import to_timestamp
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

PRIMARY_URL = AbsoluteHttpURL("https://efukt.com")


class Selectors:
    DATE = "div.videobox span.stat:contains('Uploaded')"
    TITLE = "div.videobox > div.heading > h1"
    VIDEO = "div.videoplayer source"


_SELECTORS = Selectors()


class EfuktCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"Video": "/..."}
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "efukt.com"
    FOLDER_DOMAIN: ClassVar[str] = "eFukt"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        return await self.video(scrape_item)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        video_id, *_ = scrape_item.url.name.partition("_")
        title = css.select_one_get_text(soup, _SELECTORS.TITLE)
        date_str = css.select_one_get_text(soup, _SELECTORS.DATE).split(" ", 1)[-1]
        datetime = self._parse_date(date_str, "%m/%d/%y")
        if not datetime:
            raise ScrapeError(422)
        scrape_item.possible_datetime = to_timestamp(datetime)
        link = self.parse_url(css.select_one_get_attr(soup, _SELECTORS.VIDEO, "src"))
        title = Path(title).as_posix().replace("/", "-")
        filename, ext = self.get_filename_and_ext(f"{datetime.date().isoformat()} {title} [{video_id}].mp4")
        await self.handle_file(link, scrape_item, filename, ext, debrid_link=link)
