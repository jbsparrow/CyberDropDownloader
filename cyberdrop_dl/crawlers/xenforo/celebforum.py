from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

from .xenforo import PostSelectors, Selector, XenforoCrawler, XenforoSelectors

if TYPE_CHECKING:
    from yarl import URL


class CelebForumCrawler(XenforoCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://celebforum.to")
    post_selectors = PostSelectors(
        date=Selector("time", "data-time"),
        images=Selector("a[class*=js-lbImage]", "href"),
    )
    selectors = XenforoSelectors(posts=post_selectors)
    DOMAIN: ClassVar[str] = "celebforum"
    FOLDER_DOMAIN: ClassVar[str] = "CelebForum"

    def filter_link(self, link: URL) -> URL | None:
        if link.host == self.PRIMARY_URL.host:
            if all(part in link.parts for part in ["data", "attachments"]):  # Thumbnails
                return None
            if all(part in link.parts for part in ["data", "assets"]):  # Placeholder content for insufficient rank
                return None
        return link
