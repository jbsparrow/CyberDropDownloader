---
description: Here's the gist on how to handle python on Windows
icon: windows
---

# Windows

Most new users will likely arrive at this page, and this guide is intended to help steer you in the right direction as you get started.

First, let's check if Python is installed on your system. You can do this by opening the command prompt and running the following command:

```shell
python --version
```

If the version number displayed is 3.11, 3.12 or 3.13, you're all set and can proceed with the rest of the setup guide!

If the version is lower than 3.11, the quickest and easiest solution is to uninstall the current version and install a compatible one. You can do this by searching for 'Uninstall Programs' on your machine, locating Python, and following the uninstallation process.

If you're unable to uninstall the current version due to dependencies with other software, follow the steps [mentioned here](https://github.com/jbsparrow/CyberDropDownloader/issues/248).

For those encountering an error or who have just uninstalled an older version of Python, don’t worry—installing the latest version is straightforward

But before proceeding, a few important notes:

- You don’t always want the latest version of Python. A very recent release may not be compatible with some dependencies. It's generally recommended to use the latest stable version that has been available for at least a few months.
- Installing a new version won't automatically update your existing one; it will install as a separate version, which can lead to potential conflicts.
- In most cases, there’s no need to manually update Python unless a specific version is required for your projects.

You can find and download the python installer here: [https://www.python.org/downloads/](https://www.python.org/downloads/)

{% hint style="warning" %}
Make sure to check the **'Add to PATH'** checkbox during installation—this is a crucial step. If you forget, you'll either need to uninstall and reinstall Python or manually add it to the PATH, which can be cumbersome.
{% endhint %}

Once the Python installation is complete, you can go ahead to [install Cyberdrop-DL](../cyberdrop-dl-install.md)
