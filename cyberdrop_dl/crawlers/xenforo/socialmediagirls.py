from __future__ import annotations

from cyberdrop_dl.types import AbsoluteHttpURL

from .xenforo import PostSelectors, Selector, XenforoCrawler, XenforoSelectors


class SocialMediaGirlsCrawler(XenforoCrawler):
    primary_base_domain = AbsoluteHttpURL("https://forums.socialmediagirls.com")
    DOMAIN = "socialmediagirls"
    FOLDER_DOMAIN = "SocialMediaGirls"
    post_selectors = PostSelectors(
        content=Selector("div[class=bbWrapper]"),
        images=Selector("img[class*=bbImage]", "data-src"),
        date=Selector("time", "data-time"),
    )
    selectors = XenforoSelectors(posts=post_selectors)
