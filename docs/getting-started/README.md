---
description: Get off to the races.
icon: bullseye-arrow
layout:
  title:
    visible: true
  description:
    visible: true
  tableOfContents:
    visible: true
  outline:
    visible: false
  pagination:
    visible: true
---

# Getting Started

{% hint style="warning" %}
Cyberdrop-DL requires python 3.11, 3.12 or python 3.13
{% endhint %}

## Installing Python

Cyberdrop-DL is written in Python. You'll need Python installed on your system to be able to run it. If you're using Linux or macOS, Python is likely already included by default. However, if you're on Windows or need a different version, you can easily download and install Python from the official website

{% content-ref url="python-install/" %}
[python-install](python-install/)
{% endcontent-ref %}

## Installing Cyberdrop-DL</a>

There are two ways to install Cyberdrop-DL. The first is the easy method, where you simply download the start scripts. The second method involves using pip for installation, which is recommended for advanced users who prefer managing dependencies manually.

{% content-ref url="cyberdrop-dl-install.md" %}
[cyberdrop-dl-install.md](cyberdrop-dl-install.md)
{% endcontent-ref %}

## What now?</a>

If you downloaded the start scripts, just open the start script with the name of the OS you are using. For a manual install, execute the program with this command:

```shell
cyberdrop-dl
```

On the main screen, you can use the 'Edit URLs' option to add the URLs for the files you wish to download, them select the `download` option. That's it!

However, Cyberdrop-DL has a ton of configuration options if you want more control over the downloads. You may want to review the following:

{% content-ref url="../reference/configuration-options/" %}
[configuration-options](../reference/configuration-options/)
{% endcontent-ref %}

{% content-ref url="../reference/cli-arguments.md" %}
[cli-arguments.md](../reference/cli-arguments.md)
{% endcontent-ref %}

{% content-ref url="../reference/notifications.md" %}
[notifications.md](../reference/notifications.md)
{% endcontent-ref %}

By default, all config files are under the `AppData` folder, which is created on the same directory that CDL it run from.

You may also want to peek at what websites the program actually supports:

{% content-ref url="../reference/supported-websites.md" %}
[supported-websites.md](../reference/supported-websites.md)
{% endcontent-ref %}

If you have any issues, perhaps the [FAQ](../frequently-asked-questions.md) might help you!
