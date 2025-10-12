from pathlib import Path

import pytest

from cyberdrop_dl.main import run
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
        run(tuple(command.split()))
    except SystemExit:
        pass
    captured = capsys.readouterr()
    output = captured.out
    assert text in output


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
