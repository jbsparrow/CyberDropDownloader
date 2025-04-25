import sys

from cyberdrop_dl import env


def main(*, profiling: bool = False, ask: bool = True):
    if not (profiling or env.PROFILING):
        return run()
    from cyberdrop_dl.profiling import profile

    profile(run, ask)


def run() -> None:
    try:
        from cyberdrop_dl.director import Director

        director = Director()
        sys.exit(director.run())
    except KeyboardInterrupt:
        sys.exit("\nKeyboardInterrupt")


if __name__ == "__main__":
    main()
