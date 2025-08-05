from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyberdrop_dl import crawlers
from cyberdrop_dl.crawlers.crawler import create_crawlers
from cyberdrop_dl.scraper import scrape_mapper

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager

TEST_BASE_CRAWLER = next(iter(crawlers.GENERIC_CRAWLERS))


@pytest.mark.parametrize(
    "link",
    [
        "https://bunkr.com",
        "https://dropbox.uk",
        "https://forum.allporncomix.com",
        "https://cyberfile.me/abhl",
        "https://forums.plex.tv/"
        "https://forums.socialmediagirls.com/threads/en-fr-tools-to-download-upload-content-websites-softwares-extensions.13930/#post-2070848",
    ],
)
def test_generic_crawlers_that_match_supported_crawlers_should_not_be_created(
    running_manager: Manager, link: str
) -> None:
    _ = scrape_mapper.get_crawlers_mapping()
    crawler = next(iter(create_crawlers([link], TEST_BASE_CRAWLER)))
    with pytest.raises(ValueError) as exc_info:
        scrape_mapper.register_crawler(scrape_mapper.existing_crawlers, crawler(running_manager), from_user="raise")
    assert f"Unable to assign {link.split('/')[0]}" in str(exc_info.value)


@pytest.mark.parametrize(
    "link",
    [
        "https://forum.otherforum.com",
        "https://cyberfolder.me/abhl",
        "https://meta.discourse.org/",
    ],
)
def test_generic_crawlers_that_do_no_match_supported_crawlers_should_be_created(
    running_manager: Manager, link: str
) -> None:
    _ = scrape_mapper.get_crawlers_mapping()
    crawler = next(iter(create_crawlers([link], TEST_BASE_CRAWLER)))
    existing_crawlers = scrape_mapper.existing_crawlers.copy()
    crawlers_before = set(existing_crawlers.values())
    scrape_mapper.register_crawler(existing_crawlers, crawler(running_manager), from_user="raise")
    new_crawlers = set(existing_crawlers.values()) - crawlers_before
    assert len(new_crawlers) == 1
    created_crawler = next(iter(new_crawlers))
    assert issubclass(type(created_crawler), TEST_BASE_CRAWLER)
