from __future__ import annotations

import calendar
import itertools
import json
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, NewType

from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem

CARD_DOWNLOAD_SELECTOR = "li > a[title='Download Image']"

TimeStamp = NewType("TimeStamp", int)


CARD_SELECTOR = "a.card-image-link"
CARD_PAGE_TITLE_SELECTOR = "meta[property='og:title']"
SET_SERIES_CODE_SELECTOR = "div.card-tabs span[title='Set Series Code']"
SET_INFO_SELECTOR = "script:contains('datePublished')"
LAST_PAGE_SELECTOR = "a[title='Last Page (Press L)']"


@dataclass(slots=True)
class CardSet:
    name: str
    abbr: str
    set_series_code: str | None
    release_date: TimeStamp

    @property
    def full_code(self) -> str:
        if self.set_series_code:
            return f"{self.abbr}, {self.set_series_code}"
        return f"{self.abbr}"


# This is just for information about what properties the card has. We don't actually use this class
@dataclass(slots=True)
class Card:
    name: str
    number_str: str
    set: CardSet
    download_url: URL

    @property
    def full_name(self) -> str:
        if self.name:
            return f"{self.name} ({self.set.abbr}) #{self.number_str}"
        else:
            return f"#{self.number_str}"

    # This is just for information about what other properties the card has. We don't actually use them
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
    # Simplified version of Card that groups the information we can get from the title of a page
    name: str
    number_str: str  # This can actually contain letters as well, but the oficial name is `number`
    set_name: str
    set_abbr: str


class PkmncardsCrawler(Crawler):
    primary_base_domain = URL("https://pkmncards.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "pkmncards", "Pkmncards")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        n_parts = len(scrape_item.url.parts)
        if "card" in scrape_item.url.parts and n_parts > 2:
            return await self.card(scrape_item)
        if "set" in scrape_item.url.parts and n_parts > 2:
            return await self.card(scrape_item)

        # We can download from this URL but we can't get any metadata
        # It would be downloaded as a loose file with a random name, so i disabled it
        # if scrape_item.url.path.startswith("/wp-content/uploads/"):
        #    return await self.direct_file(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def set(self, scrape_item: ScrapeItem) -> None:
        card_set: CardSet | None = None
        last_page = -1
        # This is just to set the max children limit. `handle_card` will add the actual title
        scrape_item.setup_as_album("")

        # TODO: Add proper pagination
        for page in itertools.count(1):
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

            for thumb in soup.select(CARD_SELECTOR):
                link_str, page_url_str, title = thumb["src"], thumb["href"], thumb["title"]  # type: ignore
                simple_card = get_card_info_from_title(title)  # type: ignore
                page_url = self.parse_url(page_url_str)  # type: ignore
                link = self.parse_url(link_str)  # type: ignore

                if not card_set:
                    # Make a request for the first card to get the set information
                    async with self.request_limiter:
                        soup: BeautifulSoup = await self.client.get_soup(self.domain, page_url)
                    card_set = create_set(soup, simple_card)

                if last_page == 0:
                    last_page = int(soup.select_one(LAST_PAGE_SELECTOR).text.removeprefix("/"))  # type: ignore

                new_scrape_item = scrape_item.create_child(page_url)
                card = Card(simple_card.name, simple_card.number_str, card_set, link)
                await self.handle_card(new_scrape_item, card)
                scrape_item.add_children()

            if page >= last_page:
                break

    @error_handling_wrapper
    async def card(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        link_str: str = soup.select_one(CARD_DOWNLOAD_SELECTOR)["href"]  # type: ignore
        link = self.parse_url(link_str)
        title: str = soup.select_one(CARD_PAGE_TITLE_SELECTOR)["content"]  # type: ignore
        simple_card = get_card_info_from_title(title)
        card_set = create_set(soup, simple_card)
        card = Card(simple_card.name, simple_card.number_str, card_set, link)
        await self.handle_card(scrape_item, card)

    async def handle_card(self, scrape_item: ScrapeItem, card: Card) -> None:
        if not card.name:
            raise ScrapeError(422)
        set_title = self.create_title(f"{card.set.name} ({card.set.full_code})")
        scrape_item.setup_as_album(set_title, album_id=card.set.abbr)
        scrape_item.possible_datetime = card.set.release_date
        filename, ext = self.get_filename_and_ext(card.download_url.name, assume_ext=".jpg")
        custom_filename, _ = self.get_filename_and_ext(f"{card.full_name}{ext}")
        await self.handle_file(card.download_url, scrape_item, filename, ext, custom_filename=custom_filename)


def get_card_info_from_title(title: str) -> SimpleCard:
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
        return SimpleCard("", card_number, set_name, set_name)

    card_name, set_details = _rest.split("·", 1)
    set_name, set_abbr = set_details.replace(")", "").rsplit("(", 1)
    return SimpleCard(card_name.strip(), card_number.strip(), set_name.strip(), set_abbr.strip().upper())


def create_set(soup: BeautifulSoup, card: SimpleCard) -> CardSet:
    tag = soup.select_one(SET_SERIES_CODE_SELECTOR)
    # Some sets do not have series code
    set_series_code: str | None = tag.get_text(strip=True) if tag else None  # type: ignore
    set_info: dict[str, list[dict]] = json.loads(soup.select_one(SET_INFO_SELECTOR).text)  # type: ignore
    release_date: int | None = None
    for item in set_info["@graph"]:
        if iso_date := item.get("datePublished"):
            release_date = calendar.timegm(datetime.fromisoformat(iso_date).timetuple())
            break

    if not release_date:
        raise ScrapeError(422)

    return CardSet(card.set_name, card.set_abbr, set_series_code, TimeStamp(release_date))
