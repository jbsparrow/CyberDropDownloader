from __future__ import annotations

from typing import TYPE_CHECKING

from cyberdrop_dl.types import AbsoluteHttpURL

from .xenforo import PostSelectors, Selector, XenforoCrawler, XenforoSelectors

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class XBunkerCrawler(XenforoCrawler):
    primary_base_domain = AbsoluteHttpURL("https://xbunker.nu/")
    domain = "xbunker"
    post_selectors = PostSelectors(
        content=Selector("div[class=bbWrapper]"),
        images=Selector("img[class*=bbImage], a[class*=js-lbImage]", "data-src"),
        date=Selector("time", "data-time"),
    )
    selectors = XenforoSelectors(posts=post_selectors)

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, self.DOMAIN, "XBunker")
        self.attachment_url_parts += "data"
