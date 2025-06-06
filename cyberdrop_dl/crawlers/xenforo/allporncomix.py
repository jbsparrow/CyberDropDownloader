from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

from .xenforo import PostSelectors, Selector, XenforoCrawler, XenforoSelectors


class AllPornComixCrawler(XenforoCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://forum.allporncomix.com")
    DOMAIN: ClassVar[str] = "allporncomix"
    FOLDER_DOMAIN: ClassVar[str] = "AllPornComix"
    login_required = False
    post_selectors = PostSelectors(
        content=Selector("div[class=bbWrapper]"),
        images=Selector("img[class*=bbImage]", "data-src"),
        date=Selector("time", "datetime"),
        attachments=Selector("section[class=message-attachments] .attachmentList .file .file-preview", "href"),
    )
    selectors = XenforoSelectors(posts=post_selectors)
