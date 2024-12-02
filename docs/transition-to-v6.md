---
description: This is the walk through for transitioning from V4 or V5 to V6
icon: arrow-up-to-bracket
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

# Transition from V4 or V5 to V6

Built into Cyberdrop-DL V6 is a tool that allows you to import both your configs and your history DB from previous versions.

{% hint style="danger" %}
V6 introduces some breaking changes, using a more strict config validation logic, replacing  `md5` with `xxh128` as the default hashing algorithm and using a new database schema. It's recommended to do a manual backup of your current AppData folder. You won't be able to rollback to a previous version after the transfer is completed.

You can learn more about the changes on the release announcement
{% endhint %}

{% hint style="info" %}
Even after a successful config migration, you may find that Cyberdrop-DL does not start because some of the values on your config from the previous version are no longer valid. Please follow the instructions Cyberdrop-DL will show on the screen to fix it.

You can use the Config Options page as reference for valid config values
{% endhint %}

#### Importing previous configs <a href="#importing-previous-configs" id="importing-previous-configs"></a>

This is pretty straight forward. The config will be located in the folder that you were previously running Cyberdrop-DL in.

{% hint style="info" %}
If you weren't using the config previously, you don't need to import it.

However, if you were primarily using CLI Arguments with V4, some of the arguments you will need to swap into configs.
{% endhint %}

If you don't end up using the import feature, make sure you also change the default config in the program if that's something you want to do.

#### Importing the old History DB <a href="#importing-the-old-history-db" id="importing-the-old-history-db"></a>

For a lot of people, the `download_history.sqlite` file will be in the same folder as your start file (or wherever you are running Cyberdrop-DL).

If it's not there, you can find it here:

Windows: `C:\Users\<USER>\AppData\Local\Cyberdrop-DL\Cyberdrop-DL\download_history.sqlite` Mac: `/Library/Application Support/Cyberdrop-DL/Cyberdrop-DL/download_history.sqlite` Linux: `/home/<USER>/.local/share/Cyberdrop-DL/Cyberdrop-DL/download_history.sqlite`

{% hint style="info" %}
The old `download_history.sqlite` file is no longer used by Cyberdrop-DL. After you import it, you can delete the old one.

If you don't want to import previous download history, you can just delete it.
{% endhint %}
