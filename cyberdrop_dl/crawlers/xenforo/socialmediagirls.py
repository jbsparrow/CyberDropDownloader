from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.types import AbsoluteHttpURL

from .xenforo import PostSelectors, Selector, XenforoCrawler, XenforoSelectors


class SocialMediaGirlsCrawler(XenforoCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://forums.socialmediagirls.com")
    DOMAIN: ClassVar[str] = "socialmediagirls"
    FOLDER_DOMAIN: ClassVar[str] = "SocialMediaGirls"
    post_selectors = PostSelectors(
        content=Selector("div[class=bbWrapper]"),
        images=Selector("img[class*=bbImage]", "data-src"),
        date=Selector("time", "data-time"),
    )
    selectors = XenforoSelectors(posts=post_selectors)
