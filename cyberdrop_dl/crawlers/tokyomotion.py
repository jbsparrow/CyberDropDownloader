from __future__ import annotations

import re
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper, remove_parts

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

DATE_PATTERN = re.compile(r"(\d+)\s*(weeks?|days?|hours?|minutes?|seconds?)", re.IGNORECASE)
PRIMARY_URL = AbsoluteHttpURL("https://www.tokyomotion.net")


class TokioMotionCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Albums": ("/user/<user>/albums/", "/album/<album_id>"),
        "Photo": ("/photo/<photo_id>", "/user/<user>/favorite/photos"),
        "Playlist": "/user/<user>/favorite/videos",
        "Profiles": "/user/<user>",
        "Search Results": "/search?...",
        "Video": "/video/<video_id>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    NEXT_PAGE_SELECTOR: ClassVar[str] = "a.prevnext"
    DOMAIN: ClassVar[str] = "tokyomotion"

    def __post_init__(self) -> None:
        self.album_selector = 'a[href^="/album/"]'
        self.image_link_selector = 'a[href^="/photo/"]'
        self.image_selector = "img[class='img-responsive-mw']"
        self.image_thumb_selector = "div[id*='_photo_'] img[id^='album_photo_']"
        self.title_selector = "meta[property='og:title']"
        self.video_div_selector = "div[id*='video_']"
        self.video_selector = 'a[href^="/video/"]'
        self.search_div_selector = "div[class^='well']"
        self.video_date_selector = "div.pull-right.big-views-xs.visible-xs > span.text-white"
        self.album_title_selector = "div.panel.panel-default > div.panel-heading > div.pull-left"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        scrape_item.url = scrape_item.url.without_query_params("page")

        if "video" in scrape_item.url.parts:
            return await self.video(scrape_item)
        if "videos" in scrape_item.url.parts:
            return await self.playlist(scrape_item)
        if "photo" in scrape_item.url.parts:
            return await self.image(scrape_item)
        if any(part in scrape_item.url.parts for part in ("album", "photos")):
            return await self.album(scrape_item)
        if "albums" in scrape_item.url.parts:
            return await self.albums(scrape_item)
        if "user" in scrape_item.url.parts:
            return await self.profile(scrape_item)
        if "search" in scrape_item.url.parts and scrape_item.url.query.get("search_type") != "users":
            return await self.search(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        canonical_url = scrape_item.url.with_path("/".join(scrape_item.url.parts[1:3]))
        scrape_item.url = canonical_url
        if await self.check_complete_from_referer(canonical_url):
            return

        video_id = scrape_item.url.parts[2]
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        scrape_item.possible_datetime = self.parse_date(css.select_one_get_text(soup, self.video_date_selector))

        src = soup.select_one('source[title="SD"]') or soup.select_one('source[title="HD"]')
        if not src:
            if "This is a private" in soup.text:
                raise ScrapeError(401, "Private video")
            raise ScrapeError(422, "Couldn't find video source")

        link_str: str = css.get_attr(src, "src")
        link = self.parse_url(link_str)
        title = css.select_one_get_text(soup, "title").rsplit(" - TOKYO Motion")[0].strip()
        filename, ext = f"{video_id}.mp4", ".mp4"
        custom_filename = self.create_custom_filename(title, ext, file_id=video_id)
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        img = soup.select_one(self.image_selector)
        if not img:
            if "This is a private" in soup.text:
                raise ScrapeError(401, "Private Photo")
            raise ScrapeError(422, "Couldn't find image source")

        link_str: str = css.get_attr(img, "src")
        link = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        title = await self.get_album_title(scrape_item)
        if "user" in scrape_item.url.parts:
            self.add_user_title(scrape_item)

        else:
            canonical_url = scrape_item.url.with_path("/".join(scrape_item.url.parts[1:3]))
            scrape_item.url = canonical_url
            album_id = scrape_item.url.parts[2]
            scrape_item.album_id = album_id
            title = self.create_title(title, album_id)

        scrape_item.part_of_album = True

        if title not in scrape_item.parent_title:
            scrape_item.add_to_parent_title(title)
        if title == "favorite":
            scrape_item.add_to_parent_title("photos")

        async for soup in self.web_pager(scrape_item.url):
            if "This is a private" in soup.text:
                raise ScrapeError(401, "Private album")
            for _, link in self.iter_tags(soup, self.image_thumb_selector, "src"):
                link = remove_parts(link, "tmb")
                filename, ext = self.get_filename_and_ext(link.name)
                await self.handle_file(link, scrape_item, filename, ext)

    """------------------------------------------------------------------------------------------------------------------------"""

    @error_handling_wrapper
    async def albums(self, scrape_item: ScrapeItem) -> None:
        self.add_user_title(scrape_item)
        async for soup in self.web_pager(scrape_item.url):
            for _, new_scrape_item in self.iter_children(
                scrape_item, soup, self.album_selector, new_title_part="albums"
            ):
                await self.album(new_scrape_item)

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        self.add_user_title(scrape_item)
        new_parts = ["albums", "favorite/photos", "videos", "favorite/videos"]
        scrapers = [self.albums, self.album, self.playlist, self.playlist]
        for part, scraper in zip(new_parts, scrapers, strict=False):
            link = scrape_item.url / part
            new_scrape_item = scrape_item.create_child(link)
            await scraper(new_scrape_item)

    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem) -> None:
        search_type = scrape_item.url.query.get("search_type")
        search_query = scrape_item.url.query.get("search_query")
        search_title = f"{search_query} [{search_type} search]"
        is_album = search_type == "photos"
        if not scrape_item.parent_title:
            search_title = self.create_title(search_title)

        scrape_item.setup_as_album(search_title)
        selector = f"{self.search_div_selector} "
        selector += self.album_selector if is_album else self.video_selector
        scraper = self.album if is_album else self.video

        async for soup in self.web_pager(scrape_item.url):
            for _, new_scrape_item in self.iter_children(scrape_item, soup, selector):
                await scraper(new_scrape_item)

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem) -> None:
        self.add_user_title(scrape_item)
        if "favorite" in scrape_item.url.parts:
            scrape_item.add_to_parent_title("favorite")

        scrape_item.setup_as_album("videos")
        selector = f"{self.video_div_selector} {self.video_selector}"

        async for soup in self.web_pager(scrape_item.url):
            if "This is a private" in soup.text:
                raise ScrapeError(401, "Private playlist")
            for _, new_scrape_item in self.iter_children(scrape_item, soup, selector):
                await self.video(new_scrape_item)

    """--------------------------------------------------------------------------------------------------------------------------"""

    async def get_album_title(self, scrape_item: ScrapeItem) -> str:
        if "favorite" in scrape_item.url.parts:
            return "favorite"
        if "album" in scrape_item.url.parts and len(scrape_item.url.parts) > 3:
            return scrape_item.url.parts[3]
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)
        return css.select_one_get_text(soup, self.album_title_selector)

    def add_user_title(self, scrape_item: ScrapeItem) -> None:
        try:
            user_index = scrape_item.url.parts.index("user")
            user = scrape_item.url.parts[user_index + 1]
        except ValueError:
            return
        user_title = f"{user} [user]"
        full_user_title = self.create_title(user_title)
        if not scrape_item.parent_title:
            scrape_item.add_to_parent_title(full_user_title)
        if user_title not in scrape_item.parent_title:
            scrape_item.add_to_parent_title(user_title)
