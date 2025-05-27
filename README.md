<div align="center">

# `cyberdrop-dl-patched`
*Bulk asynchronous downloader for multiple file hosts*

[![PyPI - Version](https://img.shields.io/pypi/v/cyberdrop-dl-patched)](https://pypi.org/project/cyberdrop-dl-patched/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/cyberdrop-dl-patched)](https://pypi.org/project/cyberdrop-dl-patched/)
[![Docs](https://img.shields.io/badge/docs-wiki-blue?link=https%3A%2F%2Fscript-ware.gitbook.io%2Fcyberdrop-dl)](https://script-ware.gitbook.io/cyberdrop-dl)
[![GitHub License](https://img.shields.io/github/license/jbsparrow/CyberDropDownloader)](https://github.com/jbsparrow/CyberDropDownloader/blob/master/LICENSE)
[![linting - Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/jbsparrow/CyberDropDownloader/actions/workflows/ruff.yaml)
[![tests](https://github.com/jbsparrow/CyberDropDownloader/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/jbsparrow/CyberDropDownloader/actions/workflows/ci.yml)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/cyberdrop-dl-patched)](https://pypistats.org/packages/cyberdrop-dl-patched)

[![Discord](https://discordapp.com/api/guilds/1070206871564197908/widget.png?style=banner2)](https://discord.com/invite/P5nsbKErwy)


Brand new and improved! Cyberdrop-DL now has an updated paint job, fantastic new look. It's now easier to use than ever before!

![Cyberdrop-DL TUI Preview](https://raw.githubusercontent.com/jbsparrow/CyberDropDownloader/refs/heads/master/docs/assets/cyberdrop-dl_tui_preview.png)

</div>

## Supported Sites

See the [list of supported sites](https://script-ware.gitbook.io/cyberdrop-dl/reference/supported-websites) on the official wiki


## Getting Started

Follow the [getting-started guide](https://script-ware.gitbook.io/cyberdrop-dl/getting-started) for instructions on how to install and configure Cyberdrop-DL

## Docker

You can also build and run `cyberdrop-dl` using Docker.

### Building the Image

To build the Docker image, navigate to the root directory of the project (where the `Dockerfile` is located) and run:

```bash
docker build -t cyberdrop-dl .
```

### Running the Container

Once the image is built, you can run `cyberdrop-dl` in a container.
You'll likely want to mount volumes for configuration and downloads.

**Example:**

To run the container and mount a local directory `./data` to `/app/downloads` inside the container, and a local `./config` to `/app/config` for configuration persistence:

```bash
docker run -it --rm \
  -v ./data:/app/downloads \
  -v ./config:/app/config \
  cyberdrop-dl [cyberdrop-dl arguments]
```

Replace `[cyberdrop-dl arguments]` with any arguments you would normally pass to the `cyberdrop-dl` command-line tool.

For example, to download files from a URL and save them to the mounted `downloads` directory:
```bash
docker run -it --rm \
  -v ./data:/app/downloads \
  -v ./config:/app/config \
  cyberdrop-dl --url https://some-url.com/album
```

Refer to the [CLI arguments documentation](https://script-ware.gitbook.io/cyberdrop-dl/reference/cli-arguments) for available options.
The application inside the container will look for its configuration in `/app/config`. Make sure to place your `config.yml` (or other configuration files) in the local directory you mount to `/app/config`.

## Contributing
If there is a feature you want, you've discovered a bug, or if you have other general feedback, please create an issue for it!

See [CONTRIBUTING.md](https://github.com/jbsparrow/CyberDropDownloader/blob/master/CONTRIBUTING.md) for instructions on [opening an Issue](https://github.com/jbsparrow/CyberDropDownloader/blob/master/CONTRIBUTING.md#submitting-an-issue). If you want to submit code to the project, follow the [guidelines on how to contribute](https://github.com/jbsparrow/CyberDropDownloader/blob/master/CONTRIBUTING.md#submitting-a-pull-request-pr).
