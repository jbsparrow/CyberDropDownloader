from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css

from .xenforo import XenforoCrawler

if TYPE_CHECKING:
    from bs4 import Tag


class TitsInTopsCrawler(XenforoCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://titsintops.com/phpBB2")
    DOMAIN: ClassVar[str] = "titsintops"
    FOLDER_DOMAIN: ClassVar[str] = "TitsInTops"

    def parse_url(self, link: str) -> AbsoluteHttpURL:
        return super().parse_url(fix_link(link))

    def is_username_or_attachment(self, link_obj: Tag) -> bool:
        text = css.get_text(link_obj)
        if "view attachment" in text.lower():
            return True
        title = css.get_attr_no_error(link_obj, "title")
        if title and "permanent link" in title.lower():
            return True
        return super().is_username_or_attachment(link_obj)


def fix_link(link: str) -> str:
    return (
        link.replace("index.php%3F", "index.php/")
        .replace("index.php?", "index.php/")
        .replace("index.php?goto", "index.php/goto")
    )
