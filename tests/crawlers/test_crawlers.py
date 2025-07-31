from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING, Literal, NamedTuple, NotRequired
from unittest import mock

import pytest
from pydantic import TypeAdapter
from typing_extensions import TypedDict

from cyberdrop_dl.data_structures.url_objects import MediaItem, ScrapeItem
from cyberdrop_dl.scraper.scrape_mapper import ScrapeMapper

if TYPE_CHECKING:
    from cyberdrop_dl.crawlers.crawler import Crawler
    from cyberdrop_dl.managers.manager import Manager


def _amock(crawler: Crawler, func: str = "handle_media_item") -> mock._patch[mock.AsyncMock]:
    return mock.patch.object(crawler, func, new_callable=mock.AsyncMock)


class Result(TypedDict):
    # Simplified version of media_item
    url: str
    filename: str
    debrid_link: NotRequired[Literal["ANY"] | None]
    original_filename: NotRequired[str]
    referer: NotRequired[str]
    album_id: NotRequired[str | None]
    datetime: NotRequired[int | None]


class CrawlerTestCase(NamedTuple):
    domain: str
    input_url: str
    results: list[Result]


_TEST_CASE_ADAPTER = TypeAdapter(CrawlerTestCase)
_TEST_DATA: dict[str, list[tuple[str, list[Result]]]] = {}


def _load_test_cases(path: Path) -> None:
    module_spec = importlib.util.spec_from_file_location(path.stem, path)
    assert module_spec and module_spec.loader
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    _TEST_DATA[module.DOMAIN] = module.TEST_CASES


def _load_test_data() -> None:
    if _TEST_DATA:
        return
    for file in (Path(__file__).parent / "test_cases").iterdir():
        if not file.name.startswith("_") and file.suffix == ".py":
            _load_test_cases(file)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    _load_test_data()
    if "crawler_test_case" in metafunc.fixturenames:
        valid_domains = sorted(_TEST_DATA)
        domains_to_tests: list[str] = metafunc.config.test_crawlers_domains  # type: ignore
        for domain in domains_to_tests:
            assert domain in valid_domains, f"{domain = } is not a valid or has not tests defined"

        all_test_cases: list[CrawlerTestCase] = []
        for domain, test_cases in _TEST_DATA.items():
            if domain in domains_to_tests:
                all_test_cases.extend(CrawlerTestCase(domain, *case) for case in test_cases)
        metafunc.parametrize("crawler_test_case", all_test_cases, ids=lambda x: f"{x.domain} - {x.input_url}")


@pytest.mark.crawler_test_case
async def test_crawler(running_manager: Manager, crawler_test_case: CrawlerTestCase) -> None:
    # Check that this is a valid test case with pydantic
    domain, input_url, expected_results = _TEST_CASE_ADAPTER.validate_python(crawler_test_case, strict=True)

    async with ScrapeMapper(running_manager) as scrape_mapper:
        await scrape_mapper.run()
        crawler = next(
            (crawler for crawler in scrape_mapper.existing_crawlers.values() if crawler.DOMAIN == domain), None
        )
        assert crawler, f"{domain} is not a valid crawler domain. Test case is invalid"
        await crawler.startup()
        item = ScrapeItem(url=crawler.parse_url(input_url))
        with _amock(crawler) as func:
            await crawler.run(item)
            results: list[MediaItem] = sorted((call.args[0] for call in func.call_args_list), key=lambda x: x.url)

    expected_results = sorted(expected_results, key=lambda x: x["url"])
    _validate_results(crawler, expected_results, results)


def _validate_results(crawler: Crawler, expected_results: list[Result], results: list[MediaItem]) -> None:
    assert len(expected_results) == len(results)
    for expected_result, media_item in zip(expected_results, results, strict=True):
        for attr_name, expected_value in expected_result.items():
            result_value = getattr(media_item, attr_name)
            if isinstance(expected_value, str):
                if expected_value.startswith("http"):
                    expected_value = crawler.parse_url(expected_value)
                elif expected_value == "ANY":
                    expected_value = mock.ANY

            assert expected_value == result_value, f"{attr_name} is different"
