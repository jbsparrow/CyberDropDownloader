---
description: Here's the gist on how to handle python on Mac
---

# Python Install - Mac

Luckily for all of you mac users out there, it's quite simple!

Open up a terminal and type the following:

```
python3 --version
```

If you get a version number that's 3.11 or greater, you're already set!

If you get an error when typing that in, you can do the following.

Open up terminal again (or use the same window), and type the following:

```
export HOMEBREW_NO_INSTALL_FROM_API=1
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install.sh)"
```

The above command will install homebrew! Which is a very convenient tool for installing software on macs.

After that finishes, restart your computer, and open up a new terminal window. You can then run these commands and brew will do the heavy lifting.

```
brew install python3
```

```
brew link python3
```

After that (assuming no errors), you're set! You can continue with the quick start guide.
