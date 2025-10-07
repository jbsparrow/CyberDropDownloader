import sys
from collections.abc import Sequence


def main(args: Sequence[str] | None = None) -> None:
    sys.exit(run(args))


def run(args: Sequence[str] | None = None) -> str | int | None:
    from cyberdrop_dl.utils.logger import catch_exceptions

    @catch_exceptions
    def run_() -> int:
        return _create_director(args).run()

    return run_()


def _create_director(args: Sequence[str] | None = None) -> Director:
    from cyberdrop_dl.director import Director

    return Director(args)


if __name__ == "__main__":
    main()
