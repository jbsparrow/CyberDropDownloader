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
    NEXT_PAGE = "a.next_page"
    IMAGE = "div.image_viewer img"
    VIDEO_THUMBS = "div.tile > a.thumb"


_SELECTORS = Selectors()


class EfuktCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": "/...",
        "Photo": "/pics/....",
        "Gif": "/view.gif.php?id=<id>",
        "Series": "/series/<series_name>",
        "Homepage": "/",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "efukt.com"
    FOLDER_DOMAIN: ClassVar[str] = "eFukt"
    NEXT_PAGE_SELECTOR = _SELECTORS.NEXT_PAGE
    SKIP_PRE_CHECK = True
    DEFAULT_POST_TITLE_FORMAT = "{date:%Y-%m-%d} {title}"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if is_series(scrape_item.url) or is_homepage(scrape_item.url):
            return await self.series(scrape_item)
        return await self.video_image_or_gif(scrape_item)

    @error_handling_wrapper
    async def series(self, scrape_item: ScrapeItem) -> None:
        title: str = ""
        homepage = is_homepage(scrape_item.url)
        async for soup in self.web_pager(scrape_item.url):
            if not homepage and not title:
                title = css.select_one_get_text(soup, _SELECTORS.TITLE)
                scrape_item.setup_as_album(self.create_title(f"{title} [series]"))

            for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.VIDEO_THUMBS):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def video_image_or_gif(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        date_str = css.select_one_get_text(soup, _SELECTORS.DATE).split(" ", 1)[-1]
        datetime = self._parse_date(date_str, "%m/%d/%y")
        if not datetime:
            raise ScrapeError(422)
        scrape_item.possible_datetime = to_timestamp(datetime)

        if is_image_or_gif(scrape_item.url):
            link = self.parse_url(css.select_one_get_attr(soup, _SELECTORS.IMAGE, "src"))
        else:
            link = self.parse_url(css.select_one_get_attr(soup, _SELECTORS.VIDEO, "src"))

        item_id = scrape_item.url.query.get("id") or scrape_item.url.name.partition("_")[0]
        title = Path(css.select_one_get_text(soup, _SELECTORS.TITLE)).as_posix().replace("/", "-")
        filename, ext = self.get_filename_and_ext(link.name)
        custom_filename = self.create_custom_filename(f"{datetime.date().isoformat()} {title}", ext, file_id=item_id)
        # Video links expire, but the path is always the same, only query params change
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename, debrid_link=link)


def is_homepage(url: AbsoluteHttpURL) -> bool:
    return (url == PRIMARY_URL) or (len(url.parts) == 2 and url.name.isdigit())


def is_series(url: AbsoluteHttpURL) -> bool:
    return "series" in url.parts and len(url.parts) > 2


def is_image_or_gif(url: AbsoluteHttpURL) -> bool:
    return "pics" in url.parts or url.name == "view.gif.php"
