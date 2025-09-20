from __future__ import annotations

from typing import TYPE_CHECKING

from cyberdrop_dl.exceptions import ScrapeError

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
    for meta in soup.select('meta[property^="og:"][content], meta[name^="og:"][content]'):
        try:
            name = _value(meta, "property")
        except IndexError:
            name = _value(meta, "name")
        name = name.replace("og:", "").replace(":", "_")
        if value := _value(meta):
            og_props[name] = value

    if not og_props.get("title") and (title := soup.select_one("title, h1")):
        og_props["title"] = title.get_text(strip=True)

    return og_props


def get(name: str, /, soup: bs4.BeautifulSoup) -> str | None:
    if meta := soup.select_one(f'meta[property^="og:{name}"][content], meta[name^="og:{name}"][content]'):
        return _value(meta)


def get_title(soup: bs4.BeautifulSoup) -> str | None:
    return get("title", soup)


def title(soup: bs4.BeautifulSoup) -> str:
    if title := get_title(soup):
        return title
    raise ScrapeError(422, "Page have no title [og properties]")


def _value(meta: bs4.Tag, name: str = "content") -> str:
    value = meta[name]
    assert isinstance(value, str)
    return value.strip()
