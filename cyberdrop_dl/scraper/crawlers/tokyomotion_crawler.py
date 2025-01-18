from __future__ import annotations

import re
from calendar import timegm
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from multidict import MultiDict
from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem

DATE_PATTERN = re.compile(r"(\d+)\s*(weeks?|days?|hours?|minutes?|seconds?)", re.IGNORECASE)


class TokioMotionCrawler(Crawler):
    primary_base_domain = URL("https://www.tokyomotion.net")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "tokyomotion", "Tokyomotion")

        self.album_selector = 'a[href^="/album/"]'
        self.image_div_selector = "div[id*='_photo_']"
        self.image_selector = 'a[href^="/photo/"]'
        self.image_thumb_selector = "img[id^='album_photo_']"
        self.next_page_attribute = "href"
        self.next_page_selector = "a.prevnext"
        self.title_selector = "meta[property='og:title']"
        self.video_div_selector = "div[id*='video_']"
        self.video_selector = 'a[href^="/video/"]'
        self.search_div_selector = "div[class^='well']"

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        new_query = MultiDict(scrape_item.url.query)
        new_query.pop("page", None)
        scrape_item.url = self.primary_base_domain.with_path(scrape_item.url.path).with_query(new_query)

        if "video" in scrape_item.url.parts:
            await self.video(scrape_item)

        elif "videos" in scrape_item.url.parts:
            await self.playlist(scrape_item)

        elif "photo" in scrape_item.url.parts:
            await self.image(scrape_item)

        elif any(part in scrape_item.url.parts for part in ("album", "photos")):
            await self.album(scrape_item)

        elif "albums" in scrape_item.url.parts:
            await self.albums(scrape_item)

        elif "user" in scrape_item.url.parts:
            await self.profile(scrape_item)

        else:
            await self.search(scrape_item)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a video."""
        if await self.check_complete_from_referer(scrape_item):
            return

        video_id = scrape_item.url.parts[2]
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        try:
            relative_date_str = soup.select_one("div.pull-right.big-views-xs.visible-xs > span.text-white").text.strip()
            date = await self.parse_relative_date(relative_date_str)
            scrape_item.possible_datetime = date
        except AttributeError:
            pass

        try:
            srcSD = soup.select_one('source[title="SD"]')
            srcHD = soup.select_one('source[title="HD"]')
            link_str: str = (srcHD or srcSD).get("src")
            link = self.parse_url(link_str)
        except AttributeError:
            if "This is a private" in soup.text:
                raise ScrapeError(401, "Private video", origin=scrape_item) from None
            raise ScrapeError(422, "Couldn't find video source", origin=scrape_item) from None

        title = soup.select_one("title").text.rsplit(" - TOKYO Motion")[0].strip()

        # NOTE: hardcoding the extension to prevent quering the final server URL
        # final server URL is always diferent so it can not be saved to db.
        filename, ext = f"{video_id}.mp4", ".mp4"
        custom_filename, _ = get_filename_and_ext(f"{title} [{video_id}]{ext}")
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    @error_handling_wrapper
    async def albums(self, scrape_item: ScrapeItem) -> None:
        """Scrapes user albums."""
        user = scrape_item.url.parts[2]
        user_title = self.create_title(f"{user} [user]", scrape_item.album_id)
        if user_title not in scrape_item.parent_title.split("/"):
            scrape_item.add_to_parent_title(user_title)

        async for soup in self.web_pager(scrape_item):
            albums = soup.select(self.album_selector)
            for album in albums:
                link_str: str = album.get("href")
                if not link_str:
                    continue
                link = self.parse_url(link_str)
                new_scrape_item = self.create_scrape_item(scrape_item, link, "albums", add_parent=scrape_item.url)
                await self.album(new_scrape_item)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        title = scrape_item.url.parts[-1]
        if "user" in scrape_item.url.parts:
            user = scrape_item.url.parts[2]
            user_title = self.create_title(f"{user} [user]", scrape_item.album_id)
            if user_title not in scrape_item.parent_title.split("/"):
                scrape_item.add_to_parent_title(user_title)

        else:
            scrape_item.album_id = scrape_item.url.parts[2]
            scrape_item.part_of_album = True

        if self.folder_domain not in scrape_item.parent_title:
            title = self.create_title(title, scrape_item.album_id)

        if "favorite" in scrape_item.url.parts:
            scrape_item.add_to_parent_title("favorite")

        if title not in scrape_item.parent_title.split("/"):
            scrape_item.add_to_parent_title(title)

        async for soup in self.web_pager(scrape_item):
            if "This is a private" in soup.text:
                raise ScrapeError(401, "Private album", origin=scrape_item)
            images = soup.select(self.image_div_selector)
            for image in images:
                link_tag = image.select_one(self.image_thumb_selector)
                if not link_tag:
                    continue
                link_str: str = link_tag.select("href")
                link = self.parse_url(link_str)
                link = link.with_path(link.path.replace("/tmb/", "/"))

                filename, ext = get_filename_and_ext(link.name)
                await self.handle_file(link, scrape_item, filename, ext)

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        if await self.check_complete_from_referer(scrape_item):
            return
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)
        try:
            img = soup.select_one("img[class='img-responsive-mw']")
            link_str: str = img.get("src")
            link = self.parse_url(link_str)
        except AttributeError:
            if "This is a private" in soup.text:
                raise ScrapeError(401, "Private Photo", origin=scrape_item) from None
            raise ScrapeError(422, "Couldn't find image source", origin=scrape_item) from None

        filename, ext = get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an user profile."""
        user = scrape_item.url.parts[2]
        user_title = self.create_title(f"{user} [user]", scrape_item.album_id)
        if user_title not in scrape_item.parent_title.split("/"):
            scrape_item.add_to_parent_title(user_title)

        new_parts = ["albums", "favorite/photos", "videos", "favorite/videos"]
        scrapers = [self.albums, self.album, self.playlist, self.playlist]
        for part, scraper in zip(new_parts, scrapers, strict=False):
            link = scrape_item.url / part
            new_scrape_item = self.create_scrape_item(scrape_item, link, add_parent=scrape_item.url)
            await scraper(new_scrape_item)

    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a search result."""
        search_type = scrape_item.url.query.get("search_type")
        if "search" not in scrape_item.url.parts or search_type == "users":
            return

        search_query = scrape_item.url.query.get("search_query")
        search_title = self.create_title(f"{search_query} [{search_type} search]", scrape_item.album_id)
        if search_title not in scrape_item.parent_title.split("/"):
            scrape_item.add_to_parent_title(search_title)

        selector = self.video_selector
        scraper = self.video

        if search_type == "photos":
            selector = self.album_selector
            scraper = self.album

        async for soup in self.web_pager(scrape_item):
            results = soup.select(self.search_div_selector)
            for result in results:
                link_tag = result.select_one(selector)
                if not link_tag:
                    continue
                link_str: str = link_tag.get("href")
                link = self.parse_url(link_str)
                new_scrape_item = self.create_scrape_item(scrape_item, link, add_parent=scrape_item.url)
                await scraper(new_scrape_item)

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a video playlist."""
        title = scrape_item.url.parts[-1]
        user = scrape_item.url.parts[2]
        user_title = self.create_title(f"{user} [user]", scrape_item.album_id)
        if user_title not in scrape_item.parent_title.split("/"):
            scrape_item.add_to_parent_title(user_title)

        if "favorite" in scrape_item.url.parts:
            scrape_item.add_to_parent_title("favorite")

        if self.folder_domain not in scrape_item.parent_title:
            title = self.create_title(title, scrape_item.album_id)

        if title not in scrape_item.parent_title.split("/"):
            scrape_item.add_to_parent_title(title)

        async for soup in self.web_pager(scrape_item):
            if "This is a private" in soup.text:
                raise ScrapeError(401, "Private playlist", origin=scrape_item)
            videos = soup.select(self.video_div_selector)
            for video in videos:
                link_tag = video.select_one(self.video_selector)
                if not link_tag:
                    continue
                link_str: str = link_tag.get("href")
                link = self.parse_url(link_str)
                new_scrape_item = self.create_scrape_item(scrape_item, link, "", add_parent=scrape_item.url)
                await self.video(new_scrape_item)

    async def web_pager(self, scrape_item: ScrapeItem) -> AsyncGenerator[BeautifulSoup]:
        """Generator of website pages."""
        page_url = scrape_item.url
        while True:
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, page_url, origin=scrape_item)
            next_page = soup.select_one(self.next_page_selector)
            yield soup
            if not next_page:
                break
            page_url_str: str = next_page.get(self.next_page_attribute)
            page_url = self.parse_url(page_url_str)

    @staticmethod
    async def parse_relative_date(relative_date: timedelta | str) -> int:
        """Parses `datetime.timedelta` or `string` in a timedelta format. Returns `now() - parsed_timedelta` as an unix timestamp."""
        if isinstance(relative_date, str):
            time_str = relative_date.casefold()
            matches: list[str] = re.findall(DATE_PATTERN, time_str)
            time_dict = {"days": 0}  # Assume today

            for value, unit in matches:
                value = int(value)
                unit = unit.lower()
                time_dict[unit] = value

            relative_date = timedelta(**time_dict)

        date = datetime.now() - relative_date
        return timegm(date.timetuple())
