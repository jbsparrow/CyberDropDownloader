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

# Migration to Cyberdrop-DL-Patched

To migrate to the patched version of Cyberdrop-DL, you can follow the steps below.

## If you installed on your own using pip,

You can simply uninstall the old version and install the new one using the following commands:

```shell
pip uninstall -y cyberdrop-dl
pip install cyberdrop-dl-patched
```

The command to use the new version will remain as `cyberdrop-dl`.

## If you installed using the start files

You can find the new ones here: [new start scripts](https://github.com/jbsparrow/CyberDropDownloader/releases/latest)

Put the new start scripts on the same folder as the old ones, them delete the old ones.

You also have to delete any `venv` or `.venv` folder (if you have any)

If you have custom start files, you can follow the commands for the pip installation to uninstall the old package and install the new one. Then update your start files to install `cyberdrop-dl-patched` instead of `cyberdrop-dl`.
