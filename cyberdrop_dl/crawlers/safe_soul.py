from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers._chibisafe import Album, ChibiSafeCrawler, File
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    import bs4

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class Selector:
    ALBUM_TITLE = "#title"
    FILE = "#table .image-container"
    FILE_DATE = ".details .file-date"
    FILE_NAME = ".details .name"
    FILE_URL = "a.image"


class SafeSoulCrawler(ChibiSafeCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://safe.soul.lol")
    DOMAIN: ClassVar[str] = "safe.soul.lol"
    FOLDER_DOMAIN: ClassVar[str] = "Safe.Soul"

    async def file(self, scrape_item: ScrapeItem, file_id: str) -> None:
        # file endpoint is disabled
        return await self.direct_file(scrape_item)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem, album_id: str) -> None:
        # The album endpoint is enabled, but it returns incomplete info (ex: missing date)
        # So we scrape the HTML

        soup = await self.request_soup(scrape_item.url)
        album = Album(
            id=album_id,
            name=css.select_one_get_text(soup, Selector.ALBUM_TITLE),
            files=[_parse_file(tag) for tag in soup.select(Selector.FILE)],
        )
        return await self._handle_album(scrape_item, album)


def _parse_file(file_tag: bs4.Tag) -> File:
    timestamp = int(css.select_one_get_attr(file_tag, Selector.FILE_DATE, "data-value"))

    return File(
        name=css.select_one_get_text(file_tag, Selector.FILE_NAME),
        url=css.select_one_get_attr(file_tag, Selector.FILE_URL, "href"),
        createdAt=datetime.datetime.fromtimestamp(timestamp),
    )
