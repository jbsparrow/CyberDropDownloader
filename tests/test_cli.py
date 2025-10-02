from pathlib import Path
from unittest import mock

import pytest
from pydantic import ValidationError

from cyberdrop_dl.main import _create_director, run


@pytest.mark.parametrize(
    "command, text",
    [
        ("--help", "Bulk asynchronous downloader for multiple file hosts"),
        ("--show-supported-sites", "for a details about supported paths"),
    ],
)
def test_command_by_console_output(tmp_cwd: Path, capsys: pytest.CaptureFixture[str], command: str, text: str) -> None:
    try:
        run(command.split())
    except SystemExit:
        pass
    output = capsys.readouterr().out
    assert text in output


def test_startup_logger_should_not_be_created_on_a_successful_run(tmp_cwd: Path) -> None:
    run("--download")
    startup_file = Path.cwd() / "startup.log"
    assert not startup_file.exists()


def test_startup_logger_should_not_be_created_on_invalid_cookies(tmp_cwd: Path) -> None:
    from cyberdrop_dl.utils.logger import catch_exceptions

    director = _create_director("--download")
    cookies_file = director.manager.path_manager.cookies_dir / "cookies.txt"
    cookies_file.write_bytes(b"Not a cookie file")
    catch_exceptions(director.run)()

    logs = director.manager.path_manager.main_log.read_text()
    assert "does not look like a Netscape format cookies file" in logs

    startup_file = Path.cwd() / "startup.log"
    assert not startup_file.exists()


def test_startup_logger_is_created_on_yaml_error(tmp_cwd: Path) -> None:
    from cyberdrop_dl.exceptions import InvalidYamlError
    from cyberdrop_dl.utils.logger import catch_exceptions

    with mock.patch(
        "cyberdrop_dl.director.Director._run", side_effect=InvalidYamlError(Path("fake_file.yaml"), ValueError())
    ):
        director = _create_director("--download")
        catch_exceptions(director.run)()

    startup_file = Path.cwd() / "startup.log"
    assert startup_file.exists()

    logs = startup_file.read_text()
    assert "Unable to read file" in logs


@pytest.mark.parametrize(
    "exception, exists",
    [
        (ValueError, True),
        (OSError, True),
        (KeyboardInterrupt, False),
        (ValidationError("", []), False),
    ],
)
def test_startup_logger_when_manager_startup_fails(
    tmp_cwd: Path, exception: Exception | type[Exception], exists: bool
) -> None:
    with mock.patch("cyberdrop_dl.managers.manager.Manager.set_constants", side_effect=exception):
        try:
            run("--download")
        except SystemExit:
            pass
        startup_file = Path.cwd() / "startup.log"
        assert startup_file.exists() == exists


def test_startup_logger_should_not_be_created_when_using_invalid_cli_args(tmp_cwd: Path) -> None:
    try:
        run("--invalid-command")
    except SystemExit:
        pass
    startup_file = Path.cwd() / "startup.log"
    assert not startup_file.exists()
