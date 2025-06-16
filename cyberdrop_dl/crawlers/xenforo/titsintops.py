from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from yarl import URL

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css

from .xenforo import PostSelectors, Selector, XenforoCrawler, XenforoSelectors

if TYPE_CHECKING:
    from bs4 import Tag


class TitsInTopsCrawler(XenforoCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://titsintops.com/phpBB2")
    DOMAIN: ClassVar[str] = "titsintops"
    FOLDER_DOMAIN: ClassVar[str] = "TitsInTops"
    post_selectors = PostSelectors(
        images=Selector("a[class*=file-preview]", "href"),
    )
    selectors = XenforoSelectors(posts=post_selectors)

    def filter_link(self, link: URL) -> URL:
        return URL(
            str(link)
            .replace("index.php%3F", "index.php/")
            .replace("index.php?", "index.php/")
            .replace("index.php/goto", "index.php?goto")
        )

    def pre_filter_link(self, link: str) -> str:
        return link.replace("index.php?", "index.php/").replace("index.php%3F", "index.php/")

    def is_image_or_attachment(self, link_obj: Tag) -> bool:
        is_image = link_obj.select_one("img")
        text = css.get_text(link_obj)
        if "view attachment" in text.lower():
            return False
        title: str | None = css.get_attr_or_none(link_obj, "title")
        if title and "permanent link" in title.lower():
            return False
        link_str: str | None = css.get_attr_or_none(link_obj, self.selectors.posts.links.element)
        return not (is_image and self.is_attachment(link_str))
