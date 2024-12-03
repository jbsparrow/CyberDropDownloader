---
icon: sliders
description: Here's how configuration works.
---

# Configuration Options

There are three type of config files: config settings, global settings and authentication settings.

{% content-ref url="authentication.md" %}
[authentication.md](authentication.md)
{% endcontent-ref %}

{% content-ref url="global-settings/" %}
[global-settings/](global-settings/)
{% endcontent-ref %}

{% content-ref url="settings/" %}
[settings](settings/)
{% endcontent-ref %}

{% hint style="info" %}
**Global Settings** and **Authentication Settings** are "global". They apply to **ALL** Config Settings. You can set them once and never touch them again.
{% endhint %}

Each config setting will be setup by default to have a separate `URLs.txt` files and separate log files.

You can run all of the configs sequentially by selecting `ALL` from the UI or using `--config ALL`.
