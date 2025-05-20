from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.types import AbsoluteHttpURL

from .xenforo import PostSelectors, Selector, XenforoCrawler, XenforoSelectors


class BellazonCrawler(XenforoCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://www.bellazon.com/main/")
    DOMAIN = "bellazon"
    FOLDER_DOMAIN = "Bellazon"
    thread_url_part = "topic"
    login_required = False
    post_selectors = PostSelectors(
        element="div[class*=ipsComment_content]",
        content=Selector("div[class=cPost_contentWrap]"),
        attachments=Selector("a[class*=ipsAttachLink]", "href"),
        images=Selector("a[class*=ipsAttachLink_image]", "href"),
        videos=Selector("video[class=ipsEmbeddedVideo] source", "src"),
        date=Selector("time", "datetime"),
        number=Selector("data-commentid", "data-commentid"),
    )
    selectors = XenforoSelectors(
        posts=post_selectors,
        title=Selector("span.ipsType_break.ipsContained span"),
        next_page=Selector("li[class=ipsPagination_next] a", "href"),
        post_name="comment-",
    )
    ATTACHMENT_URL_PARTS = "attachments", "uploads"
