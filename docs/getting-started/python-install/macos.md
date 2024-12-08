---
description: Here's the gist on how to handle python on Mac
icon: apple
---

# macOS

Fortunately, for macOS users, it's quite straightforward!

Simply open a terminal and enter the following command:

```shell
python3 --version
```

If the version number is 3.11 or 3.12, you're all set!

If you encounter an error when running the command, try the following:

Open a terminal (or use the same window) and enter the following command:

```shell
export HOMEBREW_NO_INSTALL_FROM_API=1
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install.sh)"
```

The above command will install [homebrew](https://brew.sh/), a useful package manager that makes it easy to install and manage software on macOS.

Once the installation is complete, restart your computer and open a new terminal window. You can then run the following commands, and Homebrew will handle the installation for you.

```shell
brew install python3
brew link python3
```

Once the Python installation is complete, you can go ahead to [install Cyberdrop-DL](../cyberdrop-dl-install.md)
