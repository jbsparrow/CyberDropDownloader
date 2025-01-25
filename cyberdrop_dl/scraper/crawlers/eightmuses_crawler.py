from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


class EightMusesCrawler(Crawler):
    primary_base_domain = URL("https://comics.8muses.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "8muses", "8Muses")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "album" in scrape_item.url.parts:
            index = len(scrape_item.url.parts[3:6]) - 1
            func = (self.album, self.sub_album, self.comic)[index]
            await func(scrape_item)
        else:
            log(f"Scrape Failed: Unknown URL path: {scrape_item.url}", 40)
            return

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        album_title, sub_album_title, comic_title = await self.get_titles(soup)
        scrape_item.album_id = album_title.replace(" ", "-")
        scrape_item.add_to_parent_title(album_title)

        sub_albums = soup.select("a[class*=c-tile]")
        for sub_album in sub_albums:
            href = sub_album.get("href")
            if href:
                sub_album_link = self.parse_url(href)
            else:
                continue
            sub_album_title = sub_album.get("title", "")
            new_scrape_item = self.create_scrape_item(
                scrape_item,
                sub_album_link,
                sub_album_title,
                True,
                f'{scrape_item.album_id}/{sub_album_title.replace(" ", "-")}',
                add_parent=scrape_item.url,
            )
            await self.sub_album(new_scrape_item)

    @error_handling_wrapper
    async def sub_album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a sub-album."""
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
        scrape_item.part_of_album = True
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        album_title, sub_album_title, comic_title = await self.get_titles(soup)
        if not scrape_item.parents:
            scrape_item.add_to_parent_title(sub_album_title)
            scrape_item.album_id = album_title.replace(" ", "-") + "/" + sub_album_title.replace(" ", "-")

        comics = soup.select("a[class*=c-tile]")
        for comic in comics:
            href = comic.get("href")
            if href:
                comic_link = self.parse_url(href)
            else:
                continue
            comic_title = comic.get("title", "")
            new_scrape_item = self.create_scrape_item(
                scrape_item,
                comic_link,
                comic_title,
                True,
                f'{scrape_item.album_id}/{comic_title.replace(" ", "-")}',
                add_parent=scrape_item.url,
            )
            await self.comic(new_scrape_item)

    @error_handling_wrapper
    async def comic(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a comic."""
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
        scrape_item.part_of_album = True
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        album_title, sub_album_title, comic_title = await self.get_titles(soup)
        if not scrape_item.parents:
            scrape_item.add_to_parent_title(comic_title)
            scrape_item.album_id = (
                album_title.replace(" ", "-")
                + "/"
                + sub_album_title.replace(" ", "-")
                + "/"
                + comic_title.replace(" ", "-")
            )

        images = soup.select("a[class*=c-tile]")
        for image in images:
            image_title = image.get("title", "")
            filename, ext = get_filename_and_ext(f"{image_title}.jpg")
            image_link = self.parse_url(
                image.select_one("div[class=image] > img").get("data-src").replace("/th/", "/fm/")
            )
            await self.handle_file(image_link, scrape_item, filename, ext)
            scrape_item.add_children()

    async def get_titles(self, soup: BeautifulSoup) -> tuple[str, str, str]:
        """Gets the album title, sub-album title, and comic title."""
        titles = soup.select("div[class=top-menu-breadcrumb] > ol > li > a")[1:]

        album_title = titles[0].text if len(titles) > 0 else ""
        sub_album_title = titles[1].text if len(titles) > 1 else ""
        comic_title = titles[2].text if len(titles) > 2 else ""

        return album_title, sub_album_title, comic_title
