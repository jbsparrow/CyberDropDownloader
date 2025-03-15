from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from .xenforo import XenforoCrawler

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class SimpCityCrawler(XenforoCrawler):
    primary_base_domain = URL("https://simpcity.su")
    login_required = False
    domain = "simpcity"
    session_cookie_name = "dontlikebots_user"

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, self.domain, "SimpCity")
