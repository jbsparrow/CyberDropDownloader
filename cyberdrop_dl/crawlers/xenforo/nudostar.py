from __future__ import annotations

from cyberdrop_dl.types import AbsoluteHttpURL

from .xenforo import PostSelectors, Selector, XenforoCrawler, XenforoSelectors


class NudoStarCrawler(XenforoCrawler):
    primary_base_domain = AbsoluteHttpURL("https://nudostar.com/forum/")
    post_selectors = PostSelectors(
        date=Selector("time", "data-time"),
        number=Selector("a[class=u-concealed]", "href"),
    )
    selectors = XenforoSelectors(posts=post_selectors)
    DOMAIN = "nudostar"
    FOLDER_DOMAIN = "NudoStar"
