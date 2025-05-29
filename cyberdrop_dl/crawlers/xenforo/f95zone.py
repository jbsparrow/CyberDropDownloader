from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.types import AbsoluteHttpURL
from cyberdrop_dl.utils.utilities import error_handling_wrapper

from .xenforo import PostSelectors, Selector, XenforoCrawler, XenforoSelectors

if TYPE_CHECKING:
    from yarl import URL

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class F95ZoneCrawler(XenforoCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://f95zone.to")
    post_selectors = PostSelectors(
        date=Selector("time", "data-time"),
        number=Selector("a[class=u-concealed]", "href"),
    )
    selectors = XenforoSelectors(posts=post_selectors)
    DOMAIN: ClassVar[str] = "f95zone"
    FOLDER_DOMAIN: ClassVar[str] = "F95Zone"

    def is_confirmation_link(self, link: AbsoluteHttpURL) -> bool:
        return "masked" in link.parts or super().is_confirmation_link(link)

    @error_handling_wrapper
    async def handle_confirmation_link(self, link: AbsoluteHttpURL, *, origin: ScrapeItem | None = None) -> URL | None:
        """Override to handle protected link confirmation."""
        async with self.request_limiter:
            data = ({"xhr": "1", "download": "1"},)
            JSON_Resp = await self.client.post_data(self.DOMAIN, link, data=data)

        if JSON_Resp["status"] == "ok":
            return self.parse_url(JSON_Resp["msg"])
        return None

    def filter_link(self, link: AbsoluteHttpURL) -> AbsoluteHttpURL:
        if "thumb" in link.parts:
            parts = [x for x in link.parts if x not in ("thumb", "/")]
            new_path = "/".join(parts)
            return link.with_path(new_path)
        return link
