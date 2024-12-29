import os
from dataclasses import dataclass, field
from pathlib import Path

from cyberdrop_dl.managers.config_manager import ConfigManager
from cyberdrop_dl.managers.manager import Manager
from cyberdrop_dl.managers.path_manager import PathManager
from cyberdrop_dl.utils import apprise
from cyberdrop_dl.utils.constants import NotificationResult
from tests.fake_classes.managers import FakeCacheManager

TEST_FILES_PATH = Path("tests/test_files/apprise")
FAKE_MANAGER = Manager()
FAKE_MANAGER.cache_manager = FakeCacheManager(FAKE_MANAGER)


def test_get_apprise_urls():
    result = apprise.get_apprise_urls(FAKE_MANAGER, file=TEST_FILES_PATH / "invalid_single_url.txt")
    assert result == []

    result = apprise.get_apprise_urls(FAKE_MANAGER, file=TEST_FILES_PATH / "invalid_multiple_urls.txt")
    assert result == []

    result = apprise.get_apprise_urls(FAKE_MANAGER, file=TEST_FILES_PATH / "valid_single_url.txt")
    assert isinstance(result, list), "Result is not a list"
    assert len(result) == 1, "This should be a single URL"
    assert isinstance(result[0], apprise.AppriseURL), "Parsed URL is not an AppriseURL"

    result = apprise.get_apprise_urls(FAKE_MANAGER, file=TEST_FILES_PATH / "valid_multiple_urls.txt")
    assert isinstance(result, list), "Result is not a list"
    assert len(result) == 5, "These should be 5 URLs"

    expected_result = [
        apprise.AppriseURL(url="discord://avatar@webhook_id/webhook_token", tags={"no_logs"}),
        apprise.AppriseURL(url="enigma2://hostname", tags={"another_tag", "no_logs"}),
        apprise.AppriseURL(url="mailto://domain.com?user=userid&pass=password", tags={"tag2", "tag_1", "no_logs"}),
        apprise.AppriseURL(url="reddit://user:password@app_id/app_secret/subreddit", tags={"attach_logs"}),
        apprise.AppriseURL(url="windows://", tags={"simplified"}),
    ]

    for index in range(len(result)):
        got = result[index]
        expected = expected_result[index]
        assert isinstance(got, apprise.AppriseURL), f"Parsed URL {got} is not an AppriseURL"
        assert got == expected, f"Parsed URL: {got.raw_url}, Expected URL: {expected.raw_url}"


async def test_send_apprise_notifications():
    @dataclass
    class AppriseTestCase:
        include: list[str]
        url: str
        result: NotificationResult
        exclude: list[str] = field(default_factory=list)

    FAKE_MANAGER.config_manager = ConfigManager(FAKE_MANAGER)

    async def send_notification(test_case: AppriseTestCase):
        FAKE_MANAGER.config_manager.apprise_urls = apprise.get_apprise_urls(FAKE_MANAGER, url=test_case.url)
        FAKE_MANAGER.path_manager = PathManager(FAKE_MANAGER)
        FAKE_MANAGER.path_manager.main_log = TEST_FILES_PATH / "valid_single_url.txt"
        result, logs = await apprise.send_apprise_notifications(FAKE_MANAGER)
        assert result.value == test_case.result.value, f"Result for this case should be {test_case.result.value}"
        assert isinstance(logs, list), "Invalid return type for logs"
        assert logs, "Logs can't be empty"
        logs_as_str = "\n".join([line.msg for line in logs])
        assert all(match in logs_as_str for match in test_case.include), "Logs do not match expected pattern"
        if test_case.exclude:
            assert not any(match in logs_as_str for match in test_case.exclude), "Logs should not match exclude pattern"
        assert "error" not in logs_as_str.casefold(), "Apprise logs have errors"

    url_fail = "windows://" if os.name != "nt" else "macosx://"
    url_success = os.environ.get("APPRISE_TEST_EMAIL_URL")
    url_success_attach_logs = f"attach_logs={url_success}"

    assert url_success, "Email URL should be set on enviroment"

    test_cases = [
        [["There are no service(s) to notify"], url_fail, NotificationResult.FAILED],
        [["Sent Email to"], url_success, NotificationResult.SUCCESS, ["Preparing Email attachment"]],
        [["Sent Email to", "Preparing Email attachment"], url_success_attach_logs, NotificationResult.SUCCESS],
    ]
    for test_case in test_cases:
        case = AppriseTestCase(*test_case)
        await send_notification(case)
