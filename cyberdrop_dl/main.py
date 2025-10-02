import sys
import warnings
from collections.abc import Sequence

from cyberdrop_dl.director import Director


def main(args: Sequence[str] | None = None) -> None:
    sys.exit(run(args))


def run(args: Sequence[str] | None = None) -> str | int | None:
    from cyberdrop_dl.utils.logger import catch_exceptions

    @catch_exceptions
    def run_() -> int:
        return _create_director(args).run()

    return run_()


def _create_director(args: Sequence[str] | None = None) -> Director:
    warnings.filterwarnings("ignore", category=SyntaxWarning, message="invalid escape sequence.*")
    from cyberdrop_dl.director import Director

    return Director(args)


if __name__ == "__main__":
    main()
