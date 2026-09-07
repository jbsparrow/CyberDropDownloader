from __future__ import annotations

from typing import TYPE_CHECKING

from cyberdrop_dl.config import parse_tokens

if TYPE_CHECKING:
    from collections.abc import Sequence

    from rich.console import RenderableType
    from rich.panel import Panel


def _error_panel(message: RenderableType, title: str = "Error") -> Panel:
    # Based on the default cyclopts panel
    from rich import box
    from rich.panel import Panel

    return Panel(
        message,
        title=title,
        box=box.ROUNDED,
        border_style="red",
        expand=True,
        title_align="left",
    )


def run_cdl(args: Sequence[str] | None = None) -> int:
    from cyberdrop_dl import tracebacks
    from cyberdrop_dl.logs import setup_console_logging

    tracebacks.install_exception_hook()

    with setup_console_logging():
        from cyberdrop_dl.cli import app
        from cyberdrop_dl.exceptions import CDLConfigRuntimeErrorsGroup, DatabaseError

        try:
            app(parse_tokens(args))
        except DatabaseError as exc:
            tb = tracebacks.from_exception(exc.with_traceback(None))
            app.console.print(_error_panel(tb))
        except CDLConfigRuntimeErrorsGroup as exc_group:
            tb = tracebacks.from_exception(exc_group)
            app.console.print(_error_panel(tb, title=exc_group.message or "Invalid Config"))
        except ValueError as exc:
            from pydantic_core import ValidationError

            if not isinstance(exc, ValidationError):
                raise
            tb = tracebacks.from_exception(exc.with_traceback(None))
            app.console.print(_error_panel(tb))
        else:
            return 0

        return 1


def main(args: Sequence[str] | None = None) -> None:
    try:
        raise SystemExit(run_cdl(args))
    except KeyboardInterrupt:
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
