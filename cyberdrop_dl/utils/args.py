import sys
import time
import warnings
from argparse import SUPPRESS, ArgumentParser, BooleanOptionalAction, RawDescriptionHelpFormatter
from argparse import _ArgumentGroup as ArgGroup
from collections.abc import Iterable, Sequence
from datetime import date
from enum import StrEnum, auto
from pathlib import Path
from shutil import get_terminal_size
from typing import TYPE_CHECKING, Any, NoReturn, Self

from pydantic import BaseModel, Field, ValidationError, computed_field, field_validator, model_validator

from cyberdrop_dl import __version__, env
from cyberdrop_dl.config import ConfigSettings, GlobalSettings
from cyberdrop_dl.models import AliasModel
from cyberdrop_dl.models.types import HttpURL
from cyberdrop_dl.utils.yaml import handle_validation_error

if TYPE_CHECKING:
    from pydantic.fields import FieldInfo


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

    def check_terminal_size() -> bool:
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


class DeprecatedArgs(BaseModel): ...


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

    def prepare_warnings(self) -> set[str]:
        warnings_to_emit = set()

        def add_warning_msg_from(field_name: str) -> None:
            if not field_name:
                return
            field_info: FieldInfo = self.deprecated_args.model_fields[field_name]
            warnings_to_emit.add(field_info.deprecated)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            pass

        return warnings_to_emit


def _add_args_from_model(
    parser: ArgumentParser | ArgGroup,
    model: type[BaseModel],
    *,
    cli_args: bool = False,
    deprecated: bool = False,
    prefix: str = "",
) -> None:
    for name, field in model.model_fields.items():
        full_name = prefix + name
        cli_name = full_name.replace("_", "-")
        arg_type = type(field.default)
        if issubclass(arg_type, BaseModel):
            _add_args_from_model(parser, arg_type, cli_args=cli_args, deprecated=deprecated, prefix=f"{cli_name}.")
            continue
        if arg_type not in (list, set, bool):
            arg_type = str
        help_text = field.description or ""
        default = field.default if cli_args else SUPPRESS
        default_options = {"default": default, "dest": full_name, "help": help_text}
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
            _ = default_options.pop("dest")
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
    MAX_HELP_POS = 80
    INDENT_INCREMENT = 2

    def __init__(self, prog: str, width: int | None = None) -> None:
        super().__init__(prog, self.INDENT_INCREMENT, self.MAX_HELP_POS, width)

    def _get_help_string(self, action) -> str | None:
        if action.help:
            return action.help.replace("program's", "CDL")  # The ' messes up the markdown formatting
        return action.help


USING_DEPRECATED_ARGS: bool = bool(DeprecatedArgs.model_fields)


def make_parser() -> tuple[ArgumentParser, dict[str, list[ArgGroup]]]:
    parser = ArgumentParser(
        description="Bulk asynchronous downloader for multiple file hosts",
        usage="cyberdrop-dl [OPTIONS] URL [URL...]",
        epilog=CDL_EPILOG,
        formatter_class=CustomHelpFormatter,
    )
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")

    cli_only = parser.add_argument_group("CLI-only options")
    _add_args_from_model(cli_only, CommandLineOnlyArgs, cli_args=True)

    groups_mapping = {
        "config_settings": _create_groups_from_nested_models(parser, ConfigSettings),
        "global_settings": _create_groups_from_nested_models(parser, GlobalSettings),
        "cli_only_args": [cli_only],
    }

    if USING_DEPRECATED_ARGS:
        deprecated = parser.add_argument_group("deprecated")
        _add_args_from_model(deprecated, DeprecatedArgs, cli_args=True, deprecated=True)
        groups_mapping["deprecated_args"] = [deprecated]

    return parser, groups_mapping


def get_parsed_args_dict(args: Sequence[str] | None = None) -> dict[str, dict[str, Any]]:
    parser, groups_mapping = make_parser()
    namespace = parser.parse_intermixed_args(args)
    parsed_args: dict[str, dict[str, Any]] = {}
    for name, groups in groups_mapping.items():
        parsed_args[name] = {}
        for group in groups:
            group_dict = {
                arg.dest: getattr(namespace, arg.dest)
                for arg in group._group_actions
                if getattr(namespace, arg.dest, None) is not None
            }
            if group_dict:
                assert group.title
                parsed_args[name][group.title] = parse_nested_values(group_dict)

    if USING_DEPRECATED_ARGS:
        parsed_args["deprecated_args"] = parsed_args["deprecated_args"].get("deprecated") or {}
    parsed_args["cli_only_args"] = parsed_args["cli_only_args"]["CLI-only options"]
    return parsed_args


def parse_args(args: Sequence[str] | None = None) -> ParsedArgs:
    """Parses the command line arguments passed into the program."""
    parsed_args_dict = get_parsed_args_dict(args)
    try:
        parsed_args_model = ParsedArgs.model_validate(parsed_args_dict)

    except ValidationError as e:
        handle_validation_error(e, title="CLI arguments")
        sys.exit(1)

    if parsed_args_model.cli_only_args.show_supported_sites:
        show_supported_sites()

    return parsed_args_model


def show_supported_sites() -> NoReturn:
    from rich import print

    from cyberdrop_dl.utils.markdown import get_crawlers_info_as_rich_table

    table = get_crawlers_info_as_rich_table()
    print(table)
    sys.exit(0)


def parse_nested_values(data_list: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}

    for command_name, value in data_list.items():
        inner_names = command_name.split(".")
        current_level = result
        for index, key in enumerate(inner_names):
            if index < len(inner_names) - 1:
                if key not in current_level:
                    current_level[key] = {}
                current_level = current_level[key]
            else:
                current_level[key] = value
    return result
