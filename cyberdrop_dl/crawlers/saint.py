from __future__ import annotations

import base64
import re
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager


VIDEOS_SELECTOR = "a.btn-primary.action.download"
EMBED_SRC_SELECTOR = "video[id=main-video] source"
DOWNLOAD_BUTTON_SELECTOR = "a:contains('Download Video')"
NOT_FOUND_IMAGE_SELECTOR = "video#video-container img"
URL_REGEX = re.compile(r"\('(.+?)'\)")


class SaintCrawler(Crawler):
    primary_base_domain = URL("https://saint2.su/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "saint", "Saint")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        scrape_item.url = self.primary_base_domain.with_path(scrape_item.url.path)

        if "a" in scrape_item.url.parts:
            return await self.album(scrape_item)
        if "embed" in scrape_item.url.parts:
            return await self.embed(scrape_item)
        await self.video(scrape_item)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        album_id = scrape_item.url.parts[2]
        results = await self.get_album_results(album_id)
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        title_portion = soup.select_one("title").text.rsplit(" - Saint Video Hosting")[0].strip()  # type: ignore
        if not title_portion:
            title_portion = scrape_item.url.name
        title = self.create_title(title_portion, album_id)
        scrape_item.setup_as_album(title, album_id=album_id)

        for video in soup.select(VIDEOS_SELECTOR):
            on_click_text: str = video.get("onclick")  # type: ignore
            if match := re.search(URL_REGEX, on_click_text):
                link_str = match.group(1)
            else:
                continue

            link = self.parse_url(link_str)
            filename, ext = self.get_filename_and_ext(link.name)
            if not self.check_album_results(link, results):
                await self.handle_file(link, scrape_item, filename, ext)
            scrape_item.add_children()

    @error_handling_wrapper
    async def embed(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an embeded video page."""
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)
        try:
            link_str: str = soup.select_one(EMBED_SRC_SELECTOR).get("src")  # type: ignore
            link = self.parse_url(link_str)
        except AttributeError:
            if is_not_found(soup):
                raise ScrapeError(404) from None
            raise ScrapeError(422, "Couldn't find video source") from None
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a video page."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)
        try:
            link_str: str = soup.select_one(DOWNLOAD_BUTTON_SELECTOR).get("href")  # type: ignore
            link = get_url_from_base64(self.parse_url(link_str))
        except AttributeError:
            if is_not_found(soup):
                raise ScrapeError(404) from None
            raise ScrapeError(422, "Couldn't find video source") from None
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)


def is_not_found(soup: BeautifulSoup) -> bool:
    title = soup.title
    if title and title.text == "Video not found":
        return True

    if (image := soup.select_one(NOT_FOUND_IMAGE_SELECTOR)) and image.get(
        "src"
    ) == "https://saint2.su/assets/notfound.gif":
        return True
    if "File not found in the database" in str(soup):
        return True
    return False


def get_url_from_base64(link: URL) -> URL:
    base64_str: str | None = link.query.get("file")
    if not base64_str:
        return link
    assert link.host
    filename_decoded = base64.b64decode(base64_str).decode("utf-8")
    return URL(f"https://{link.host}/videos/{filename_decoded}")
