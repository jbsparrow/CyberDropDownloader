from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from .xenforo_crawler import PostSelectors, Selector, XenforoCrawler, XenforoSelectors

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class XBunkerCrawler(XenforoCrawler):
    primary_base_domain = URL("https://xbunker.nu/")
    domain = "xbunker"
    post_selectors = PostSelectors(
        content=Selector("div[class=bbWrapper]", None),
        images=Selector("img[class*=bbImage], a[class*=js-lbImage]", "data-src"),
        date=Selector("time", "data-time"),
    )
    selectors = XenforoSelectors(posts=post_selectors)

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, self.domain, "XBunker")
        self.attachment_url_part += "data"
