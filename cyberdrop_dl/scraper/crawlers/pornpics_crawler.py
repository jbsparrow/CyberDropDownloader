from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, FILE_HOST_PROFILE, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


class PornPicsCrawler(Crawler):
    primary_base_domain = URL("https://pornpics.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "pornpics", "PornPics")
        self.image_selector = "div#main a.rel-link"

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if self.is_cdn(scrape_item.url):
            await self.image(scrape_item)
        elif scrape_item.url.query.get("q"):
            await self.collection(scrape_item, "search")
        elif len(scrape_item.url.parts) < 3:
            raise ValueError

        if "galleries" in scrape_item.url.parts:
            await self.gallery(scrape_item)
        elif "channels" in scrape_item.url.parts:
            await self.collection(scrape_item, "channel")
        elif "pornstars" in scrape_item.url.parts:
            await self.collection(scrape_item, "pornstar")
        elif "tags" in scrape_item.url.parts:
            await self.collection(scrape_item, "tag")
        else:
            await self.collection(scrape_item, "category")

    @error_handling_wrapper
    async def collection(self, scrape_item: ScrapeItem, type: str) -> None:
        """Scrapes a collection."""
        assert type in ("search", "channel", "pornstar", "tag", "category")
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        selector = "h2" if type == "channel" else "h1"
        title = soup.select_one(selector).text.removesuffix(" Nude Pics").removesuffix(" Porn Pics")
        title = self.create_title(f"{title} [{type}]")
        scrape_item.add_to_parent_title(title)
        self.process_subgalleries(scrape_item, soup)

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a gallery."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)
        gallery_id = scrape_item.url.name.rsplit("-", 1)[-1]
        canonical_url = self.primary_base_domain / "galleries" / gallery_id
        scrape_item.url = canonical_url
        title = soup.select_one("h1").text
        title = self.create_title(title, gallery_id)
        scrape_item.add_to_parent_title(title)
        scrape_item.part_of_album = True
        scrape_item.album_id = gallery_id
        results = await self.get_album_results(gallery_id)
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)

        images = soup.select(self.image_selector)
        for image in images:
            link_str: str = image.get("href")
            link = self.parse_url(link_str)
            if not self.check_album_results(link, results):
                filename, ext = get_filename_and_ext(link.name)
                new_scrape_item = self.create_scrape_item(scrape_item, link, add_parent=scrape_item.url)
                await self.handle_file(link, new_scrape_item, filename, ext)
            scrape_item.add_children()

    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        link = scrape_item.url
        gallery_id = link.parts[-2]
        filename, ext = get_filename_and_ext(link.name)
        new_scrape_item = self.create_scrape_item(scrape_item, link, album_id=gallery_id, add_parent=scrape_item.url)
        await self.handle_file(link, new_scrape_item, filename, ext)

    def process_subgalleries(self, scrape_item: ScrapeItem, soup: BeautifulSoup) -> None:
        """Queue galleries in colletions"""
        scrape_item.part_of_album = True
        scrape_item.set_type(FILE_HOST_PROFILE, self.manager)
        galleries = soup.select("div#main a.rel-link")
        for gallery in galleries:
            link_str: str = gallery.get("href")
            link = self.parse_url(link_str)
            new_scrape_item = self.create_scrape_item(scrape_item, link, add_parent=scrape_item.url)
            self.manager.task_group.create_task(self.run(new_scrape_item))
            scrape_item.add_children()

    def is_cdn(self, url: URL) -> bool:
        assert url.host
        base_host: str = self.primary_base_domain.host.removeprefix("www.")
        url_host: str = url.host.removeprefix("www.")
        return len(url_host.split(".")) > len(base_host.split("."))
