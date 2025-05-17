import sys
import time
import warnings
from argparse import SUPPRESS, ArgumentParser, BooleanOptionalAction, RawDescriptionHelpFormatter
from argparse import _ArgumentGroup as ArgGroup
from collections.abc import Iterable
from datetime import date
from enum import StrEnum, auto
from pathlib import Path
from shutil import get_terminal_size
from typing import TYPE_CHECKING, Self

from pydantic import BaseModel, Field, ValidationError, computed_field, field_validator, model_validator

from cyberdrop_dl import __version__, env
from cyberdrop_dl.config_definitions import ConfigSettings, GlobalSettings
from cyberdrop_dl.types import AliasModel, HttpURL
from cyberdrop_dl.utils.yaml import handle_validation_error

if TYPE_CHECKING:
    from pydantic.fields import FieldInfo

CLI_ARGUMENTS_MD = Path("docs/reference/cli-arguments.md")
CDL_EPILOG = "Visit the wiki for additional details: https://script-ware.gitbook.io/cyberdrop-dl"


class UIOptions(StrEnum):
    DISABLED = auto()
    ACTIVITY = auto()
    SIMPLE = auto()
    FULLSCREEN = auto()


warnings.simplefilter("always", DeprecationWarning)
WARNING_TIMEOUT = 5  # seconds


def _check_mutually_exclusive(group: Iterable, msg: str) -> None:
    if sum(1 for value in group if value) >= 2:
        raise ValueError(msg)


def is_terminal_in_portrait() -> bool:
    """Check if CDL is being run in portrait mode based on a few conditions."""
    # Return True if running in portait mode, False otherwise (landscape mode)

    def check_terminal_size():
        terminal_size = get_terminal_size()
        width, height = terminal_size.columns, terminal_size.lines
        aspect_ratio = width / height

        # High aspect ratios are likely to be in landscape mode
        if aspect_ratio >= 3.2:
            return False

        # Check for mobile device in portrait mode
        if (aspect_ratio < 1.5 and height >= 40) or (width <= 85 and aspect_ratio < 2.3):
            return True

        # Assume landscape mode for other cases
        return False

    if env.PORTRAIT_MODE:
        return True

    return check_terminal_size()


class CommandLineOnlyArgs(BaseModel):
    links: list[HttpURL] = Field([], description="link(s) to content to download (passing multiple links is supported)")
    appdata_folder: Path | None = Field(None, description="AppData folder path")
    completed_after: date | None = Field(None, description="only download completed downloads at or after this date")
    completed_before: date | None = Field(None, description="only download completed downloads at or before this date")
    config: str | None = Field(None, description="name of config to load")
    config_file: Path | None = Field(None, description="path to the CDL settings.yaml file to load")
    disable_cache: bool = Field(False, description="Temporarily disable the requests cache")
    download: bool = Field(False, description="skips UI, start download immediatly")
    download_dropbox_folders_as_zip: bool = Field(False, description="download Dropbox folder without api key as zip")
    download_tiktok_audios: bool = Field(False, description="download TikTok audios")
    max_items_retry: int = Field(0, description="max number of links to retry")
    no_textual_ui: bool = Field(False, description="Disable textual UI (TUI with mouse support)")
    portrait: bool = Field(is_terminal_in_portrait(), description="show UI in a portrait layout")
    print_stats: bool = Field(True, description="Show stats report at the end of a run")
    retry_all: bool = Field(False, description="retry all downloads")
    retry_failed: bool = Field(False, description="retry failed downloads")
    retry_maintenance: bool = Field(
        False, description="retry download of maintenance files (bunkr). Requires files to be hashed"
    )
    show_supported_sites: bool = Field(False, description="shows a list of supported sites and exits")
    ui: UIOptions = Field(UIOptions.FULLSCREEN, description="DISABLED, ACTIVITY, SIMPLE or FULLSCREEN")

    @property
    def retry_any(self) -> bool:
        return any((self.retry_all, self.retry_failed, self.retry_maintenance))

    @property
    def fullscreen_ui(self) -> bool:
        return self.ui == UIOptions.FULLSCREEN

    @property
    def multiconfig(self) -> bool:
        return bool(self.config) and self.config.casefold() == "all"

    @computed_field
    def __computed__(self) -> dict:
        return {"retry_any": self.retry_any, "fullscreen_ui": self.fullscreen_ui, "multiconfig": self.multiconfig}

    @model_validator(mode="after")
    def mutually_exclusive(self) -> Self:
        group1 = [self.links, self.retry_all, self.retry_failed, self.retry_maintenance]
        msg1 = "`--links`, '--retry-all', '--retry-maintenace' and '--retry-failed' are mutually exclusive"
        _check_mutually_exclusive(group1, msg1)
        group2 = [self.config, self.config_file]
        msg2 = "'--config' and '--config-file' are mutually exclusive"
        _check_mutually_exclusive(group2, msg2)
        return self

    @field_validator("ui", mode="before")
    @classmethod
    def lower(cls, value: str) -> str:
        return value.lower()


class DeprecatedArgs(BaseModel):
    no_ui: bool = Field(
        False,
        description="disables the UI/progress view entirely",
        deprecated="'--no-ui' is deprecated and will be removed in the future. Use '--ui disabled'",
    )


class ParsedArgs(AliasModel):
    cli_only_args: CommandLineOnlyArgs = CommandLineOnlyArgs()  # type: ignore
    config_settings: ConfigSettings = ConfigSettings()
    deprecated_args: DeprecatedArgs = DeprecatedArgs()  # type: ignore
    global_settings: GlobalSettings = GlobalSettings()

    def model_post_init(self, _) -> None:
        exit_on_warning = False

        if self.cli_only_args.retry_all or self.cli_only_args.retry_maintenance:
            self.config_settings.runtime_options.ignore_history = True

        warnings_to_emit = self.prepare_warnings()

        if (
            not self.cli_only_args.fullscreen_ui
            or self.cli_only_args.retry_any
            or self.cli_only_args.config_file
            or self.config_settings.sorting.sort_downloads
        ):
            self.cli_only_args.download = True

        if warnings_to_emit:
            for msg in warnings_to_emit:
                warnings.warn(msg, DeprecationWarning, stacklevel=10)
            if exit_on_warning:
                sys.exit(1)
            time.sleep(WARNING_TIMEOUT)

    @staticmethod
    def parse_args() -> "ParsedArgs":
        """Parses the command line arguments passed into the program. Returns an instance of `ParsedArgs`"""
        return parse_args()

    def prepare_warnings(self) -> set[str]:
        warnings_to_emit = set()

        def add_warning_msg_from(field_name: str) -> None:
            if not field_name:
                return
            field_info: FieldInfo = self.deprecated_args.model_fields[field_name]
            warnings_to_emit.add(field_info.deprecated)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            if self.deprecated_args.no_ui:
                add_warning_msg_from("no_ui")
                self.cli_only_args.ui = UIOptions.DISABLED

        return warnings_to_emit


def _add_args_from_model(
    parser: ArgumentParser | ArgGroup, model: type[BaseModel], *, cli_args: bool = False, deprecated: bool = False
) -> None:
    for name, field in model.model_fields.items():
        cli_name = name.replace("_", "-")
        arg_type = type(field.default)
        if arg_type not in (list, set, bool):
            arg_type = str
        help_text = field.description or ""
        default = field.default if cli_args else SUPPRESS
        default_options = {"default": default, "dest": name, "help": help_text}
        name_or_flags = [f"--{cli_name}"]
        alias: str = field.alias or field.validation_alias or field.serialization_alias  # type: ignore
        if alias and len(alias) == 1:
            name_or_flags.insert(0, f"-{alias}")
        if arg_type is bool:
            action = BooleanOptionalAction
            default_options.pop("default")
            if cli_args and not (cli_name == "portrait" and env.RUNNING_IN_TERMUX):
                action = "store_false" if default else "store_true"
            if deprecated:
                default_options = default_options | {"default": SUPPRESS}
            parser.add_argument(*name_or_flags, action=action, **default_options)
            continue
        if cli_name == "links":
            default_options.pop("dest")
            parser.add_argument(cli_name, metavar="LINK(S)", nargs="*", action="extend", **default_options)
            continue
        if arg_type in (list, set):
            parser.add_argument(*name_or_flags, nargs="*", action="extend", **default_options)
            continue
        parser.add_argument(*name_or_flags, type=arg_type, **default_options)


def _create_groups_from_nested_models(parser: ArgumentParser, model: type[BaseModel]) -> list[ArgGroup]:
    groups: list[ArgGroup] = []
    for name, field in model.model_fields.items():
        submodel: type[BaseModel] = field.annotation  # type: ignore
        submodel_group = parser.add_argument_group(name)
        _add_args_from_model(submodel_group, submodel)
        groups.append(submodel_group)
    return groups


class CustomHelpFormatter(RawDescriptionHelpFormatter):
    def __init__(self, prog):
        witdh = 300 if env.RUNNING_IN_IDE else None
        super().__init__(prog, max_help_position=80, width=witdh)

    def _get_help_string(self, action):
        if action.help:
            return action.help.replace("program's", "CDL")  ## The ' messes up the markdown formatting
        return action.help

    def format_help(self):
        help_text = super().format_help()
        if env.RUNNING_IN_IDE and CLI_ARGUMENTS_MD.is_file():
            cli_overview, *_ = help_text.partition(CDL_EPILOG)
            current_text = CLI_ARGUMENTS_MD.read_text(encoding="utf8")
            new_text, *_ = current_text.partition("```shell")
            new_text += f"```shell\n{cli_overview}```\n"
            if current_text != new_text:
                CLI_ARGUMENTS_MD.write_text(new_text, encoding="utf8")
        return help_text


def parse_args() -> ParsedArgs:
    """Parses the command line arguments passed into the program."""
    parser = ArgumentParser(
        description="Bulk asynchronous downloader for multiple file hosts",
        usage="cyberdrop-dl [OPTIONS] URL [URL...]",
        epilog=CDL_EPILOG,
        formatter_class=CustomHelpFormatter,
    )
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")

    cli_only = parser.add_argument_group("CLI-only options")
    _add_args_from_model(cli_only, CommandLineOnlyArgs, cli_args=True)

    group_lists = {
        "config_settings": _create_groups_from_nested_models(parser, ConfigSettings),
        "global_settings": _create_groups_from_nested_models(parser, GlobalSettings),
        "cli_only_args": [cli_only],
    }

    using_deprecated_args: bool = bool(DeprecatedArgs.model_fields)
    if using_deprecated_args:
        deprecated = parser.add_argument_group("deprecated")
        _add_args_from_model(deprecated, DeprecatedArgs, cli_args=True, deprecated=True)
        group_lists["deprecated_args"] = [deprecated]

    args = parser.parse_intermixed_args()
    parsed_args: dict[str, dict] = {}
    for name, groups in group_lists.items():
        parsed_args[name] = {}
        for group in groups:
            group_dict = {
                arg.dest: getattr(args, arg.dest)
                for arg in group._group_actions
                if getattr(args, arg.dest, None) is not None
            }
            if group_dict:
                parsed_args[name][group.title] = group_dict

    if using_deprecated_args:
        parsed_args["deprecated_args"] = parsed_args["deprecated_args"].get("deprecated") or {}
    parsed_args["cli_only_args"] = parsed_args["cli_only_args"]["CLI-only options"]

    try:
        parsed_args_model = ParsedArgs.model_validate(parsed_args)

    except ValidationError as e:
        handle_validation_error(e, title="CLI arguments")
        sys.exit(1)
    return parsed_args_model
