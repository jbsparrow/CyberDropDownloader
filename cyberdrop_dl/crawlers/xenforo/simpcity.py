from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.types import AbsoluteHttpURL

from .xenforo import XenforoCrawler


class SimpCityCrawler(XenforoCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://simpcity.su")
    login_required = False
    DOMAIN = "simpcity"
    FOLDER_DOMAIN = "SimpCity"
    session_cookie_name = "dontlikebots_user"
