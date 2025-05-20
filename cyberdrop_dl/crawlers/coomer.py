from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from aiolimiter import AsyncLimiter

from cyberdrop_dl.crawlers.kemono import KemonoCrawler, UserPost
from cyberdrop_dl.types import AbsoluteHttpURL, OneOrTupleStrMapping

if TYPE_CHECKING:
    from aiohttp_client_cache.response import AnyResponse

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class CoomerCrawler(KemonoCrawler):
    SUPPORTED_PATHS: ClassVar[OneOrTupleStrMapping] = {
        "Model": "/<service>/user/",
        "Favorites": "/favorites",
        "Search": "/search?...",
        "Individual Post": "/user/post/",
        "Direct links": "",
    }
    primary_base_domain = AbsoluteHttpURL("https://coomer.su")
    DEFAULT_POST_TITLE_FORMAT: ClassVar[str] = "{date} - {title}"
    DOMAIN = "coomer"
    FOLDER_DOMAIN = "Coomer"
    API_ENTRYPOINT = AbsoluteHttpURL("https://coomer.su/api/v1")
    SERVICES = "onlyfans", "fansly"

    def __post_init__(self) -> None:
        super().__post_init__()
        self.request_limiter = AsyncLimiter(4, 1)
        self.session_cookie = self.manager.config_manager.authentication_data.coomer.session

    async def async_startup(self) -> None:
        def check_coomer_page(response: AnyResponse) -> bool:
            if any(p in response.url.parts for p in ("onlyfans", "fansly", "data")):
                return False
            return True

        self.register_cache_filter(self.primary_base_domain, check_coomer_page)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        return await self._fetch_kemono_defaults(scrape_item)

    def _handle_post_content(self, scrape_item: ScrapeItem, post: UserPost) -> None:
        """Handles the content of a post."""
        if "#ad" in post.content and self.manager.config_manager.settings_data.ignore_options.ignore_coomer_ads:
            return

        return super()._handle_post_content(scrape_item, post)
