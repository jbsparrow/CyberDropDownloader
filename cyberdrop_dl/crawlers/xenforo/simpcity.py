from __future__ import annotations

from typing import TYPE_CHECKING

from cyberdrop_dl.types import AbsoluteHttpURL

from .xenforo import XenforoCrawler

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class SimpCityCrawler(XenforoCrawler):
    primary_base_domain = AbsoluteHttpURL("https://simpcity.su")
    login_required = False
    domain = "simpcity"
    session_cookie_name = "dontlikebots_user"

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, self.DOMAIN, "SimpCity")
