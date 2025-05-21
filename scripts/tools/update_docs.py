from pathlib import Path

from cyberdrop_dl.utils.args import CDL_EPILOG, CustomHelpFormatter, make_parser

CLI_ARGUMENTS_MD = Path(__file__).parents[1] / "docs/reference/cli-arguments.md"


def update_cli_overview() -> None:
    parser, _ = make_parser()

    def _get_formatter(_=None) -> CustomHelpFormatter:
        return CustomHelpFormatter(parser.prog, width=300)

    parser._get_formatter = _get_formatter
    help_text = parser.format_help()
    shell = "```shell"
    cli_overview, *_ = help_text.partition(CDL_EPILOG)
    current_text = CLI_ARGUMENTS_MD.read_text(encoding="utf8")
    new_text, *_ = current_text.partition(shell)
    new_text += f"{shell}\n{cli_overview}```\n"
    if current_text != new_text:
        CLI_ARGUMENTS_MD.write_text(new_text, encoding="utf8")
