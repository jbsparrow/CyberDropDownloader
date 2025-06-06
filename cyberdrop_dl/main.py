import sys

from cyberdrop_dl import env


def main(*, profiling: bool = False, ask: bool = True) -> None:
    if not (profiling or env.PROFILING):
        return actual_main()
    from cyberdrop_dl.profiling import profile

    profile(actual_main, ask)


def actual_main() -> None:
    sys.exit(run())


def run(args: tuple[str, ...] | None = None) -> str | int:
    try:
        from cyberdrop_dl.director import Director

        director = Director(args)
        return director.run()
    except KeyboardInterrupt:
        return "\nKeyboardInterrupt"


if __name__ == "__main__":
    main()
