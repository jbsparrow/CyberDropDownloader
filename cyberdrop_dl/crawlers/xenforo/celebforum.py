from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from .xenforo import PostSelectors, Selector, XenforoCrawler, XenforoSelectors

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class CelebForumCrawler(XenforoCrawler):
    primary_base_domain = URL("https://celebforum.to")
    post_selectors = PostSelectors(
        date=Selector("time", "data-time"),
        images=Selector("a[class*=js-lbImage]", "href"),
    )
    selectors = XenforoSelectors(posts=post_selectors)
    domain = "celebforum"

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, self.domain, "CelebForum")

    def filter_link(self, link: URL) -> URL | None:
        if link.host == self.primary_base_domain.host:
            if all(part in link.parts for part in ["data", "attachments"]):  # Thumbnails
                return None
            if all(part in link.parts for part in ["data", "assets"]):  # Placeholder content for insufficient rank
                return None
        return link
