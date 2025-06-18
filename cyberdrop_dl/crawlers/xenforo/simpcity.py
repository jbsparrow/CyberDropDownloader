from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

from .xenforo import XenforoCrawler


class SimpCityCrawler(XenforoCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://simpcity.su")
    DOMAIN: ClassVar[str] = "simpcity"
    FOLDER_DOMAIN: ClassVar[str] = "SimpCity"
    XF_USER_COOKIE_NAME = "dontlikebots_user"
    login_required = False
