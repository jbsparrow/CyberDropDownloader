from __future__ import annotations

from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, FILE_HOST_PROFILE, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


class FapelloCrawler(Crawler):
    primary_base_domain = URL("https://fapello.su/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "fapello", "Fapello")
        self.request_limiter = AsyncLimiter(5, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if scrape_item.url.parts[-1] != "/":
            scrape_item.url = URL(str(scrape_item.url) + "/")

        if scrape_item.url.parts[-2].isdigit():
            await self.post(scrape_item)
        else:
            await self.profile(scrape_item)

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a profile."""
        async with self.request_limiter:
            soup, response_url = await self.client.get_soup_and_return_url(
                self.domain,
                scrape_item.url,
                origin=scrape_item,
            )
            if response_url != scrape_item.url:
                return

        scrape_item.set_type(FILE_HOST_PROFILE, self.manager)
        scrape_item.part_of_album = True

        title = self.create_title(soup.select_one('h2[class="font-semibold lg:text-2xl text-lg mb-2 mt-4"]').get_text())

        content = soup.select("div[id=content] a")
        for post in content:
            link_str: str = post.get("href")
            if "javascript" in link_str:
                video_tag = post.select_one("iframe")
                link_str: str = video_tag.get("src")

            link = self.parse_url(link_str)
            new_scrape_item = self.create_scrape_item(scrape_item, link, title, add_parent=scrape_item.url)
            self.handle_external_links(new_scrape_item)
            scrape_item.add_children()

        next_page = soup.select_one('div[id="next_page"] a')
        if next_page:
            next_page_str: str = next_page.get("href")
            next_page = self.parse_url(next_page_str)
            new_scrape_item = self.create_scrape_item(scrape_item, next_page)
            self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def post(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        content = soup.select_one('div[class="flex justify-between items-center"]')
        content_tags = content.select("img")
        content_tags.extend(content.select("source"))
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)

        async with self.request_limiter:
            soup = await self.client.get_soup(self.domain, scrape_item.url)

        for selection in content_tags:
            link_str: str = selection.get("src")
            link = self.parse_url(link_str)
            filename, ext = get_filename_and_ext(link.name)
            await self.handle_file(link, scrape_item, filename, ext)
            scrape_item.add_children()
