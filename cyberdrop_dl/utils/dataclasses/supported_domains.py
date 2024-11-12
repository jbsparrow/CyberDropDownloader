from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass
class SupportedDomains:
    """The allows options for domains to skip when scraping and mappings."""

    supported_hosts: ClassVar[tuple[str, ...]] = (
        "bunkr",
        "bunkrr",
        "celebforum",
        "coomer",
        "cyberdrop",
        "cyberfile",
        "e-hentai",
        "erome",
        "f95zone",
        "fapello",
        "gofile",
        "host.church",
        "hotpic",
        "ibb.co",
        "imageban",
        "imagepond.net",
        "img.kiwi",
        "imgbox",
        "imgur",
        "jpeg.pet",
        "jpg.church",
        "jpg.fish",
        "jpg.fishing",
        "jpg.homes",
        "jpg.pet",
        "jpg1.su",
        "jpg2.su",
        "jpg3.su",
        "jpg4.su",
        "jpg5.su",
        "kemono",
        "leakedmodels",
        "mediafire",
        "nudostar.com",
        "nudostar.tv",
        "omegascans",
        "pimpandhost",
        "pixeldrain",
        "postimg",
        "realbooru",
        "real-debrid",
        "redd.it",
        "reddit",
        "redgifs",
        "rule34.xxx",
        "rule34.xyz",
        "rule34vault",
        "saint",
        "scrolller",
        "socialmediagirls",
        "toonily",
        "tokyomotion.net",
        "xbunker",
        "xbunkr",
        "xxxbunker",
        "simpcity",
    )

    supported_forums: ClassVar[tuple[str, ...]] = (
        "celebforum.to",
        "f95zone.to",
        "forums.socialmediagirls.com",
        "leakedmodels.com",
        "nudostar.com",
        "xbunker.nu",
        "simpcity.su",
    )
    supported_forums_map: ClassVar[dict[str, str]] = {
        "celebforum.to": "celebforum",
        "f95zone.to": "f95zone",
        "forums.socialmediagirls.com": "socialmediagirls",
        "leakedmodels.com": "leakedmodels",
        "nudostar.com": "nudostar",
        "xbunker.nu": "xbunker",
        "simpcity.su": "simpcity",
    }

    sites: list[str]
