from __future__ import annotations

import itertools
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


class Selectors:
    CONTENT = "div[class='box-grid ng-star-inserted'] a[class='box ng-star-inserted']"
    TITLE = "div[class*=title]"
    DATE = 'div[class="posted-date-full text-secondary mt-4 ng-star-inserted"]'
    VIDEO = 'div[class="con-video ng-star-inserted"] > video > source'
    IMAGE = 'img[class*="img ng-star-inserted"]'


_SELECTORS = Selectors()


class Rule34VaultCrawler(Crawler):
    primary_base_domain = URL("https://rule34vault.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "rule34vault", "Rule34Vault")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "post" in scrape_item.url.parts:
            return await self.file(scrape_item)
        if "playlists/view" in scrape_item.url.path:
            return await self.playlist(scrape_item)
        await self.tag(scrape_item)

    @error_handling_wrapper
    async def tag(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""

        init_page = int(scrape_item.url.query.get("page") or 1)
        title: str = ""
        for page in itertools.count(init_page):
            n_images = 0
            url = scrape_item.url.with_query(page=page)
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, url)

            if not title:
                title = self.create_title(scrape_item.url.parts[1])
                scrape_item.setup_as_album(title)

            for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.CONTENT):
                n_images += 1
                self.manager.task_group.create_task(self.run(new_scrape_item))

            if n_images < 30:
                break

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a playlist."""

        album_id = scrape_item.url.parts[-1]
        init_page = int(scrape_item.url.query.get("page") or 1)
        title: str = ""
        for page in itertools.count(init_page):
            url = scrape_item.url.with_query(page=page)
            n_images = 0
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, url)

            if not title:
                title_str: str = soup.select_one(_SELECTORS.TITLE).text  # type: ignore
                title = self.create_title(title_str, album_id)
                scrape_item.setup_as_album(title, album_id=album_id)

            for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.CONTENT):
                n_images += 1
                self.manager.task_group.create_task(self.run(new_scrape_item))

            if n_images < 30:
                break

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        if date_tag := soup.select_one(_SELECTORS.DATE):
            scrape_item.possible_datetime = self.parse_date(date_tag.text, "%b %d, %Y, %I:%M:%S %p")

        media_tag = soup.select_one(_SELECTORS.VIDEO) or soup.select_one(_SELECTORS.IMAGE)
        link_str: str = media_tag["src"]  # type: ignore
        for trash in (".small", ".thumbnail", ".720", ".hevc"):
            link_str = link_str.replace(trash, "")

        link = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""
