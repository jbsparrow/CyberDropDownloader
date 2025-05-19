from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import create_task_id
from cyberdrop_dl.crawlers.kemono import KemonoCrawler

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager


class NekohouseCrawler(KemonoCrawler):
    primary_base_domain = URL("https://nekohouse.su")
    DEFAULT_POST_TITLE_FORMAT = "{date} - {title}"

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager)
        self.domain = "nekohouse"
        self.folder_domain = "Nekohouse"
        self.services = "fanbox", "fantia", "fantia_products", "subscribestar", "twitter"

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "thumbnails" in scrape_item.url.parts:
            return await self.handle_direct_link(scrape_item)
        if "post" in scrape_item.url.parts:
            return await self.post_w_no_api(scrape_item)
        if any(x in scrape_item.url.parts for x in self.services):
            return await self.profile_w_no_api(scrape_item)
        if any(x in scrape_item.url.parts for x in ("posts", "discord")):
            raise ValueError

        await self.handle_direct_link(scrape_item)
