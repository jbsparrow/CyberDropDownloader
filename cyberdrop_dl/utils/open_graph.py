from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import bs4

_required_attrs = ("title", "type", "image", "url", "description")


class OpenGraph(dict[str, str | None]):
    """Open Graph properties. Each attribute corresponds to an OG property."""

    title: str
    type: str
    image: str
    url: str
    description: str

    def __getattr__(self, name) -> str | None:
        return self.get(name, None)

    def is_valid(self) -> bool:
        return all(self.get(attr) for attr in _required_attrs)


def parse(soup: bs4.BeautifulSoup) -> OpenGraph:
    """Extracts Open Graph properties (og properties) from soup."""
    og_props = OpenGraph()
    for meta in soup.select('meta[property^="og:"][content]'):
        name = meta["property"].replace("og:", "").replace(":", "_")  # type: ignore
        value = meta["content"]
        assert isinstance(value, str)
        og_props[name] = value or None

    if not og_props.get("title") and (title := soup.select_one("title, h1")):
        og_props["title"] = title.get_text(strip=True)

    return og_props


def get(name: str, /, soup: bs4.BeautifulSoup) -> str | None:
    if meta := soup.select_one(f'meta[property^="og:{name}"][content]'):
        value = meta["content"]
        assert isinstance(value, str)
        return value


def get_title(soup: bs4.BeautifulSoup) -> str | None:
    return get("title", soup)
