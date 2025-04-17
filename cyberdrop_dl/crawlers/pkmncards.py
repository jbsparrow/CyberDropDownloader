from __future__ import annotations

import calendar
import json
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, NewType

from bs4 import BeautifulSoup
from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup, Tag

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


TimeStamp = NewType("TimeStamp", int)


CARD_DOWNLOAD_SELECTOR = "li > a[title='Download Image']"
CARD_SELECTOR = "a.card-image-link"
CARD_PAGE_TITLE_SELECTOR = "meta[property='og:title']"
CARD_NAME_SELECTOR = "span[title='Name'] a"
CARD_NUMBER_SELECTOR = "span[title='Number'] a"

SET_NAME_SELECTOR = "span[title='Set'] a"
SET_ABBR_SELECTOR = "span[title='Set Abbreviation'] a"
SET_SERIES_CODE_SELECTOR = "span[title='Set Series Code'] a"


CARD_FROM_FULL_SELECTOR = "article[id*='post-']"
CARD_PAGE_URL_SELECTOR = "a[title='Permalink / Title']"

SET_SERIES_CODE_SELECTOR = "div.card-tabs span[title='Set Series Code']"
SET_INFO_SELECTOR = "script:contains('datePublished')"
NEXT_PAGE_SELECTOR = "a[title='Next Page (Press →)']"


@dataclass(slots=True)
class Card:
    """A Pokemon card"""

    name: str
    number_str: str
    set: CardSet
    download_url: URL

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
    number_str: str  # This can actually contain letters as well, but the oficial name is `number`
    set_name: str
    set_abbr: str


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


class PkmncardsCrawler(Crawler):
    primary_base_domain = URL("https://pkmncards.com")
    next_page_selector = NEXT_PAGE_SELECTOR

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "pkmncards", "Pkmncards")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""

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

        page_url = self.primary_base_domain / "series" / scrape_item.url.parts[2]
        page_url = page_url.with_query(sort="date", ord="auto", display="full")
        async for soup in self.web_pager(page_url):
            # Can't use `iter_children` becuase we need to pass `cart_tag` to self.card
            for card_tag in soup.select(CARD_FROM_FULL_SELECTOR):
                card_page_url_str: str = soup.select_one(CARD_PAGE_URL_SELECTOR)["href"]  # type: ignore
                new_scrape_item = scrape_item.create_child(card_page_url_str)
                await self.card(new_scrape_item, card_tag)
                scrape_item.add_children()

    @error_handling_wrapper
    async def card_set(self, scrape_item: ScrapeItem) -> None:
        # This is just to set the max children limit. `handle_card` will add the actual title
        scrape_item.setup_as_album("")

        card_set: CardSet | None = None
        page_url = self.primary_base_domain / "set" / scrape_item.url.parts[2]
        page_url = page_url.with_query(sort="date", ord="auto")
        async for soup in self.web_pager(page_url):
            for thumb in soup.select(CARD_SELECTOR):
                parts: tuple[str, str, str] = thumb.select_one("img")["src"], thumb["href"], thumb["title"]  # type: ignore
                link_str, card_page_url_str, title = parts
                simple_card = get_card_info_from_title(title)
                card_page_url = self.parse_url(card_page_url_str)
                download_url = self.parse_url(link_str)

                if not card_set:
                    # Make a request for the first card to get the set information
                    async with self.request_limiter:
                        soup: BeautifulSoup = await self.client.get_soup(self.domain, card_page_url)
                    card_set = create_set(soup)

                new_scrape_item = scrape_item.create_child(card_page_url)
                card = Card(simple_card.name, simple_card.number_str, card_set, download_url)
                await self.handle_card(new_scrape_item, card)
                scrape_item.add_children()

    @error_handling_wrapper
    async def card(self, scrape_item: ScrapeItem, card_tag: Tag | None = None) -> None:
        if not card_tag:
            async with self.request_limiter:
                soup_or_tag = await self.client.get_soup(self.domain, scrape_item.url)
        else:
            soup_or_tag: Tag = card_tag

        name = soup_or_tag.select_one(CARD_NAME_SELECTOR).text  # type: ignore
        number = soup_or_tag.select_one(CARD_NUMBER_SELECTOR).text  # type: ignore
        link_str: str = soup_or_tag.select_one(CARD_DOWNLOAD_SELECTOR)["href"]  # type: ignore
        link = self.parse_url(link_str)
        card_set = create_set(soup_or_tag)
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
        custom_filename, _ = self.get_filename_and_ext(f"{card.full_name}{ext}")
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)


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

    card_name, _set_details = _rest.split("·", 1)
    set_name, set_abbr = _set_details.replace(")", "").rsplit("(", 1)
    return SimpleCard(card_name.strip(), card_number.strip(), set_name.strip(), set_abbr.strip().upper())


def create_set(soup: Tag) -> CardSet:
    tag = soup.select_one(SET_SERIES_CODE_SELECTOR)
    # Some sets do not have series code
    set_series_code: str | None = tag.get_text(strip=True) if tag else None  # type: ignore
    set_info: dict[str, list[dict]] = json.loads(soup.select_one(SET_INFO_SELECTOR).text)  # type: ignore
    release_date: int | None = None
    for item in set_info["@graph"]:
        if iso_date := item.get("datePublished"):
            release_date = calendar.timegm(datetime.fromisoformat(iso_date).timetuple())
            break

    set_abbr = soup.select_one(SET_ABBR_SELECTOR).text  # type: ignore
    set_name = soup.select_one(SET_NAME_SELECTOR).text  # type: ignore

    if not release_date:
        raise ScrapeError(422)

    return CardSet(set_name, set_abbr, set_series_code, TimeStamp(release_date))
