from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.dates import TimeStamp, to_timestamp
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import Tag

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class Selectors:
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
    SET_INFO = "script:-soup-contains('datePublished')"
    NEXT_PAGE = "li[title='Next Page (Press →)'] a"


_SELECTORS = Selectors()


@dataclass(slots=True)
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

    # Other card properties that we don't use
    # hp: int = 0
    # color: str = ""
    # type: str = ""
    # text: str = ""
    # pokemons: tuple[str, ...] = ()
    # simbols: tuple[str, ...] = ()
    # ram: int = 0
    # rarity: str = ""


@dataclass(slots=True)
class SimpleCard:
    """Simplified version of Card that groups the information we can get from the title of a page."""

    name: str
    number_str: str  # This can actually contain letters as well, but the official name is `number`
    set_name: str
    set_abbr: str
    download_url: AbsoluteHttpURL


@dataclass(slots=True)
class CardSet:
    """Group of cards"""

    name: str
    abbr: str
    set_series_code: str | None
    release_date: TimeStamp

    @property
    def full_code(self) -> str:
        if not self.set_series_code:
            return f"{self.abbr}"
        return f"{self.abbr}, {self.set_series_code}"


PRIMARY_URL = AbsoluteHttpURL("https://pkmncards.com")


class PkmncardsCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"Card": "/card/...", "Set": "/set/...", "Series": "/series/..."}
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    NEXT_PAGE_SELECTOR: ClassVar[str] = _SELECTORS.NEXT_PAGE
    DOMAIN: ClassVar[str] = "pkmncards"

    def __post_init__(self) -> None:
        self.known_sets: dict[str, CardSet] = {}
        self.set_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if len(scrape_item.url.parts) > 2:
            if "card" in scrape_item.url.parts:
                return await self.card(scrape_item)
            if "set" in scrape_item.url.parts:
                return await self.card_set(scrape_item)
            if "series" in scrape_item.url.parts:
                return await self.series(scrape_item)

        # We can download from this URL but we can't get any metadata
        # It would be downloaded as a loose file with a random name, so i disabled it
        # if scrape_item.url.path.startswith("/wp-content/uploads/"):
        #    return await self.direct_file(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def series(self, scrape_item: ScrapeItem) -> None:
        # This is just to set the max children limit. `handle_card` will add the actual title
        scrape_item.setup_as_profile("")
        page_url = PRIMARY_URL / "series" / scrape_item.url.parts[2]
        await self._iter_from_url(scrape_item, page_url)

    @error_handling_wrapper
    async def card_set(self, scrape_item: ScrapeItem) -> None:
        scrape_item.setup_as_album("")
        page_url = PRIMARY_URL / "set" / scrape_item.url.parts[2]
        await self._iter_from_url(scrape_item, page_url)

    async def _iter_from_url(self, scrape_item: ScrapeItem, url: AbsoluteHttpURL) -> None:
        page_url = url.with_query(sort="date", ord="auto", display="images")
        async for soup in self.web_pager(page_url):
            for thumb in soup.select(_SELECTORS.CARD):
                link_str = css.select_one_get_attr(thumb, "img", "src")
                card_page_url_str = css.get_attr(thumb, "href")
                title = css.get_attr(thumb, "title")
                card_page_url = self.parse_url(card_page_url_str)
                download_url = self.parse_url(link_str)
                simple_card = create_simple_card(title, download_url)
                new_scrape_item = scrape_item.create_child(card_page_url)
                self.create_task(self.handle_simple_card(new_scrape_item, simple_card))
                scrape_item.add_children()

    @error_handling_wrapper
    async def card(self, scrape_item: ScrapeItem) -> None:
        soup = await self.request_soup(scrape_item.url)

        name = css.select_one_get_text(soup, _SELECTORS.CARD_NAME)
        number = css.select_one_get_text(soup, _SELECTORS.CARD_NUMBER)
        link_str: str = css.select_one_get_attr(soup, _SELECTORS.CARD_DOWNLOAD, "href")
        link = self.parse_url(link_str)
        card_set = create_set(soup)
        card = Card(name, number, card_set, link)
        await self.handle_card(scrape_item, card)

    @error_handling_wrapper
    async def handle_card(self, scrape_item: ScrapeItem, card: Card) -> None:
        if not card.name:
            raise ScrapeError(422)
        link = card.download_url  # .with_suffix(".png")  # they offer both jpg and png. png is higher quality
        set_title = self.create_title(f"{card.set.name} ({card.set.full_code})")
        scrape_item.setup_as_album(set_title, album_id=card.set.abbr)
        scrape_item.possible_datetime = card.set.release_date
        filename, ext = self.get_filename_and_ext(link.name, assume_ext=".jpg")
        custom_filename = self.create_custom_filename(card.full_name, ext)
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    async def handle_simple_card(self, scrape_item: ScrapeItem, simple_card: SimpleCard) -> None:
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
        await self.handle_card(scrape_item, card)
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
    tag = soup.select_one(_SELECTORS.SET_SERIES_CODE)
    # Some sets do not have series code
    set_series_code: str | None = tag.get_text(strip=True) if tag else None
    set_info: dict[str, list[dict]] = json.loads(css.select_one(soup, _SELECTORS.SET_INFO).text)
    release_date: int | None = None
    for item in set_info["@graph"]:
        if iso_date := item.get("datePublished"):
            release_date = to_timestamp(datetime.fromisoformat(iso_date))
            break

    set_abbr = css.select_one(soup, _SELECTORS.SET_ABBR).text
    set_name = css.select_one(soup, _SELECTORS.SET_NAME).text

    if not release_date:
        raise ScrapeError(422)

    return CardSet(set_name, set_abbr, set_series_code, TimeStamp(release_date))
