from __future__ import annotations

from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.crawlers.crawler import create_task_id
from cyberdrop_dl.crawlers.kemono import KemonoCrawler, UserPost
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


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

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "favorites" in scrape_item.url.parts:
            return await self.favorites(scrape_item)
        return await self._fetch_kemono_defaults(scrape_item)

    @error_handling_wrapper
    async def favorites(self, scrape_item: ScrapeItem) -> None:
        """Scrapes the users' favourites and creates scrape items for each artist found."""
        if not self.session_cookie:
            msg = "No session cookie found in the config file, cannot scrape favorites"
            raise ScrapeError(401, msg)

        cookies = {"session": self.session_cookie}
        self.update_cookies(cookies)
        title = self.create_title("My favorites")
        scrape_item.setup_as_profile(title)
        api_url = self.api_entrypoint / "account/favorites"
        favourites_api_url = api_url.with_query(type="artist")
        async with self.request_limiter:
            json_resp = await self.client.get_json(self.domain, favourites_api_url)

        cookies = {"session": ""}
        self.update_cookies(cookies)

        for user in json_resp:
            id, service = user["id"], user["service"]
            url = self.primary_base_domain / service / "user" / id
            new_scrape_item = scrape_item.create_child(url)
            self.manager.task_group.create_task(self.run(new_scrape_item))

    def _handle_post_content(self, scrape_item: ScrapeItem, post: UserPost) -> None:
        """Handles the content of a post."""
        if "#ad" in post.content and self.manager.config_manager.settings_data.ignore_options.ignore_coomer_ads:
            return

        return super()._handle_post_content(scrape_item, post)
