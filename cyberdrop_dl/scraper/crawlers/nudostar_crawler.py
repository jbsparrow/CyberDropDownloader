from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from .xenforo_crawler import PostSelectors, Selector, XenforoCrawler, XenforoSelectors

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class NudoStarCrawler(XenforoCrawler):
    primary_base_domain = URL("https://nudostar.com")
    post_selectors = PostSelectors(
        date=Selector("time", "data-time"),
        number=Selector("a[class=u-concealed]", "href"),
    )
    selectors = XenforoSelectors(posts=post_selectors)
    domain = "nudostar"

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, self.domain, "NudoStar")
