from __future__ import annotations

from cyberdrop_dl.types import AbsoluteHttpURL

from .xenforo import XenforoCrawler


class SimpCityCrawler(XenforoCrawler):
    primary_base_domain = AbsoluteHttpURL("https://simpcity.su")
    login_required = False
    DOMAIN = "simpcity"
    FOLDER_DOMAIN = "SimpCity"
    session_cookie_name = "dontlikebots_user"
