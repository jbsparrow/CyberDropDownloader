from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from .xenforo_crawler import PostSelectors, Selector, XenforoCrawler, XenforoSelectors

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class BellazonCrawler(XenforoCrawler):
    primary_base_domain = URL("https://www.bellazon.com/main/")
    domain = "bellazon"
    thread_url_part = "topic"
    login_required = False
    post_selectors = PostSelectors(
        content=Selector("div[class=cPost_contentWrap]", None),
        images=Selector("a[class*=ipsAttachLink_image]", "href"),
        videos=Selector("video[class=ipsEmbeddedVideo] source", "src"),
        date=Selector("time", "datetime"),
    )
    selectors = XenforoSelectors(
        posts=post_selectors,
        title=Selector("span.ipsType_break.ipsContained span", None),
    )

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, self.domain, "Bellazon")
