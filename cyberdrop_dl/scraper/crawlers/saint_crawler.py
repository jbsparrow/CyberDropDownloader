from __future__ import annotations

import base64
import re
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from re import Match

    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


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
            await self.album(scrape_item)
        elif "embed" in scrape_item.url.parts:
            await self.embed(scrape_item)
        else:
            await self.video(scrape_item)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        album_id = scrape_item.url.parts[2]
        results = await self.get_album_results(album_id)
        scrape_item.album_id = album_id
        scrape_item.part_of_album = True
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        title_portion = soup.select_one("title").text.rsplit(" - Saint Video Hosting")[0].strip()
        if not title_portion:
            title_portion = scrape_item.url.name
        title = self.create_title(title_portion, album_id)
        scrape_item.add_to_parent_title(title)

        videos = soup.select("a.btn-primary.action.download")

        for video in videos:
            match: Match = re.search(r"\('(.+?)'\)", video.get("onclick"))
            link_str = match.group(1) if match else None
            if not link_str:
                continue
            link = self.parse_url(link_str)
            filename, ext = get_filename_and_ext(link.name)
            if not self.check_album_results(link, results):
                await self.handle_file(link, scrape_item, filename, ext)
            scrape_item.add_children()

    @error_handling_wrapper
    async def embed(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an embeded video page."""
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)
        try:
            link_str: str = soup.select_one("video[id=main-video] source").get("src")
            link = self.parse_url(link_str)
        except AttributeError:
            if is_not_found(soup):
                raise ScrapeError(404, origin=scrape_item) from None
            raise ScrapeError(422, "Couldn't find video source", origin=scrape_item) from None
        filename, ext = get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a video page."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)
        try:
            link_str: str = soup.select_one("a:contains('Download Video')").get("href")
            link = self.parse_url(link_str)
            link = get_url_from_base64(link)
        except AttributeError:
            if is_not_found(soup):
                raise ScrapeError(404, origin=scrape_item) from None
            raise ScrapeError(422, "Couldn't find video source", origin=scrape_item) from None
        filename, ext = get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)


def is_not_found(soup: BeautifulSoup) -> bool:
    title = soup.title
    if title and title.text == "Video not found":
        return True
    image = soup.select_one("video#video-container img")
    if image and image.get("src") == "https://saint2.su/assets/notfound.gif":
        return True
    return False


def get_url_from_base64(link: URL) -> URL:
    base64_str: str = link.query.get("file")
    if not base64_str:
        return link
    filename_decoded = base64.b64decode(base64_str).decode("utf-8")
    return URL("https://some_cdn.saint2.cr/videos").with_host(link.host) / filename_decoded
