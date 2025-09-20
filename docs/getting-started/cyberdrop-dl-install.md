---
description:
icon: download
---

# Cyberdrop-DL Install

## Using Start Scripts (From Release Page)

This is the simplest method to get the program up and running. Pre-configured start files are provided that will automatically install python, install cyberdrop-dl, update, and launch the program for you.

{% hint style="info" %}
The start scripts only work on 64bits operating systems. If you are running a 32bit OS, you need to install direcly from pypi and may need to compile some dependencies
{% endhint %}

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

You can open the start script from the zip in a text editor like notepad. At the top of the file, you will this line:

```shell
set "COMMANDLINE_ARGS="
```

`COMMANDLINE_ARGS`:  Provide any arguments to pass to Cyberdrop-Dl. For more information, refer to the [CLI Arguments section](../reference/cli-arguments.md)

{% hint style="info" %}
You **MUST** put the values _inside_ the double quotes. Ex: `set "COMMANDLINE_ARGS=--disable-cache"`
{% endhint %}

</details>

## Manual Install

### Python Install

You'll need to have python installed to use Cyberdrop-DL. If you are on Linux or mac, you probably already do

If you don't have python, you can find and download it from their official website: [https://www.python.org/downloads/](https://www.python.org/downloads/)

{% hint style="warning" %}
Cyberdrop-DL requires python 3.11, 3.12 or python 3.13
{% endhint %}

{% hint style="warning" %}
If you are using a version of Cyberdrop-DL from the previous repository (`cyberdrop-dl` instead of `cyberdrop-dl-patched`), you **MUST** uninstall it before installing the patched version.

```shell
pip uninstall cyberdrop-dl
```

{% endhint %}

You can install cyberdrop-dl direcly from pypi using `uv`, `pipx` or `pip`. In a command prompt/terminal window:

{% tabs %}

{% tab title="uv" %}

```shell
uv install cyberdrop-dl-patched
```

{% endtab %}

{% tab title="pipx" %}

```shell
pipx install cyberdrop-dl-patched
```

{% endtab %}

{% tab title="pip" %}
{% hint style="warning" %}
Using `pip` to install `cyberdrop-dl-patched` is discouraged as it may lead to dependency conflicts with global installs and an inconsistent environment. Consider using `uv` or `pipx`
{% endhint %}

```shell
pip install cyberdrop-dl-patched
```

{% endtab %}
{% endtabs %}
