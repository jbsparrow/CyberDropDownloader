from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from .xenforo_crawler import PostSelectors, Selector, XenforoCrawler, XenforoSelectors

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class TitsInTopsCrawler(XenforoCrawler):
    primary_base_domain = URL("https://titsintops.com")
    domain = "titsintops"
    post_selectors = PostSelectors(
        images=Selector("a[class=file-preview]", "href"),
    )
    selectors = XenforoSelectors(posts=post_selectors)
    login_required = True

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, self.domain, "TitsInTops")
        self.attachment_url_part = ["attachments", "data"]

    async def filter_link(self, link: URL):
        return URL(
            str(link)
            .replace("index.php%3F", "index.php/")
            .replace("index.php?", "index.php/")
            .replace("index.php/goto", "index.php?goto")
        )

    async def pre_filter_link(self, link):
        return URL(str(link).replace("index.php?", "index.php/"))
