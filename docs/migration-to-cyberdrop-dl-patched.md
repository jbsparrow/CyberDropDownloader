---
description: How to migrate to the patched version of Cyberdrop-DL.
icon: arrow-trend-up
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

# Move to Cyberdrop-DL-Patched

If you used the original version of the package (`cyberdrop-dl` instead of `cyberdrop-dl-patched`), you can follow the steps below to migrate.

{% hint style="warning" %}
You may need to adjust your config to make sure it's compatible with the newer versions.

See: [Transition to V8](https://script-ware.gitbook.io/cyberdrop-dl/upgrade)
{% endhint %}

## If you installed on your own using pip

You can simply uninstall the old version and install the new one using the following commands:

```shell
pip uninstall -y cyberdrop-dl
pip install cyberdrop-dl-patched
```

The command to use the new version will be `cyberdrop-dl-patched`.

## If you installed using the start files

You can find the new ones here: [new start scripts](https://github.com/jbsparrow/CyberDropDownloader/releases/latest)

Put the new start scripts on the same folder as the old ones, them delete the old ones.

You also have to delete any `venv` or `.venv` folder (if you have any)
