from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal, final

from cyclopts import App, Parameter
from cyclopts.bind import normalize_tokens
from pydantic.fields import Field
from pydantic.functional_validators import AfterValidator
from pydantic.main import BaseModel
from pydantic.types import NonNegativeInt, PositiveInt  # noqa: TC002

from cyberdrop_dl.config.appdata import AppData
from cyberdrop_dl.constants import DEFAULT_PARAMETER
from cyberdrop_dl.exceptions import CDLConfigRuntimeErrorsGroup, InvalidYamlError
from cyberdrop_dl.models import AdditiveArg, ConfigModel, merge_dicts, merge_models
from cyberdrop_dl.models.types import ByteSizeSerilized  # noqa: TC001
from cyberdrop_dl.models.validators import remove_duplicates, to_bytesize
from cyberdrop_dl.utils import cleanup

from .auth import Authentication, Notifications
from .crawlers import Crawlers
from .filters import Filters
from .settings import ALIASES, Downloads, Hashing, Jdownloader, Logs, MaxChildren, Network, Sort, SubFolders, UIOptions

if TYPE_CHECKING:
    from collections.abc import Iterable


MIN_REQUIRED_FREE_SPACE = to_bytesize("512MiB")
MODULE_PATH = Path(__file__).parent
logger = logging.getLogger(__name__)
_app: App | None = None


@final
class Files:
    DEFAULT: Path = MODULE_PATH / "default.yaml"
    SCHEMA: Path = MODULE_PATH / "schema.json"

    @staticmethod
    def update() -> None:
        import json

        Files.SCHEMA.write_text(json.dumps(Config.model_json_schema(), indent=2, ensure_ascii=False))
        Config().save_to(Files.DEFAULT)


_ADDITIVE_ARGS: tuple[tuple[str, ...], ...] | None = None


@Parameter(name="*")
class Config(ConfigModel, title="cyberdrop-dl config"):
    __final__: Literal[True] = True

    auth: Authentication = Field(default_factory=Authentication)
    cookies: Path | None = None
    "File/folder to import cookies from (.txt Netscape files)"

    crawlers: Crawlers = Field(default_factory=Crawlers)
    deep_scrape: bool = False
    "Make additional requests while scraping (slower)"

    delete_empty_folders: bool = True
    "Delete empty files and folders after a run"

    delete_partial_files: bool = False
    "Delete partial files after a run"

    download_folder: Annotated[Path, Parameter(alias=("--output", "-o", "-d"))] = Path("downloads/cyberdrop-dl")
    "Base output path for all downloads"

    downloads: Downloads = Field(default_factory=Downloads)
    dump_json: Annotated[bool, Parameter(alias="-j")] = False
    "Save details about each file (both skipped and downloaded) to a .jsonl file"

    filters: Filters = Field(default_factory=Filters)
    hashing: Hashing = Field(default_factory=Hashing)
    ignore_history: bool = False
    "Download files even if the already are marked as downloaded on the database"

    ignore_hashes: bool = False
    "Download files even if their hash matches a file downloaded on the database"

    jdownloader: Jdownloader = Field(default_factory=Jdownloader)
    logs: Logs = Field(default_factory=Logs)
    max_children: MaxChildren = Field(default_factory=MaxChildren)
    "Limit the number of items to scrape per category"

    max_file_name_length: PositiveInt = 95
    "Max number of characters a filename should have. Filenames longer that this will be truncated"

    max_folder_name_length: PositiveInt = 60
    "Max number of characters a folder should have. Filenames longer that this will be truncated"

    max_thread_depth: NonNegativeInt = 0
    "Restricts how many levels of nested threads are scraped on a forum"

    max_thread_folder_depth: NonNegativeInt | None = None
    "Max number of nested folders CDL will create when maximum_thread_depth is greater that 0"

    min_free_space: Annotated[ByteSizeSerilized, AfterValidator(lambda x: max(x, MIN_REQUIRED_FREE_SPACE))] = (
        to_bytesize("5GiB")
    )
    "Minimum free space require to start new downloads"

    mtime: bool = True
    "Use original upload date as modification date for downloaded file"

    network: Network = Field(default_factory=Network)
    notifications: Notifications = Field(default_factory=Notifications)

    restrict_path: Annotated[
        tuple[Literal["unix", "windows", "no_emoji", "ascii"], ...],
        AfterValidator(remove_duplicates),
        Parameter(alias="restrict-filenames"),
    ] = ()
    sort: Sort = Field(default_factory=Sort)
    subfolders: SubFolders = Field(default_factory=SubFolders)
    ui: UIOptions = Field(default_factory=UIOptions)

    _resolved: bool = False
    _sources: tuple[Path, ...] = ()

    def __repr_args__(self) -> list[tuple[str, tuple[Path, ...]]]:
        return [("source", self._sources)]

    @property
    def source(self) -> Path | None:
        return self._sources[0] if self._sources else None

    def dump_yaml(self) -> str:
        import yaml

        return yaml.safe_dump(self.model_dump(mode="json"), default_flow_style=False)

    def save_to(self, file: Path) -> None:
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(self.dump_yaml(), encoding="utf8")

    @staticmethod
    def load(data: dict[str, Any]) -> Config:
        return Config.model_validate(data, by_alias=True, by_name=True)

    @staticmethod
    def from_file(file: Path) -> Config:
        return Config.from_files(file, file.with_suffix(f".override{file.suffix}"))

    @staticmethod
    def from_files(file: Path, *overrides: Path) -> Config:
        try:
            data = _load_yaml(file)
        except FileNotFoundError:
            sources = []
            data = {}

        else:
            sources = [file]
            for override in overrides:
                if override.is_file():
                    logger.info("Found config override '%s'", override)
                    sources.append(override)
                    data = merge_dicts(data, _load_yaml(override))

        config = Config.load(data)
        config._sources = tuple(sources)
        return config

    @staticmethod
    def parse_args(tokens: str | Iterable[str]) -> Config:
        global _app  # noqa: PLW0603
        if _app is None:
            _app = App(print_error=False, exit_on_error=False, default_parameter=DEFAULT_PARAMETER)
            _ = _app.command(name="coerce")(_coerce)
        fn, bound, *_ = _app.parse_args(["coerce", *parse_tokens(tokens)])
        assert fn is _coerce
        return _coerce(*bound.args, **bound.kwargs)

    def resolve_paths(self) -> None:
        if self._resolved:
            return

        default_log_folder = AppData.default().logs_folder
        self.logs.resolve_filenames(default_log_folder)
        _resolve_paths(self)
        if self.logs.expire_after:
            self.logs.delete_old_logs_and_folders()
            cleanup.rm_empty_dirs(self.logs.effective_log_folder)
        self._resolved = True

    def _additive_args(self) -> tuple[tuple[str, ...], ...]:
        global _ADDITIVE_ARGS  # noqa: PLW0603
        if _ADDITIVE_ARGS is None:
            _ADDITIVE_ARGS = tuple(sorted(AdditiveArg.resolve(self)))  # pyright: ignore[reportConstantRedefinition]
        return _ADDITIVE_ARGS

    def __or__(self, other: Config) -> Config:
        if not isinstance(other, Config):
            return NotImplemented

        me = merge_models(self, other, self._additive_args())
        me._sources = self._sources
        me.logs._created_at = self.logs._created_at
        return me


def _load_yaml(file: Path) -> dict[str, Any]:
    import yaml

    try:
        return yaml.safe_load(file.read_text()) or {}
    except yaml.YAMLError as e:
        raise CDLConfigRuntimeErrorsGroup("Invalid YAML file", (InvalidYamlError(file, e),)) from None


def parse_tokens(tokens: Iterable[str] | str | None) -> list[str]:
    return [ALIASES.get(token, token) for token in normalize_tokens(tokens)]


def _resolve_paths(model: BaseModel) -> None:
    for field_name, field_value in model:
        if isinstance(field_value, Path):
            if "{config}" in str(field_value):
                error = ValueError(
                    f"Using '{{config}}' as reference on a path is no longer supported: {field_value} ({field_name})"
                )
                raise CDLConfigRuntimeErrorsGroup("Invalid config", (error,))

            object.__setattr__(model, field_name, field_value.expanduser().resolve().absolute())

        elif isinstance(field_value, BaseModel):
            _resolve_paths(field_value)


def _coerce(*, config: Config | None = None) -> Config:
    if config is None:
        return Config()
    return config


__all__ = ["Config", "Files"]
