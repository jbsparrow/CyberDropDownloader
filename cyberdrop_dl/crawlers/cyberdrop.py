from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

API_ENTRYPOINT = AbsoluteHttpURL("https://api.cyberdrop.me/api/")
PRIMARY_URL = AbsoluteHttpURL("https://cyberdrop.me/")


class Selectors:
    ALBUM_TITLE = "h1[id=title]"
    ALBUM_DATE = "p[class=title]"
    ALBUM_ITEM = "div[class*=image-container] a[class=image]"


_SELECTORS = Selectors()


class CyberdropCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Album": "/a/...",
        "File": "/f/...",
        "Direct links": "",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "cyberdrop"
    _RATE_LIMIT: ClassVar[tuple[float, float]] = 5, 1
    _DOWNLOAD_SLOTS: ClassVar[int | None] = 1

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "a" in scrape_item.url.parts:
            return await self.album(scrape_item)
        await self.file(scrape_item)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        scrape_item.url = scrape_item.url.with_query("nojs")
        album_id = scrape_item.url.parts[2]

        soup = await self.request_soup(scrape_item.url)

        try:
            title: str = css.select_one_get_text(soup, _SELECTORS.ALBUM_TITLE)
            title = self.create_title(title, album_id)
            scrape_item.setup_as_album(title, album_id=album_id)
        except AttributeError:
            msg = "Unable to parse album information from response content"
            raise ScrapeError(422, msg) from None

        if date_tags := soup.select(_SELECTORS.ALBUM_DATE):
            scrape_item.possible_datetime = self.parse_date(date_tags[-1].text, "%d.%m.%Y")

        for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.ALBUM_ITEM):
            self.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        scrape_item.url = await self._get_stream_link(scrape_item.url)
        if await self.check_complete_from_referer(scrape_item):
            return

        file_id = scrape_item.url.name
        file_info: tuple[dict[str, Any], dict[str, Any]] = await asyncio.gather(
            self.request_json(API_ENTRYPOINT / "file" / "info" / file_id),
            self.request_json(API_ENTRYPOINT / "file" / "auth" / file_id),
        )

        filename, ext = self.get_filename_and_ext(file_info[0]["name"])
        link = self.parse_url(file_info[1]["url"])
        await self.handle_file(link, scrape_item, filename, ext)

    async def _get_stream_link(self, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        """Gets the stream link for a given URL."""

        if any(part in url.parts for part in ("a", "f")):
            return url

        if url.host.count(".") > 1 or "e" in url.parts:
            return PRIMARY_URL / "f" / url.name

        async with self.request(url) as resp:
            return resp.url
