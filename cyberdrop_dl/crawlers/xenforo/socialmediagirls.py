from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

from .xenforo import XenforoCrawler


class SocialMediaGirlsCrawler(XenforoCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://forums.socialmediagirls.com")
    DOMAIN: ClassVar[str] = "socialmediagirls"
    FOLDER_DOMAIN: ClassVar[str] = "SocialMediaGirls"
    IGNORE_EMBEDED_IMAGES_SRC = False
