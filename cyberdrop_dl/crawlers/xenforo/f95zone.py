from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.utils.utilities import error_handling_wrapper

from .xenforo import PostSelectors, Selector, XenforoCrawler, XenforoSelectors

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager


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

    def is_confirmation_link(self, link: URL) -> bool:
        return "masked" in link.parts or super().is_confirmation_link(link)

    @error_handling_wrapper
    async def handle_confirmation_link(self, link: URL, *, origin: ScrapeItem | None = None) -> URL | None:
        """Override to handle protected link confirmation."""
        async with self.request_limiter:
            data = ({"xhr": "1", "download": "1"},)
            JSON_Resp = await self.client.post_data(self.domain, link, data=data)

        if JSON_Resp["status"] == "ok":
            return self.parse_url(JSON_Resp["msg"])
        return None

    def filter_link(self, link: URL) -> URL:
        if "thumb" in link.parts:
            parts = [x for x in link.parts if x not in ("thumb", "/")]
            new_path = "/".join(parts)
            return link.with_path(new_path)
        return link
