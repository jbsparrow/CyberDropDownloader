from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.types import AbsoluteHttpURL

from .xenforo import PostSelectors, Selector, XenforoCrawler, XenforoSelectors


class XBunkerCrawler(XenforoCrawler):
    primary_base_domain = AbsoluteHttpURL("https://xbunker.nu/")
    DOMAIN: ClassVar[str] = "xbunker"
    FOLDER_DOMAIN: ClassVar[str] = "XBunker"
    post_selectors = PostSelectors(
        content=Selector("div[class=bbWrapper]"),
        images=Selector("img[class*=bbImage], a[class*=js-lbImage]", "data-src"),
        date=Selector("time", "data-time"),
    )
    selectors = XenforoSelectors(posts=post_selectors)
