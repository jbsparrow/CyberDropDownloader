from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

from .xenforo import PostSelectors, Selector, XenforoCrawler, XenforoSelectors

_post_selectors = PostSelectors(
    number=Selector("a[class=u-concealed]", "href"),
)


class NudoStarCrawler(XenforoCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://nudostar.com/forum/")
    XF_SELECTORS = XenforoSelectors(posts=_post_selectors)
    DOMAIN: ClassVar[str] = "nudostar"
    FOLDER_DOMAIN: ClassVar[str] = "NudoStar"
