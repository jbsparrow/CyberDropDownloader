from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils.utilities import error_handling_wrapper

from .xenforo import PostSelectors, Selector, XenforoCrawler, XenforoSelectors

if TYPE_CHECKING:
    from yarl import URL


_post_selectors = PostSelectors(date=Selector("time", "data-time"), id=Selector("a[class=u-concealed]", "href"))
_confirmation_data = ({"xhr": "1", "download": "1"},)


class F95ZoneCrawler(XenforoCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://f95zone.to")
    DOMAIN: ClassVar[str] = "f95zone"
    FOLDER_DOMAIN: ClassVar[str] = "F95Zone"
    XF_SELECTORS = XenforoSelectors(posts=_post_selectors)

    @error_handling_wrapper
    async def handle_confirmation_link(self, link: AbsoluteHttpURL) -> AbsoluteHttpURL | None:
        """Override to handle protected link confirmation."""
        async with self.request_limiter:
            json_resp = await self.client.post_data(self.DOMAIN, link, data=_confirmation_data)

        if json_resp["status"] == "ok":
            return self.parse_url(json_resp["msg"])

    def filter_link(self, link: AbsoluteHttpURL) -> URL:
        if "thumb" in link.parts:
            return link.with_path(link.path.replace("/thumb/", ""))
        return link
