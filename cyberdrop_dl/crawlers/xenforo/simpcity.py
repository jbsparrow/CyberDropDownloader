from __future__ import annotations

from typing import ClassVar

from aiolimiter import AsyncLimiter

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

from .xenforo import XenforoCrawler


class SimpCityCrawler(XenforoCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://simpcity.cr")
    DOMAIN: ClassVar[str] = "simpcity"
    FOLDER_DOMAIN: ClassVar[str] = "SimpCity"
    LOGIN_USER_COOKIE_NAME = "ogaddgmetaprof_user"
    login_required = False
    IGNORE_EMBEDED_IMAGES_SRC = False
    OLD_DOMAINS: ClassVar[tuple[str, ...]] = ("simpcity.su",)

    def __post_init__(self) -> None:
        super().__post_init__()
        self.request_limiter = AsyncLimiter(1, 10)
