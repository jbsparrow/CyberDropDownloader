from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

from ._invision import InvisionCrawler


class BellazonCrawler(InvisionCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://www.bellazon.com/main/")
    DOMAIN: ClassVar[str] = "bellazon"
    FOLDER_DOMAIN: ClassVar[str] = "Bellazon"
    login_required = False
