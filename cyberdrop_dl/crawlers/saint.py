from __future__ import annotations

import base64
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class Selectors:
    VIDEOS = "a.btn-primary.action.download"
    EMBED_SRC = "video[id=main-video] source"
    DOWNLOAD_BUTTON = "a:contains('Download Video')"
    NOT_FOUND_IMAGE = "video#video-container img"


PRIMARY_URL = AbsoluteHttpURL("https://saint2.su/")
NOT_FOUND_GIF = "https://saint2.su/assets/notfound.gif"
_SELECTORS = Selectors()


class SaintCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Album": "/a/...",
        "Video": (
            "/embed/...",
            "/d/...",
        ),
        "Direct links": "",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "saint"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        scrape_item.url = PRIMARY_URL.with_path(scrape_item.url.path)
        if "a" in scrape_item.url.parts:
            return await self.album(scrape_item)
        if "embed" in scrape_item.url.parts:
            return await self.embed(scrape_item)
        await self.video(scrape_item)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        album_id = scrape_item.url.parts[2]
        results = await self.get_album_results(album_id)
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        title_portion = css.select_one_get_text(soup, "title").rsplit(" - Saint Video Hosting")[0].strip()
        if not title_portion:
            title_portion = scrape_item.url.name
        title = self.create_title(title_portion, album_id)
        scrape_item.setup_as_album(title, album_id=album_id)

        for video in soup.select(_SELECTORS.VIDEOS):
            on_click_text: str = css.get_attr(video, "onclick")
            link_str = get_text_between(on_click_text, "('", "');")
            link = self.parse_url(link_str)
            if not self.check_album_results(link, results):
                new_scrape_item = scrape_item.create_child(link)
                self.manager.task_group.create_task(self.run(new_scrape_item))
            scrape_item.add_children()

    @error_handling_wrapper
    async def embed(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)
        try:
            link_str: str = css.select_one_get_attr(soup, _SELECTORS.EMBED_SRC, "src")
        except AssertionError:
            if is_not_found(soup):
                raise ScrapeError(404) from None
            raise ScrapeError(422, "Couldn't find video source") from None
        link = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)
        try:
            link_str: str = css.select_one_get_attr(soup, _SELECTORS.DOWNLOAD_BUTTON, "href")
        except (AttributeError, css.SelectorError):
            if is_not_found(soup):
                raise ScrapeError(404) from None
            raise ScrapeError(422, "Couldn't find video source") from None
        link = get_url_from_base64(self.parse_url(link_str))
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)


def is_not_found(soup: BeautifulSoup) -> bool:
    if (title := soup.select_one("title")) and title.text == "Video not found":
        return True
    if (image := soup.select_one(_SELECTORS.NOT_FOUND_IMAGE)) and image.get("src") == NOT_FOUND_GIF:
        return True
    if "File not found in the database" in soup.get_text():
        return True
    return False


def get_url_from_base64(link: AbsoluteHttpURL) -> AbsoluteHttpURL:
    base64_str: str | None = link.query.get("file")
    if not base64_str:
        return link
    filename_decoded = base64.b64decode(base64_str).decode("utf-8")
    return AbsoluteHttpURL(f"https://{link.host}/videos/{filename_decoded}")
