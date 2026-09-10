from __future__ import annotations

import asyncio
import dataclasses
from collections import defaultdict
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, json_ld
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import Tag

    from cyberdrop_dl.url_objects import ScrapeItem


class Selector:
    CARD = "a.card-image-link"
    CARD_DOWNLOAD = "li > a[title='Download Image']"
    CARD_PAGE_TITLE = "meta[property='og:title']"
    CARD_NAME = "span[title='Name'] a"
    CARD_NUMBER = "span[class='number'] a"
    CARD_FROM_FULL = "article[id*='post-']"
    CARD_PAGE_URL = "a[title='Permalink / Title']"

    SET_NAME = "span[title='Set'] a"
    SET_ABBR = "span[title='Set Abbreviation']"
    SET_SERIES_CODE = "div.card-tabs span[title='Set Series Code']"
    NEXT_PAGE = "li[title='Next Page (Press →)'] a"


@dataclasses.dataclass(slots=True)
class Card:
    """A Pokemon card"""

    name: str
    number_str: str
    set: CardSet
    download_url: AbsoluteHttpURL

    @property
    def full_name(self) -> str:
        if not self.name:
            return f"#{self.number_str}"
        return f"{self.name} ({self.set.abbr}) #{self.number_str}"


@dataclasses.dataclass(slots=True)
class SimpleCard:
    """Simplified version of Card that groups the information we can get from the title of a page."""

    name: str
    number_str: str  # This can actually contain letters as well, but the official name is `number`
    set_name: str
    set_abbr: str
    download_url: AbsoluteHttpURL


@dataclasses.dataclass(slots=True)
class CardSet:
    """Group of cards"""

    name: str
    abbr: str
    set_series_code: str | None
    release_date: float

    @property
    def full_code(self) -> str:
        if not self.set_series_code:
            return f"{self.abbr}"
        return f"{self.abbr}, {self.set_series_code}"


class PkmncardsCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Card": "/card/...",
        "Set": "/set/...",
        "Series": "/series/...",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://pkmncards.com")
    NEXT_PAGE_SELECTOR: ClassVar[str] = Selector.NEXT_PAGE
    DOMAIN: ClassVar[str] = "pkmncards"

    def __post_init__(self) -> None:
        self.known_sets: dict[str, CardSet] = {}
        self.set_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["card", _, *_]:
                return await self.card(scrape_item)
            case ["set", slug, *_]:
                return await self.card_set(scrape_item, slug)
            case ["series", slug, *_]:
                return await self.series(scrape_item, slug)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def series(self, scrape_item: ScrapeItem, slug: str) -> None:
        # This is just to set the max children limit. `handle_card` will add the actual title
        scrape_item.setup_as_profile("")
        page_url = self.PRIMARY_URL / "series" / slug
        await self._iter_from_url(scrape_item, page_url)

    @error_handling_wrapper
    async def card_set(self, scrape_item: ScrapeItem, slug: str) -> None:
        scrape_item.setup_as_album("")
        page_url = self.PRIMARY_URL / "set" / slug
        await self._iter_from_url(scrape_item, page_url)

    async def _iter_from_url(self, scrape_item: ScrapeItem, url: AbsoluteHttpURL) -> None:
        page_url = url.with_query(sort="date", ord="auto", display="images")
        async for soup in self.web_pager(page_url):
            for thumb in soup.select(Selector.CARD):
                link_str = css.select(thumb, "img", "src")
                card_page_url_str = css.attr(thumb, "href")
                title = css.attr(thumb, "title")
                card_page_url = self.parse_url(card_page_url_str)
                download_url = self.parse_url(link_str)
                simple_card = create_simple_card(title, download_url)
                new_scrape_item = scrape_item.create_child(card_page_url)
                self.create_task(self._simple_card(new_scrape_item, simple_card))
                scrape_item.add_children()

    @error_handling_wrapper
    async def card(self, scrape_item: ScrapeItem) -> None:
        soup = await self.request_soup(scrape_item.url)

        name = css.select_text(soup, Selector.CARD_NAME)
        number = css.select_text(soup, Selector.CARD_NUMBER)
        link_str: str = css.select(soup, Selector.CARD_DOWNLOAD, "href")
        link = self.parse_url(link_str)
        card_set = create_set(soup)
        card = Card(name, number, card_set, link)
        await self._card(scrape_item, card)

    @error_handling_wrapper
    async def _card(self, scrape_item: ScrapeItem, card: Card) -> None:
        if not card.name:
            raise ScrapeError(422)

        link = card.download_url  # .with_suffix(".png")  # they offer both jpg and png. png is higher quality
        set_title = self.create_title(f"{card.set.name} ({card.set.full_code})")
        scrape_item.setup_as_album(set_title, album_id=card.set.abbr)
        scrape_item.uploaded_at = card.set.release_date
        filename, ext = self.get_filename_and_ext(link.name, assume_ext=".jpg")
        custom_filename = self.create_custom_filename(card.full_name, ext)
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    async def _simple_card(self, scrape_item: ScrapeItem, simple_card: SimpleCard) -> None:
        @error_handling_wrapper
        async def get_card_set(self, scrape_item: ScrapeItem) -> CardSet:
            soup = await self.request_soup(scrape_item.url)
            return create_set(soup)

        async with self.set_locks[simple_card.set_abbr]:
            card_set = self.known_sets.get(simple_card.set_abbr)
            if not card_set:
                # Make a request for 1 card, to get the set information about the set
                card_set = await get_card_set(self, scrape_item)
                if not card_set:  # Request failed
                    return
                self.known_sets[simple_card.set_abbr] = card_set

        card = Card(simple_card.name, simple_card.number_str, card_set, simple_card.download_url)
        await self._card(scrape_item, card)
        scrape_item.add_children()


def create_simple_card(title: str, download_url: AbsoluteHttpURL) -> SimpleCard:
    """Over-complicated function to parse the information of a card from the title of a page or the alt-title of a thumbnail."""

    # ex: Fuecoco · Scarlet & Violet Promos (SVP) #002
    # ex: Sprigatito · Scarlet & Violet Promos (SVP) #001 ‹ PkmnCards  # noqa: RUF003
    # TODO: Replace with regex groups?

    clean_title = title.removesuffix("‹ PkmnCards").strip()  # noqa: RUF001
    _rest, card_number = clean_title.rsplit("#", 1)
    if clean_title.startswith("#"):
        # ex: #xy188 ‹ PkmnCards  # noqa: RUF003
        buffer = ""
        for char in reversed(card_number):
            if char.isdigit():
                buffer = char + buffer
            else:
                break
        set_name = card_number.removesuffix(buffer)
        return SimpleCard("", card_number, set_name, set_name, download_url)

    card_name, _set_details = _rest.split("·", 1)
    set_name, set_abbr = _set_details.replace(")", "").rsplit("(", 1)
    return SimpleCard(card_name.strip(), card_number.strip(), set_name.strip(), set_abbr.strip().upper(), download_url)


def create_set(soup: Tag) -> CardSet:
    series = soup.select_one(Selector.SET_SERIES_CODE)
    return CardSet(
        name=css.select_text(soup, Selector.SET_NAME),
        abbr=css.select_text(soup, Selector.SET_ABBR),
        set_series_code=series.get_text(strip=True) if series else None,
        release_date=json_ld.date_published(soup),
    )
