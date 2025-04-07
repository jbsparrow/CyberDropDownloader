from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, FILE_HOST_PROFILE, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


class EromeCrawler(Crawler):
    primary_base_domain = URL("https://www.erome.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "erome", "Erome")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "a" in scrape_item.url.parts:
            await self.album(scrape_item)
        else:
            await self.profile(scrape_item)

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a profile."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        title = self.create_title(scrape_item.url.name)
        albums = soup.select("a[class=album-link]")

        scrape_item.set_type(FILE_HOST_PROFILE, self.manager)

        for album in albums:
            link_str: str = album["href"]
            link = self.parse_url(link_str)
            new_scrape_item = self.create_scrape_item(scrape_item, link, title, True, add_parent=scrape_item.url)
            self.manager.task_group.create_task(self.run(new_scrape_item))
            scrape_item.add_children()

        next_page = soup.select_one('a[rel="next"]')
        if next_page:
            next_page_number = next_page.get("href").split("page=")[-1]
            next_page_url = scrape_item.url.with_query(f"page={next_page_number}")
            new_scrape_item = self.create_scrape_item(scrape_item, next_page_url)
            self.manager.task_group.create_task(self.run(new_scrape_item))

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

        title_portion = soup.select_one("title").text.rsplit(" - Porn")[0].strip()
        if not title_portion:
            title_portion = scrape_item.url.name
        title = self.create_title(title_portion, scrape_item.url.parts[2])
        scrape_item.add_to_parent_title(title)

        images = soup.select('img[class="img-front lasyload"]')
        videos = soup.select("div[class=media-group] div[class=video-lg] video source")

        image_links = [self.parse_url(image["data-src"]) for image in images]
        video_links = [self.parse_url(video["src"]) for video in videos]

        for link in image_links + video_links:
            filename, ext = self.get_filename_and_ext(link.name)
            if not self.check_album_results(link, results):
                await self.handle_file(link, scrape_item, filename, ext)
            scrape_item.add_children()
