from __future__ import annotations

from cyberdrop_dl.types import AbsoluteHttpURL

from .xenforo import PostSelectors, Selector, XenforoCrawler, XenforoSelectors


class LeakedModelsCrawler(XenforoCrawler):
    primary_base_domain = AbsoluteHttpURL("https://leakedmodels.com/forum/")
    post_selectors = PostSelectors(
        date=Selector("time", "data-time"),
    )
    selectors = XenforoSelectors(posts=post_selectors)
    DOMAIN = "leakedmodels"
    FOLDER_DOMAIN = "LeakedModels"
