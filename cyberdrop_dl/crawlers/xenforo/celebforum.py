from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

from .xenforo import XenforoCrawler


class CelebForumCrawler(XenforoCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://celebforum.to")
    DOMAIN: ClassVar[str] = "celebforum"
    FOLDER_DOMAIN: ClassVar[str] = "CelebForum"
    XF_IGNORE_EMBEDED_IMAGES_SRC: ClassVar = True

    def filter_link(self, link: AbsoluteHttpURL) -> AbsoluteHttpURL | None:
        if link.host == self.PRIMARY_URL.host:
            if all(part in link.parts for part in ["data", "attachments"]):  # Thumbnails
                return None
            if all(part in link.parts for part in ["data", "assets"]):  # Placeholder content for insufficient rank
                return None
        return link
