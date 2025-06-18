from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, ClassVar, final

from cyberdrop_dl.crawlers.crawler import Crawler
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils.utilities import (
    error_handling_wrapper,
)

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, ScrapeItem


class MessageBoardCrawler(Crawler, is_abc=True):
    SUPPORTS_THREAD_RECURSION: ClassVar[bool] = False

    @property
    def scrape_single_forum_post(self) -> bool:
        return self.manager.config_manager.settings_data.download_options.scrape_single_forum_post

    @property
    def max_thread_depth(self) -> int:
        return self.manager.config_manager.settings_data.download_options.maximum_thread_depth

    @classmethod
    @abstractmethod
    def is_attachment(cls, url: AbsoluteHttpURL) -> bool: ...

    @abstractmethod
    async def forum(self, scrape_item: ScrapeItem) -> None: ...

    @abstractmethod
    async def thread(self, scrape_item: ScrapeItem) -> None: ...

    @abstractmethod
    async def post(self, scrape_item: ScrapeItem) -> None: ...

    @error_handling_wrapper
    async def handle_link(self, scrape_item: ScrapeItem, link: AbsoluteHttpURL) -> None:
        if link == self.PRIMARY_URL:
            return
        if self.is_attachment(link):
            return await self.handle_internal_link(scrape_item.create_new(link))
        if self.PRIMARY_URL.host in scrape_item.url.host and self.stop_thread_recursion(scrape_item):
            msg = f"Skipping nested thread URL {scrape_item.url} found on {scrape_item.origin}"
            return self.log(msg)
        new_scrape_item = scrape_item.copy()
        new_scrape_item.type = None
        new_scrape_item.reset_childen()
        self.handle_external_links(new_scrape_item)
        scrape_item.add_children()

    @error_handling_wrapper
    async def handle_internal_link(self, scrape_item: ScrapeItem) -> None:
        if len(scrape_item.url.parts) < 5 and not scrape_item.url.suffix:
            return
        filename, ext = self.get_filename_and_ext(scrape_item.url.name)
        scrape_item.add_to_parent_title("Attachments")
        scrape_item.part_of_album = True
        await self.handle_file(scrape_item.url, scrape_item, filename, ext)

    @final
    def stop_thread_recursion(self, scrape_item: ScrapeItem) -> bool:
        if (
            not self.SUPPORTS_THREAD_RECURSION
            or not self.max_thread_depth
            or (len(scrape_item.parent_threads) > self.max_thread_depth)
        ):
            return True
        return False

    @final
    async def write_last_forum_post(self, thread_url: AbsoluteHttpURL, last_post_url: AbsoluteHttpURL | None) -> None:
        if not last_post_url or last_post_url == thread_url:
            return
        await self.manager.log_manager.write_last_post_log(last_post_url)


ForumCrawler = MessageBoardCrawler
