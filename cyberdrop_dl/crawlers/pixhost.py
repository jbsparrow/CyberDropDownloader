from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


PRIMARY_BASE_DOMAIN = URL("https://pixhost.to/")
GALLERY_TITLE_SELECTOR = "a[class=link] h2"
IMAGES_SELECTOR = "div[class=images] a"
IMAGE_SELECTOR = "img[class=image-img]"


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
            return await self.handle_direct_link(scrape_item, link)
        if "gallery" in scrape_item.url.parts:
            return await self.gallery(scrape_item)
        if "show" in scrape_item.url.parts:
            return await self.image(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a gallery."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        album_id = scrape_item.url.name
        title = soup.select_one(GALLERY_TITLE_SELECTOR).text  # type: ignore
        title = self.create_title(title, album_id)
        scrape_item.setup_as_album(title, album_id=album_id)
        results = await self.get_album_results(album_id)

        for thumb, link in self.iter_tags(soup, IMAGES_SELECTOR):
            if not thumb:
                continue
            link = get_canonical_url(link)
            src = thumbnail_to_img(thumb)
            if not self.check_album_results(src, results):
                new_scrape_item = scrape_item.create_child(link)
                await self.handle_direct_link(new_scrape_item, src)
            scrape_item.add_children()

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        link_str: str = soup.select_one(IMAGE_SELECTOR).get("src")  # type: ignore
        link = self.parse_url(link_str)
        await self.handle_direct_link(scrape_item, link)

    @error_handling_wrapper
    async def handle_direct_link(self, scrape_item: ScrapeItem, url: URL | None = None) -> None:
        link = url or scrape_item.url
        if is_thumbnail(link):
            link = thumbnail_to_img(link)
        await self.direct_file(scrape_item, link)


def thumbnail_to_img(url: URL) -> URL:
    assert url.host
    thumb_server_id: str = url.host.split(".", 1)[0].split("t")[-1]
    img_host = f"img{thumb_server_id}.{PRIMARY_BASE_DOMAIN.host}"
    img_url = replace_first_part(url, "images")
    return img_url.with_host(img_host)


def replace_first_part(url: URL, new_part: str) -> URL:
    new_parts = new_part, *url.parts[1:]
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
