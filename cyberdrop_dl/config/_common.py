from typing import Any

from pydantic import Field as P_Field
from pydantic.fields import _Unset


def Field(default: Any, validation_alias: str = _Unset, **kwargs) -> Any:  # noqa: N802
    return P_Field(default=default, validation_alias=validation_alias, **kwargs)
