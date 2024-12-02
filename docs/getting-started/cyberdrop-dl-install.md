---
description: This is the easiest method for getting Cyberdrop-DL going!
icon: download
---

# Cyberdrop-DL Install

I've created some start files that will automatically install, update and run Cyberdrop-DL

### Using start-script (from release page)

You can download them here: [https://github.com/jbsparrow/CyberDropDownloader/releases/latest](https://github.com/jbsparrow/CyberDropDownloader/releases/latest)

You'll want to download the `Cyberdrop-DL_<version>.zip` file, you don't need to worry about the rest of them.

Extract the contents of that folder to wherever you would like Cyberdrop-DL to run and download files to.

The contents will include a start file for Windows, macOS, and Linux.

If you are on Windows you can just open the start file, and it'll do the rest. Don't run it as admin.

If you're on Linux you should also just be able to open the start file.

In some very rare cases, Mac users may need to run this additional command first:

```shell
xcode-select --install
```

But you should also just be able to open the file and it'll handle the rest.

<details>

<summary>Running Cyberdrop-DL Script with Custom Parameters</summary>

You can open the start script from the zip. At the top of the file, you will find 3 variables:

```shell
set "PYTHON="
set "VENV_DIR="
set "COMMANDLINE_ARGS="
```

* **PYTHON**: You c[^1]an set a custom path for the python executable. This is useful if you have multiple python version installed an want to use an specific one

- **VENV_DIR**: Path of the folder were the python virtual environment will be created

* **COMMANDLINE_ARGS**: Arguments to pass to cyberdrop-dl. You can learn more about them in[cli-arguments.md](../reference/cli-arguments.md "mention")

</details>

## Manual Install

In a command prompt/terminal window:

```shell
pip install --upgrade cyberdrop-dl-patched
```

If you're on Mac/Linux, you may need to change it to be

```shell
pip3 install --upgrade cyberdrop-dl-patched
```

[^1]:
