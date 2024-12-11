from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from .xenforo_crawler import PostSelectors, Selector, XenforoCrawler, XenforoSelectors

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class F95ZoneCrawler(XenforoCrawler):
    primary_base_domain = URL("https://f95zone.to")
    post_selectors = PostSelectors(
        date=Selector("time", "data-time"),
    )
    selectors = XenforoSelectors(posts=post_selectors)

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "f95zone", "F95Zone")
