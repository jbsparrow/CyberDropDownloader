from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.crawlers.crawler import create_task_id
from cyberdrop_dl.crawlers.mixdrop import MixDropCrawler
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_og_properties, get_text_between

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


class Selectors:
    JS = "script:contains('MDCore.ref')"
    VIDEO = "iframe[src*=mixdrop]"
    USER_NAME = "div.info a[href*='archivebate.store/profile/']"
    SITE_NAME = f"{USER_NAME} + p"
    NEXT_PAGE = "a.page-link[rel='next']"
    PROFILE_VIDEOS = "section.video_item a"


_SELECTORS = Selectors()


class ArchiveBateCrawler(MixDropCrawler):
    SUPPORTED_SITES: ClassVar[dict] = {}
    primary_base_domain = URL("https://www.archivebate.store")
    next_page = _SELECTORS.NEXT_PAGE

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager)
        self.domain = "archivebate"
        self.folder_domain = "ArchiveBate"
        self.request_limiter = AsyncLimiter(4, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "watch" in scrape_item.url.parts:
            return await self.video(scrape_item)

        if "profile" in scrape_item.url.parts:
            return await self.profile(scrape_item)

        raise ValueError

    async def profile(self, scrape_item: ScrapeItem) -> None:
        # Not supported, video entries are dynamically generated with javascript
        # They have an API to request them but it also returns javascript
        raise ValueError
        scrape_item.setup_as_profile("")
        async for soup in self.web_pager(scrape_item.url):
            for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.PROFILE_VIDEOS):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        url = scrape_item.url
        # Can't use check_complete_by_referer. We need the mixdrop url for that
        check_complete = await self.manager.db_manager.history_table.check_complete(self.domain, url, url)
        if check_complete:
            self.log(f"Skipping {scrape_item.url} as it has already been downloaded", 10)
            self.manager.progress_manager.download_progress.add_previously_completed()
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        if "This video has been deleted" in soup.text:
            raise ScrapeError(410)

        og_props = get_og_properties(soup)
        date_str: str = get_text_between(og_props.description, "show on", " - ").strip()
        user_name: str = soup.select_one(_SELECTORS.USER_NAME).text  # type: ignore
        site_name: str = soup.select_one(_SELECTORS.SITE_NAME).text  # type: ignore
        video_src: str = soup.select_one(_SELECTORS.VIDEO)["src"]  # type: ignore
        title = self.create_title(f"{user_name} [{site_name}]")
        scrape_item.setup_as_profile(title)
        scrape_item.possible_datetime = self.parse_date(date_str)
        show_title = f"Show on {date_str}"

        mixdrop_url = self.get_embed_url(self.parse_url(video_src))  # Override domain

        if await self.check_complete_from_referer(mixdrop_url):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, mixdrop_url)

        link = self.create_download_link(soup)
        filename, ext = self.get_filename_and_ext(link.name)
        custom_filename, _ = self.get_filename_and_ext(f"{show_title}{ext}")
        scrape_item.url = mixdrop_url
        await self.handle_file(url, scrape_item, filename, ext, custom_filename=custom_filename, debrid_link=link)
