from pathlib import Path
from unittest import mock

import pytest
from pydantic import ValidationError

from cyberdrop_dl.main import _create_director, run
from cyberdrop_dl.utils.args import parse_args


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
    cookies_file.write_text("Not a cookie file", encoding="utf8")
    catch_exceptions(director.run)()

    logs = director.manager.path_manager.main_log.read_text(encoding="utf8")
    assert "does not look like a Netscape format cookies file" in logs

    startup_file = Path.cwd() / "startup.log"
    assert not startup_file.exists()


def test_startup_logger_is_created_on_yaml_error(tmp_cwd: Path) -> None:
    from cyberdrop_dl.exceptions import InvalidYamlError

    with mock.patch(
        "cyberdrop_dl.director.Director._run", side_effect=InvalidYamlError(Path("fake_file.yaml"), ValueError())
    ):
        try:
            run("--download")
        except SystemExit:
            pass

    startup_file = Path.cwd() / "startup.log"
    assert startup_file.exists()

    logs = startup_file.read_text(encoding="utf8")
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
    tmp_cwd: Path, exception: Exception | type[Exception], exists: bool, capsys: pytest.CaptureFixture[str]
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


def test_impersonate_defaults_to_true_with_no_args() -> None:
    result = parse_args(["--download"])
    assert result.cli_only_args.impersonate is None
    result = parse_args(["--impersonate"])
    assert result.cli_only_args.impersonate is True


def test_impersonate_accepts_valid_targets() -> None:
    result = parse_args(["--download", "--impersonate", "chrome"])
    assert result.cli_only_args.impersonate == "chrome"


def test_impersonate_does_not_accepts_invalid_values() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--impersonate", "not_a_browser"])
