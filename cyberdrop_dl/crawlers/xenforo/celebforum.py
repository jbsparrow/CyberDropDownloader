from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

from .xenforo import XenforoCrawler


class CelebForumCrawler(XenforoCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://celebforum.to")
    DOMAIN: ClassVar[str] = "celebforum"
    FOLDER_DOMAIN: ClassVar[str] = "CelebForum"
    IGNORE_EMBEDED_IMAGES_SRC: ClassVar = True  # images src is always a thumbnail

    @classmethod
    def is_thumbnail(cls, link: AbsoluteHttpURL) -> bool:
        if link.host == cls.PRIMARY_URL.host:
            if all(part in link.parts for part in ["data", "attachments"]):  # Thumbnails
                return True
            if all(part in link.parts for part in ["data", "assets"]):  # Placeholder content for insufficient rank
                return True
        return False
