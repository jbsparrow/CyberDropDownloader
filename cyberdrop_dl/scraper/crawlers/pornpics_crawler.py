from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


class PornPicsCrawler(Crawler):
    primary_base_domain = URL("https://pornpics.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "pornpics", "PornPics")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "galleries" in scrape_item.url.parts:
            await self.gallery(scrape_item)
        elif scrape_item.url.query.get("g"):
            await self.search(scrape_item)
        elif len(scrape_item.url.parts) > 1:
            await self.category(scrape_item)
        else:
            raise ValueError

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
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

        images = soup.select("div#main a.rel-link")
        for image in images:
            link_str: str = image.get("href")
            link = self.parse_url(link_str)
            if not self.check_album_results(link, results):
                filename, ext = get_filename_and_ext(link.name)
                new_scrape_item = self.create_scrape_item(scrape_item, link, add_parent=scrape_item.url)
                await self.handle_file(link, new_scrape_item, filename, ext, custom_filename=filename)
            scrape_item.add_children()

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image page."""
        ...

    def is_cdn(self, url: URL) -> bool:
        assert url.host
        return self.primary_base_domain.host in url.host and "." in url.host.rstrip(".com")
