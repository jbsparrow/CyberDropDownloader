---
description:
icon: download
---

# Cyberdrop-DL Install

## Using Start Scripts (From Release Page)

This is the simplest method to get the program up and running. Pre-configured start files are provided that will automatically install, update, and launch the program for you.

You can download them here: [https://github.com/jbsparrow/CyberDropDownloader/releases/latest](https://github.com/jbsparrow/CyberDropDownloader/releases/latest)

You only need to download the `Cyberdrop-DL_<version>.zip` file, you don't need to worry about the other files.

Extract the contents of the zip file to any location where you'd like the program to run and store downloaded files. The extracted files will include a start file for Windows, macOS, and Linux

If you're using Windows or Linux, simply open the start file, and it will handle the rest for you

{% hint style="info" %}
If you are using Windows, **DO NOT** run the script as admin
{% endhint %}

On macOS, you should be able to open the start file and have everything set up automatically. However, in some rare cases, macOS users may need to run the following command first::

```shell
xcode-select --install
```

<details>

<summary>Optional: Running Cyberdrop-DL Script with Custom Parameters</summary>

You can open the start script from the zip in a text editor like notepad. At the top of the file, you will find 3 variables:

```shell
set "PYTHON="
set "VENV_DIR="
set "COMMANDLINE_ARGS="
```

`PYTHON`: Specify a custom path to the Python executable. This is useful if you have multiple Python versions installed and want to select a specific one

`VENV_DIR`: Define the path where the Python virtual environment will be created

`COMMANDLINE_ARGS`:  Provide any arguments to pass to Cyberdrop-Dl. For more information, refer to the [CLI Arguments section](../reference/cli-arguments.md)

{% hint style="info" %}
You **MUST** put the values _inside_ the double quotes. Ex: `set "PYTHON=C:\Program Files\Python311\python.exe"`
{% endhint %}

</details>

## Manual Install

{% hint style="warning" %}
If you are using a version of Cyberdrop-DL from the previous repository, you **MUST** uninstall it before installing the patched version.

```shell
pip uninstall cyberdrop-dl
```

{% endhint %}

In a command prompt/terminal window:

```shell
pip install --upgrade cyberdrop-dl-patched
```

If you're on Mac/Linux, you may need to change it to be

```shell
pip3 install --upgrade cyberdrop-dl-patched
```
