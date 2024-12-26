import sys
import time
import warnings
from argparse import SUPPRESS, ArgumentDefaultsHelpFormatter, ArgumentParser, BooleanOptionalAction
from argparse import _ArgumentGroup as ArgGroup
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Self

from pydantic import BaseModel, Field, ValidationError, computed_field, field_validator, model_validator

from cyberdrop_dl import __version__
from cyberdrop_dl.config_definitions import ConfigSettings, GlobalSettings
from cyberdrop_dl.config_definitions.custom_types import AliasModel, HttpURL
from cyberdrop_dl.utils.yaml import handle_validation_error

if TYPE_CHECKING:
    from pydantic.fields import FieldInfo


warnings.simplefilter("always", DeprecationWarning)
WARNING_TIMEOUT = 5  # seconds


def _check_mutually_exclusive(group: set, msg: str) -> None:
    if sum(1 for value in group if value) >= 2:
        raise ValueError(msg)


class CommandLineOnlyArgs(BaseModel):
    links: list[HttpURL] = Field([], description="link(s) to content to download (passing multiple links is supported)")
    appdata_folder: Path | None = Field(None, description="AppData folder path")
    completed_after: date | None = Field(None, description="only download completed downloads at or after this date")
    completed_before: date | None = Field(None, description="only download completed downloads at or before this date")
    config: str | None = Field(None, description="name of config to load")
    config_file: Path | None = Field(None, description="path to the CDL settings.yaml file to load")
    download: bool = Field(False, description="skips UI, start download inmediatly")
    max_items_retry: int = Field(0, description="max number of links to retry")
    no_ui: bool = Field(False, description="disables the UI/progress view entirely")
    retry_all: bool = Field(False, description="retry all downloads")
    retry_failed: bool = Field(False, description="retry failed downloads")
    retry_maintenance: bool = Field(
        False, description="retry download of maintenance files (bunkr). Requires files to be hashed"
    )

    @computed_field
    @property
    def retry_any(self) -> bool:
        return any((self.retry_all, self.retry_failed, self.retry_maintenance))

    @computed_field
    @property
    def multiconfig(self) -> bool:
        return self.config and self.config.casefold() == "all"

    @model_validator(mode="after")
    def mutually_exclusive(self) -> Self:
        group1 = {self.retry_all, self.retry_failed, self.retry_maintenance}
        msg1 = "'--retry-all', '--retry-maintenace' and '--retry-failed' are mutually exclusive"
        _check_mutually_exclusive(group1, msg1)
        group2 = {self.config, self.config_file}
        msg2 = "'--config' and '--config-file' are mutually exclusive"
        _check_mutually_exclusive(group2, msg2)
        return self


class DeprecatedArgs(BaseModel):
    output_folder: Path | None = Field(
        None,
        deprecated="'--output-folder' is deprecated and will be removed in the future. Use '--download-folder'",
    )
    download_all_configs: bool = Field(
        False,
        description="Skip the UI and go straight to downloading (runs all configs sequentially)",
        deprecated="'--download-all-configs' is deprecated and will be removed in the future. Use '--download --config all'",
    )
    sort_all_configs: bool = Field(
        False,
        description="Sort all configs sequentially",
        deprecated="'--sort-all-configs' is deprecated and will be removed in the future. Use '--sort-downloads --config all'",
    )
    sort_all_downloads: bool = Field(
        False,
        description="sort all downloads, not just those downloaded by Cyberdrop-DL",
        deprecated="'--sort-all-downloads' is deprecated.",
    )

    sort_cdl_only: bool = Field(
        False,
        description="only sort files downloaded by Cyberdrop-DL",
        deprecated="'--sort-cdl-only' is deprecated.",
    )

    main_log_filename: Path | None = Field(
        None,
        deprecated="'--main-log-filename' is deprecated and will be removed in the future. Use '--main-log'",
    )
    last_forum_post_filename: Path | None = Field(
        None,
        deprecated="'--last-forum-post-filename' is deprecated and will be removed in the future. Use '--last-forum-post'",
    )
    unsupported_urls_filename: Path | None = Field(
        None,
        deprecated="'--unsupported-urls-filename' is deprecated and will be removed in the future. Use '--unsupported-urls'",
    )
    download_error_urls_filename: Path | None = Field(
        None,
        deprecated="'--download-error-urls-filename' is deprecated and will be removed in the future. Use '--download-error-urls'",
    )
    scrape_error_urls_filename: Path | None = Field(
        None,
        deprecated="'--scrape-error-urls-filename' is deprecated and will be removed in the future. Use '--scrape-error-urls'",
    )

    @field_validator("main_log_filename", mode="after")
    @classmethod
    def fix_main_log_extension(cls, value: Path) -> Path:
        return value.with_suffix(".log")

    @field_validator(
        "last_forum_post_filename",
        "unsupported_urls_filename",
        "download_error_urls_filename",
        "scrape_error_urls_filename",
        mode="after",
    )
    @classmethod
    def fix_other_logs_extensions(cls, value: Path) -> Path:
        return value.with_suffix(".csv")


class ParsedArgs(AliasModel):
    cli_only_args: CommandLineOnlyArgs = CommandLineOnlyArgs()
    config_settings: ConfigSettings = ConfigSettings()
    deprecated_args: DeprecatedArgs = DeprecatedArgs()
    global_settings: GlobalSettings = GlobalSettings()

    def model_post_init(self, _) -> None:
        exit_on_warning = False
        logs_deprecated_names = [
            "main_log_filename",
            "last_forum_post_filename",
            "unsupported_urls_filename",
            "download_error_urls_filename",
            "scrape_error_urls_filename",
        ]

        if self.cli_only_args.retry_all or self.cli_only_args.retry_maintenance:
            self.config_settings.runtime_options.ignore_history = True

        warnings_to_emit = set()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)

            def add_warning_msg_from(field_name: str) -> None:
                field_info: FieldInfo = self.deprecated_args.model_fields[field_name]
                warnings_to_emit.add(field_info.deprecated)

            if self.deprecated_args.sort_all_configs:
                add_warning_msg_from("sort_all_configs")
                self.config_settings.sorting.sort_downloads = True
                self.cli_only_args.config = "ALL"

            if self.deprecated_args.output_folder:
                add_warning_msg_from("output_folder")
                self.config_settings.files.download_folder = self.deprecated_args.output_folder

            if self.deprecated_args.download_all_configs:
                add_warning_msg_from("download_all_configs")
                self.cli_only_args.download = True
                self.cli_only_args.config = "ALL"

            if self.deprecated_args.sort_all_downloads:
                add_warning_msg_from("sort_all_downloads")
                exit_on_warning = True

            if self.deprecated_args.sort_cdl_only:
                add_warning_msg_from("sort_cdl_only")
                exit_on_warning = True

            for deprecated_name in logs_deprecated_names:
                cli_value = getattr(self.deprecated_args, deprecated_name, None)
                if cli_value:
                    add_warning_msg_from(deprecated_name)
                    model_name = deprecated_name.replace("_filename", "")
                    setattr(self.config_settings.logs, model_name, cli_value)

        if (
            self.cli_only_args.no_ui
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
    def parse_args() -> Self:
        """Parses the command line arguments passed into the program. Returns an instance of `ParsedArgs`"""
        return parse_args()


def _add_args_from_model(
    parser: ArgumentParser, model: type[BaseModel], *, cli_args: bool = False, deprecated: bool = False
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
        alias = field.alias or field.validation_alias or field.serialization_alias
        if alias and len(alias) == 1:
            name_or_flags.insert(0, f"-{alias}")
        if arg_type is bool:
            action = BooleanOptionalAction
            default_options.pop("default")
            if cli_args:
                action = "store_false" if default else "store_true"
            if deprecated:
                default_options = default_options | {"default": SUPPRESS}
            parser.add_argument(*name_or_flags, action=action, **default_options)
            continue
        if cli_name == "links":
            default_options.pop("dest")
            parser.add_argument(cli_name, metavar="LINK(S)", nargs="*", **default_options)
            continue
        if arg_type in (list, set):
            parser.add_argument(*name_or_flags, nargs="*", **default_options)
            continue
        parser.add_argument(*name_or_flags, type=arg_type, **default_options)


def _create_groups_from_nested_models(parser: ArgumentParser, model: type[BaseModel]) -> list[ArgGroup]:
    groups: list[ArgGroup] = []
    for name, field in model.model_fields.items():
        submodel = field.annotation
        submodel_group = parser.add_argument_group(name)
        _add_args_from_model(submodel_group, submodel)
        groups.append(submodel_group)
    return groups


def parse_args() -> ParsedArgs:
    """Parses the command line arguments passed into the program."""
    parser = ArgumentParser(
        description="Bulk asynchronous downloader for multiple file hosts",
        usage="cyberdrop-dl [OPTIONS] URL [URL...]",
        epilog="Visit the wiki for additional details: https://script-ware.gitbook.io/cyberdrop-dl",
        formatter_class=ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")

    cli_only = parser.add_argument_group("CLI-only Options")
    _add_args_from_model(cli_only, CommandLineOnlyArgs, cli_args=True)

    group_lists = {
        "config_settings": _create_groups_from_nested_models(parser, ConfigSettings),
        "global_settings": _create_groups_from_nested_models(parser, GlobalSettings),
        "cli_only_args": [cli_only],
    }

    deprecated = parser.add_argument_group("Deprecated")
    _add_args_from_model(deprecated, DeprecatedArgs, cli_args=True, deprecated=True)
    group_lists["deprecated_args"] = [deprecated]

    args = parser.parse_args()
    parsed_args = {}
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

    parsed_args["deprecated_args"] = parsed_args["deprecated_args"].get("Deprecated") or {}
    parsed_args["cli_only_args"] = parsed_args["cli_only_args"]["CLI-only Options"]
    try:
        parsed_args = ParsedArgs.model_validate(parsed_args)

    except ValidationError as e:
        handle_validation_error(e, title="CLI arguments")
        sys.exit(1)
    return parsed_args
