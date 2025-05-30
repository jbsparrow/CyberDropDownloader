from __future__ import annotations

from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.crawlers.crawler import create_task_id
from cyberdrop_dl.crawlers.kemono import KemonoCrawler, UserPost

if TYPE_CHECKING:
    from aiohttp_client_cache.response import AnyResponse

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager


class CoomerCrawler(KemonoCrawler):
    primary_base_domain = URL("https://coomer.su")
    DEFAULT_POST_TITLE_FORMAT = "{date} - {title}"

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager)
        self.domain = "coomer"
        self.folder_domain = "Coomer"
        self.api_entrypoint = URL("https://coomer.su/api/v1")
        self.services = "onlyfans", "fansly"
        self.request_limiter = AsyncLimiter(4, 1)
        self.session_cookie = self.manager.config_manager.authentication_data.coomer.session

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def async_startup(self) -> None:
        def check_coomer_page(response: AnyResponse):
            if any(p in response.url.parts for p in ("onlyfans", "fansly", "data")):
                return False
            return True

        self.register_cache_filter(self.primary_base_domain, check_coomer_page)

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        return await self._fetch_kemono_defaults(scrape_item)

    def _handle_post_content(self, scrape_item: ScrapeItem, post: UserPost) -> None:
        """Handles the content of a post."""
        if "#ad" in post.content and self.manager.config_manager.settings_data.ignore_options.ignore_coomer_ads:
            return

        return super()._handle_post_content(scrape_item, post)
