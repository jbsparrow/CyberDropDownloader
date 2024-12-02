---
icon: sliders
description: Here's how configuration works.
---

# Configuration Options

{% hint style="info" %}
There is a lot of possible customization that you can do with the program, don't worry though. I'll try and make it as easy as possible for you.
{% endhint %}

A little note on how configs work in V5:

There are three type of config files in V5.

* settings
* global\_settings
* authentication\_settings

Global settings and authentication settings are "global". **They apply to all settings configs**. You can set them once and never touch them again.

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
**Global Settings** and **Authentication Settings** are "global". **They apply to all settings configs**. You can set them once and never touch them again.
{% endhint %}

Each settings config will be setup by default to have separate `URLs.txt` files and separate logs.

You can run all of the configs sequentially by selecting `ALL` from the UI or using `--config ALL`.
