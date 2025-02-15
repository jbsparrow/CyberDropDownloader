from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


PRIMARY_BASE_DOMAIN = URL("https://pixhost.to/")


class PixHostCrawler(Crawler):
    primary_base_domain = PRIMARY_BASE_DOMAIN
    update_unsupported = True

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "pixhost", "PixHost")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if is_cdn(scrape_item.url):
            link = scrape_item.url
            scrape_item.url = get_canonical_url(link)
            await self.handle_direct_link(scrape_item, link)
        elif "gallery" in scrape_item.url.parts:
            await self.gallery(scrape_item)
        elif "show" in scrape_item.url.parts:
            await self.image(scrape_item)
        else:
            raise ValueError

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a gallery."""
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        album_id = scrape_item.url.name
        title = soup.select_one("a[class=link] h2").text  # type: ignore
        title = self.create_title(title, album_id)
        scrape_item.add_to_parent_title(title)
        scrape_item.part_of_album = True
        scrape_item.album_id = album_id
        results = await self.get_album_results(album_id)

        images = soup.select("div[class=images] a")
        for image in images:
            link_str: str = image.get("href")  # type: ignore
            thumb_link_str: str = image.select_one("img").get("src")  # type: ignore
            if not (thumb_link_str and link_str):
                continue
            link = self.parse_url(link_str)
            link = get_canonical_url(link)
            thumb_link = self.parse_url(thumb_link_str)
            src = thumbnail_to_img(thumb_link)
            if not self.check_album_results(src, results):
                new_scrape_item = self.create_scrape_item(scrape_item, link, add_parent=scrape_item.url)
                await self.handle_direct_link(new_scrape_item, src)
            scrape_item.add_children()

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""

        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        link_str: str = soup.select_one("img[class=image-img]").get("src")  # type: ignore
        link = self.parse_url(link_str)
        await self.handle_direct_link(scrape_item, link)

    @error_handling_wrapper
    async def handle_direct_link(self, scrape_item: ScrapeItem, url: URL | None = None) -> None:
        link = url or scrape_item.url
        if is_thumbnail(link):
            link = thumbnail_to_img(link)
        filename, ext = get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)


def thumbnail_to_img(url: URL) -> URL:
    assert url.host
    thumb_server_id: str = url.host.split(".", 1)[0].split("t")[-1]
    img_host = f"img{thumb_server_id}.{PRIMARY_BASE_DOMAIN.host}"
    img_url = replace_first_part(url, "images")
    return img_url.with_host(img_host)


def replace_first_part(url: URL, new_part: str) -> URL:
    new_parts = list(url.parts)[1:]
    new_parts[0] = new_part
    new_path = "/".join(new_parts)
    return url.with_path(new_path)


def is_thumbnail(url: URL) -> bool:
    assert url.host
    return "thumbs" in url.parts and is_cdn(url)


def is_cdn(url: URL) -> bool:
    assert url.host
    return len(url.host.split(".")) > 2


def get_canonical_url(url: URL) -> URL:
    show_url = replace_first_part(url, "show")
    return show_url.with_host(PRIMARY_BASE_DOMAIN.host)  # type: ignore
