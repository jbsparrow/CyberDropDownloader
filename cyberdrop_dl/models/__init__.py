"""Pydantic models"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar, Final, Self, TypedDict, final, get_args, get_origin, override

from cyclopts import Parameter
from pydantic import AnyUrl, BaseModel, Secret, SerializationInfo, TypeAdapter, model_serializer, model_validator
from pydantic.fields import FieldInfo  # noqa: TC002

from cyberdrop_dl import env
from cyberdrop_dl.constants import DEFAULT_PARAMETER
from cyberdrop_dl.utils import fast_cache, operators

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable

logger = logging.getLogger(__name__)


class DeferredModel(
    BaseModel,
    validate_by_name=True,
    validate_by_alias=True,
    defer_build=True,
    allow_inf_nan=False,
    url_preserve_empty_path=True,
    val_temporal_unit="milliseconds",
    validate_default=env.DEBUG_MODE,
    validation_error_cause=env.DEBUG_MODE,
): ...


_warned: set[tuple[type, str]] = set()


@DEFAULT_PARAMETER
class ConfigModel(DeferredModel, extra="forbid"):
    @override
    def model_post_init(self, context: Any, /) -> None:
        super().model_post_init(context)
        deprecated = self.model_fields_set.intersection(_deprecated_fields(self))
        if not deprecated:
            return

        import time

        for field in deprecated:
            warn_id = type(self), field
            if warn_id not in _warned:
                _warned.add(warn_id)
                logger.warning("'%s' config option is deprecated and will be removed in a future version", field)

        time.sleep(2)


def _deprecated_fields(model: BaseModel) -> list[str]:
    return [name for name, field in type(model).model_fields.items() if field.deprecated]


class ConfigGroup(ConfigModel):
    def __init_subclass__(cls, *, group: str | None = None, name: str | None = "*") -> None:
        _ = Parameter(group=group or cls.__name__, name=name)(cls)
        return super().__init_subclass__()


class _AppriseURLDict(TypedDict):
    url: str
    tags: set[str]


@Parameter(name="*")
class AppriseURL(ConfigModel):
    url: Secret[AnyUrl]
    tags: set[str] = set()

    _OS_SCHEMES: ClassVar[tuple[str, ...]] = "windows", "macosx", "dbus", "qt", "glib", "kde"
    _VALID_TAGS: ClassVar[set[str]] = {"no_logs", "attach_logs", "simplified"}

    @override
    def model_post_init(self, context: Any, /) -> None:
        super().model_post_init(context)
        if not self.tags.intersection(self._VALID_TAGS):
            self.tags |= {"no_logs"}

        if self.is_os_url:
            self.tags = (self.tags - self._VALID_TAGS) | {"simplified"}

    def __str__(self) -> str:
        return self.format(dump_secret=True)

    @property
    def scheme(self) -> str:
        return self.url.get_secret_value().scheme

    @property
    def is_os_url(self) -> bool:
        return any(scheme in self.scheme for scheme in self._OS_SCHEMES)

    @property
    def attach_logs(self) -> bool:
        return "attach_logs" in self.tags

    @model_serializer()
    def serialize(self, info: SerializationInfo) -> str:
        return self.format(dump_secret=info.mode != "json")

    def format(self, *, dump_secret: bool) -> str:
        url = str(self.url.get_secret_value() if dump_secret else self.url)
        if not self.tags:
            return url
        return f"{','.join(sorted(self.tags))}={url}"

    @model_validator(mode="before")
    @classmethod
    def _validate(cls, obj: object) -> _AppriseURLDict:
        match obj:
            case str():
                return cls._parse_url(obj)

            case dict():
                tags = obj.get("tags") or set()
                url = str(obj.get("url", ""))
                if not tags:
                    return cls._parse_url(url)

                return {"url": url, "tags": tags}

            case _:
                return {"url": str(obj), "tags": set()}

    @staticmethod
    def _parse_url(obj: str) -> _AppriseURLDict:
        match obj.split("://", 1)[0].split("=", 1):
            case [tags_, _scheme]:
                tags = set(tags_.split(","))
                url = obj.split("=", 1)[-1]
            case _:
                tags: set[str] = set()
                url: str = obj

        return {"url": url, "tags": tags}


def merge_dicts(
    dict1: dict[str, Any],
    dict2: dict[str, Any],
    additive_keys: Iterable[tuple[str, ...]] = (),
) -> dict[str, Any]:
    for keys in additive_keys:
        get = operators.nested_itemgetter(*keys)
        try:
            current_value, new_value = get(dict1), get(dict2)
        except KeyError:
            continue
        else:
            new_value = merge_additive_args(current_value, new_value)
            operators.nested_itemsetter(*keys)(dict2, new_value)

    return _merge_dicts(dict1, dict2)


def _merge_dicts(dict1: dict[str, Any], dict2: dict[str, Any]) -> dict[str, Any]:
    for key, val in dict1.items():
        if isinstance(val, dict):
            if key in dict2 and isinstance(dict2[key], dict):
                _merge_dicts(val, dict2[key])
        elif key in dict2:
            dict1[key] = dict2[key]

    for key, val in dict2.items():
        if key not in dict1:
            dict1[key] = val

    return dict1


def merge_models[M: BaseModel](
    default: M,
    new: M,
    additive_keys: Iterable[tuple[str, ...]] = (),
) -> M:
    current_data = default.model_dump()
    new_data = new.model_dump(exclude_unset=True)
    updated_dict = merge_dicts(current_data, new_data, additive_keys)
    return default.model_validate(updated_dict)


@fast_cache
def type_adapter[T](cls: type[T]) -> TypeAdapter[T]:
    """Get a type adapter for this class.

    Type adapters are cached. Multiple calls return the same adapter"""
    return TypeAdapter(cls)


def merge_additive_args[T: list[str] | tuple[str, ...] | set[str]](current_values: Iterable[str], overrides: T) -> T:
    if isinstance(overrides, set):
        if "+" in overrides:
            new_values = set(current_values).union(overrides)
        elif "-" in overrides:
            new_values = set(current_values) - set(overrides)
        else:
            return overrides
    else:
        match overrides:
            case ["+", *_]:
                new_values = set(current_values).union(overrides)
            case ["-", *_]:
                new_values = set(current_values) - set(overrides)
            case _:
                return overrides

    return type(overrides)(sorted(new_values - {"+", "-"}))


class FieldMetadata:
    IGNORE: Final = "<IGNORE>"

    def __init__(self, **data: Any) -> None:
        self.data: dict[str, Any] = data

    @override
    def __repr__(self) -> str:
        return f"{type(self).__name__}(data={self.data!r})"

    @classmethod
    def get(cls, field: FieldInfo) -> Self | None:
        if field.metadata:
            for data in field.metadata:
                if type(data) is cls:
                    return data

    @classmethod
    def _check(cls, field: FieldInfo) -> bool:
        return cls.get(field) is not None

    @classmethod
    def resolve(cls, model: BaseModel) -> Generator[tuple[str, ...]]:
        for name in cls._resolve(model):
            if cls.IGNORE not in name:
                yield tuple(name.split("."))

    @classmethod
    def _resolve(cls, model: BaseModel) -> Generator[str]:
        import warnings

        for name, field in type(model).model_fields.items():
            if cls._check(field):
                yield name
                continue

            with warnings.catch_warnings(action="ignore"):
                value = getattr(model, name)

            if isinstance(value, BaseModel):
                for inner_name in cls._resolve(value):
                    yield f"{name}.{inner_name}"


@final
class AdditiveArg(FieldMetadata):
    @override
    @classmethod
    def _check(cls, field: FieldInfo) -> bool:
        from cyclopts.annotations import resolve

        if get_origin(field.annotation) in {set, list, tuple}:
            arg = resolve(get_args(field.annotation)[0])
            all_args = get_args(arg) or [arg]
            if all(map(_is_str, all_args)):
                return True

        return super()._check(field)


def _is_str(type_: object) -> bool:
    from cyclopts.annotations import resolve

    type_ = resolve(type_)
    if type_ is str:
        return True
    try:
        return issubclass(type_, str)
    except Exception:  # noqa: BLE001
        try:
            return isinstance(type_, str)
        except Exception:  # noqa: BLE001
            return False
