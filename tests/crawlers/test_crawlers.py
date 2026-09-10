from __future__ import annotations

import re
from collections.abc import Callable, Generator, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest

import tests
from cyberdrop_dl.crawlers.crawler import compose_ep_name
from cyberdrop_dl.scrape_mapper import ScrapeMapper
from cyberdrop_dl.url_objects import AbsoluteHttpURL, MediaItem, ScrapeItem
from cyberdrop_dl.utils import parse_url

from . import test_cases

if TYPE_CHECKING:
    from cyberdrop_dl.crawlers.crawler import Crawler
    from cyberdrop_dl.manager import Manager


REPO_ROOT = Path(tests.__file__).parent.parent


def _crawler_mock(func: str = "handle_media_item") -> mock._patch[mock.AsyncMock]:
    return mock.patch(f"cyberdrop_dl.crawlers.crawler.Crawler.{func}", new_callable=mock.AsyncMock)


_TEST_DATA: test_cases.TestData = {}


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if not _TEST_DATA:
        _TEST_DATA.update(test_cases.load_cases())

    if "test_case" in metafunc.fixturenames:
        valid_domains = set(_TEST_DATA)
        domains_to_tests: list[str] = getattr(metafunc.config, "test_crawlers_domains", [])
        for domain in domains_to_tests:
            assert domain in valid_domains, f"{domain = } is not a valid or has not tests defined"

        cases = {domain: cases for domain, cases in _TEST_DATA.items() if domain in domains_to_tests}
        all_test_cases = test_cases.parse_cases(cases)
        metafunc.parametrize("test_case", all_test_cases, ids=lambda case: case.test_id)


@pytest.mark.crawler_test_case
async def test_crawler(running_manager: Manager, test_case: test_cases.CrawlerTestCase) -> None:
    if test_case.skip:
        pytest.skip(reason=test_case.skip if isinstance(test_case.skip, str) else "")

    with _crawler_mock() as func:
        async with ScrapeMapper(running_manager)() as scrape_mapper:
            await running_manager.http_client.load_cookie_files([REPO_ROOT / "cookies.txt"])
            await scrape_mapper.run()
            cls = next(
                (crawler for crawler in scrape_mapper.crawlers.values() if test_case.domain == crawler.DOMAIN),
                None,
            )
            assert cls, f"{test_case.domain} is not a valid crawler domain. Test case is invalid"
            crawler = scrape_mapper._factory(cls)
            await crawler.__async_init__()
            item = ScrapeItem.from_url(crawler.parse_url(test_case.url))
            item.download_folder = running_manager.config.download_folder
            await crawler.run(item)

    results: list[MediaItem] = sorted((call.args[0] for call in func.call_args_list), key=lambda x: str(x.url))
    count = test_case.count or len(test_case.results)
    _assert_n_results(test_case, len(results))
    if count:
        func.assert_awaited()
        _validate_results(crawler, test_case, results)


def _assert_n_results(test_case: test_cases.CrawlerTestCase, n_results: int) -> None:
    count = test_case.count or len(test_case.results)
    if isinstance(count, Sequence):
        assert n_results in count
    else:
        assert count == n_results


class _NOT_NONE:  # noqa: N801, PLW1641
    def __eq__(self, other: object) -> bool:
        return other is not None

    def __ne__(self, other: object) -> bool:
        return other is None

    def __repr__(self) -> str:
        return "<NOT_NONE>"


NOT_NONE = _NOT_NONE()


def _validate_results(crawler: Crawler, test_case: test_cases.CrawlerTestCase, results: list[MediaItem]) -> None:  # noqa: C901
    expected_results = dict(sorted(((x["url"], idx), x) for idx, x in enumerate(test_case.results, 1)))
    origin = getattr(crawler, "PRIMARY_URL", AbsoluteHttpURL("https://google.com"))
    for (index, expected), media_item in zip(expected_results.items(), results, strict=False):
        for attr_name, expected_value in expected.items():
            result_value = getattr(media_item, attr_name)
            if isinstance(result_value, Path):
                result_value = result_value.as_posix()

            match expected_value:
                case type():
                    assert isinstance(result_value, expected_value), (
                        f"{attr_name} for result#{index} is {type(result_value)!r}, expected {expected_value!r}"
                    )
                    continue

                case str():
                    match expected_value:
                        case "ANY":
                            expected_value = mock.ANY
                        case "NOT_NONE":
                            expected_value = NOT_NONE
                        case _:
                            if expected_value.startswith("http"):
                                expected_value = crawler.parse_url(expected_value, origin)

                            elif expected_value.startswith("re:"):
                                expected_value = expected_value.removeprefix("re:")
                                assert re_search(expected_value, result_value), (
                                    f"{attr_name} for result#{index} is different, "
                                    f"{result_value = } does not match {expected_value!r}"
                                )
                                continue

                            elif attr_name == "url":
                                expected_value = AbsoluteHttpURL(expected_value)

            assert expected_value == result_value, f"{attr_name} for result#{index} is different"


def _re_search(expected: str, result: object) -> re.Match[str] | None:
    try:
        return re.search(expected, str(result))
    except re.error:
        pass


def re_search(expected: str, result: str) -> re.Match[str] | None:
    return _re_search(expected, result) or _re_search(re.escape(expected), result)


@pytest.mark.parametrize(
    ("url", "filename"),
    [
        (
            "https://techdigitalspace.com/wp-content/uploads/2025/11/Valve-Steam-Machine-2.jpg",
            "Valve-Steam-Machine-2.jpg",
        ),
        (
            "https://simpcity.su/attachments/273974549_106860831858568_7219174579013873561_n-jpg.40743",
            "273974549_106860831858568_7219174579013873561_n.jpg",
        ),
        (
            "https://storage.googleapis.com/gweb-uniblog-publish-prod/images/Android_14-Hero_image-P8P.width-1300.png",
            "Android_14-Hero_image-P8P.width-1300.png",
        ),
    ],
)
async def test_direct_http_crawler(running_manager: Manager, url: str, filename: str) -> None:
    test_case = test_cases.CrawlerTestCase(domain="no_crawler", url=url, results=[{"url": url, "filename": filename}])

    with _crawler_mock() as func:
        async with ScrapeMapper(running_manager)() as scrape_mapper:
            crawler = scrape_mapper._direct_http
            await scrape_mapper.run()
            item = ScrapeItem(
                url=parse_url(test_case.url),
                download_folder=running_manager.config.download_folder,
            )
            await crawler.fetch(item)

    results: list[MediaItem] = sorted((call.args[0] for call in func.call_args_list), key=lambda x: str(x.url))
    func.assert_awaited()
    _validate_results(crawler, test_case, results)


def test_invalid_crawler_modules_should_raise_import_error() -> None:
    from cyberdrop_dl.crawlers import Registry

    with pytest.raises(ImportError, match="Could not import crawlers from module"):
        Registry._import_module("cyberdrop_dl.crawler.fake_crawler_12345")


def test_public_methods_have_error_handling_wrapper() -> None:
    import inspect

    from cyberdrop_dl.crawlers import Registry
    from cyberdrop_dl.crawlers.crawler import Crawler
    from cyberdrop_dl.utils.errors import is_error_wrapped

    def returns_none(func: Callable[..., Any]) -> bool:
        return_ = inspect.signature(func).return_annotation
        return return_ == "None" or return_ is type(None)

    def public_methods(cls: type):
        return (
            (name, method)
            for name, method in inspect.getmembers(cls, predicate=inspect.isfunction)
            if not name.startswith("_")
        )

    base_methods = {name for name, _ in public_methods(Crawler)}

    def unsafe_public_methods(cls: type) -> Generator[str]:
        return (
            name
            for name, method in public_methods(cls)
            if name not in base_methods and not is_error_wrapped(method) and returns_none(method)
        )

    errors: list[Exception] = []
    for crawler in sorted(Registry.get_crawlers(generic=True), key=lambda x: x.__name__):
        unwrapped_methods = sorted(unsafe_public_methods(crawler))
        if unwrapped_methods:
            errors.append(ValueError(crawler.__name__, unwrapped_methods))

    if errors:
        exc = BaseExceptionGroup("Some crawler has unsafe public methods that could crash CDL", errors)
        exc.add_note("Wrap them with @error_handling_wrapper or make them private")
        raise exc


def test_load_test_data() -> None:
    test_data = test_cases.load_cases()
    assert len(test_data) > 20
    assert "dropbox" in test_data
    dropbox = test_data["dropbox"]
    assert type(dropbox) is test_cases.TestCaseModule
    assert len(dropbox.cases) == 4

    for case in dropbox.cases:
        assert type(case) is dict
        assert "url" in case


@pytest.mark.parametrize(
    ("season", "ep", "name", "expected"),
    [
        (20, 34, "episode a", "S20E034 - episode a"),
        (9, 2, "episode b", "S09E002 - episode b"),
        (2, 4, None, "S02E004"),
        (None, 2, None, "E002"),
        (None, None, "episode d", "episode d"),
        (120, 0, "episode e", "S120E000 - episode e"),
    ],
)
def test_compose_ep_name(season: int | None, ep: int | None, name: str | None, expected: str) -> None:
    name = compose_ep_name(season, ep, name)
    assert name == expected


def test_compose_ep_name_raise_value_error_if_empty() -> None:
    with pytest.raises(ValueError):
        compose_ep_name(None, None, "")
