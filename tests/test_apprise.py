from pathlib import Path

from cyberdrop_dl.managers.manager import Manager
from cyberdrop_dl.utils import apprise
from tests.fake_classes.managers import FakeCacheManager

TEST_FILES_PATH = Path("tests/test_files/apprise")
FAKE_MANAGER = Manager()
FAKE_MANAGER.cache_manager = FakeCacheManager(FAKE_MANAGER)


def test_get_apprise_urls():
    result = apprise.get_apprise_urls(FAKE_MANAGER, TEST_FILES_PATH / "invalid_single_url.txt")
    assert result is None

    result = apprise.get_apprise_urls(FAKE_MANAGER, TEST_FILES_PATH / "invalid_multiple_urls.txt")
    assert result is None

    result = apprise.get_apprise_urls(FAKE_MANAGER, TEST_FILES_PATH / "valid_single_url.txt")
    assert isinstance(result, list), "Result is not a list"
    assert len(result) == 1, "List does not have exactly one item"
    assert isinstance(result[0], apprise.AppriseURL), "Parsed URL is not an AppriseURL"

    result = apprise.get_apprise_urls(FAKE_MANAGER, TEST_FILES_PATH / "valid_multiple_urls.txt")
    assert isinstance(result, list), "Result is not a list"
    assert len(result) == 5, "List does not have 5 items"

    expected_result = [
        apprise.AppriseURL(url="discord://avatar@webhook_id/webhook_token", tags={"no_logs"}),
        apprise.AppriseURL(url="enigma2://hostname", tags={"another_tag"}),
        apprise.AppriseURL(url="mailto://domain.com?user=userid&pass=password", tags={"tag2", "tag_1"}),
        apprise.AppriseURL(url="reddit://user:password@app_id/app_secret/subreddit", tags={"attach_logs"}),
        apprise.AppriseURL(url="windows://", tags={"simplified"}),
    ]

    for index in range(len(result)):
        got = result[index]
        expected = expected_result[index]
        assert isinstance(got, apprise.AppriseURL), f"Parsed URL {got} is not an AppriseURL"
        assert got == expected, f"Parsed URL: {got.raw_url}, Expected URL: {expected.raw_url}"
