from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.utils.utilities import error_handling_wrapper

from .xenforo_crawler import PostSelectors, Selector, XenforoCrawler, XenforoSelectors

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


class F95ZoneCrawler(XenforoCrawler):
    primary_base_domain = URL("https://f95zone.to")
    post_selectors = PostSelectors(
        date=Selector("time", "data-time"),
        number=Selector("a[class=u-concealed]", "href"),
    )
    selectors = XenforoSelectors(posts=post_selectors)
    domain = "f95zone"

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, self.domain, "F95Zone")

    async def is_confirmation_link(self, link: URL) -> bool:
        parts = link.parts
        if (len(parts) >= 1 and parts[1] == "masked") or "f95zone.to/masked/" in str(link):
            return True
        return False

    @error_handling_wrapper
    async def handle_confirmation_link(self, link: URL, *, origin: ScrapeItem | None = None) -> URL | None:
        """Override to handle protected link confirmation."""
        async with self.request_limiter:
            JSON_Resp = await self.client.post_data(
                self.domain, link, data={"xhr": "1", "download": "1"}, origin=origin
            )

        if JSON_Resp["status"] == "ok":
            return URL(JSON_Resp["msg"])
        return

    async def filter_link(self, link: URL) -> bool:
        if any(part == "thumb" for part in link.parts):
            return URL(str(link).replace("/thumb/", "/"))
        return link
