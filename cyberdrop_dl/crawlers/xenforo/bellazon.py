from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

from .xenforo import PostSelectors, Selector, XenforoCrawler, XenforoSelectors

_post_selectors = PostSelectors(
    article="div[class*=ipsComment_content]",
    attachments=Selector("a[class*=ipsAttachLink]", "href"),
    content=Selector("div.cPost_contentWrap"),
    id=Selector("data-commentid", "data-commentid"),
    images=Selector("a[class*=ipsAttachLink_image]", "href"),
    videos=Selector("video.ipsEmbeddedVideo source", "src"),
)


# TODO: Bellazon uses Invision, not Xenforo. The selectors are completely different.
# See: https://github.com/jbsparrow/CyberDropDownloader/pull/1079#issuecomment-2982845352
class BellazonCrawler(XenforoCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://www.bellazon.com/main/")
    DOMAIN: ClassVar[str] = "bellazon"
    FOLDER_DOMAIN: ClassVar[str] = "Bellazon"
    login_required = False

    XF_THREAD_URL_PART = "topic"
    XF_POST_URL_PART_NAME = "comment-"
    XF_SELECTORS = XenforoSelectors(
        posts=_post_selectors,
        title=Selector("span.ipsType_break.ipsContained span"),
        next_page=Selector("li.ipsPagination_next a[href]", "href"),
    )
