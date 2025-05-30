from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.types import AbsoluteHttpURL

from .xenforo import PostSelectors, Selector, XenforoCrawler, XenforoSelectors


class LeakedModelsCrawler(XenforoCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://leakedmodels.com/forum/")
    post_selectors = PostSelectors(
        date=Selector("time", "data-time"),
    )
    selectors = XenforoSelectors(posts=post_selectors)
    DOMAIN: ClassVar[str] = "leakedmodels"
    FOLDER_DOMAIN: ClassVar[str] = "LeakedModels"
