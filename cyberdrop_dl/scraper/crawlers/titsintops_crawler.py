from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from .xenforo_crawler import PostSelectors, Selector, XenforoCrawler, XenforoSelectors

if TYPE_CHECKING:
    from bs4 import Tag

    from cyberdrop_dl.managers.manager import Manager


class TitsInTopsCrawler(XenforoCrawler):
    primary_base_domain = URL("https://titsintops.com")
    domain = "titsintops"
    post_selectors = PostSelectors(
        images=Selector("a[class*=file-preview]", "href"),
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
        return URL(str(link).replace("index.php?", "index.php/").replace("index.php%3F", "index.php/"))

    def is_valid_post_link(self, link_obj: Tag) -> bool:
        is_image = link_obj.select_one("img")
        text = link_obj.text
        if text and "view attachment" in text.lower():
            return False
        if link_obj.get("title") and "permanent link" in link_obj.get("title").lower():
            return False
        link = link_obj.get(self.selectors.posts.links.element)
        return not (is_image and self.is_attachment(link))
