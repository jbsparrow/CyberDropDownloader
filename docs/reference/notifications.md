---
icon: envelope-open-text
description: These are the options to setup notifications from CDL.
---

# Notifications

Cyberdrop-DL generates a report at the end of a run with stats about all the downloads, total runtime, errors, deduplication report, etc. By default, this report is only shown in the console and at the end of the main log file.

You can set up CDL to sent you the report via discord, email, a native notification of your OS, telegram and many other services.

## Notifications via Discord

To get notifications via discord, you need to provide a discord `webhook_url` inside the `setting.yaml` of the config you are running.

You can learn how to setup a webhook following the [official discord guide](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks).

Optionally, you can add the tag `attach_logs=` as a prefix to your webhook url. This will tell CDL to include a copy of the main log as an attachment to Discord.

## Notifications to other services (via Apprise)

Cyberdrop-DL uses [Apprise](https://github.com/caronc/apprise) to send notifications to any of the services than they support.

### How to setup Apprise

To send notifications via Apprise, you need to create an `apprise.txt` file inside `AppData/Configs/<config_name>`, where `<config_name>` if the config you want to use. The file must contain a list of URLs and they must be in the format of one of the supported apprise services.

You can check the full list of supported services [here](https://github.com/caronc/apprise/wiki) and the URL format than each one uses [here](https://github.com/caronc/apprise?tab=readme-ov-file#supported-notifications).

Apprise services also support the `attach_logs=` tag to send the main log as an attachment.

### Troubleshooting Apprise notifications

Cyberdrop-DL will show you a message at the end of a run telling you if the apprise notifications were successfully sent or not. If you are having trouble getting notifications via Apprise, follow their [troubleshooting guide](https://github.com/caronc/apprise/wiki/Troubleshooting).

{% hint style="info" %}
When running on Windows, Cyberdrop-DL will setup OS notifications by default.

You can disable them by deleting the `windows://` line from the default `apprise.txt` file. You can also completely delete the file if you don't have any other notification setup.
{% endhint %}

## Examples

{% tabs %}
{% tab title="Email" %}
To get notifications via email, use this URL format in your `apprise.txt` file:

```shell
mailto://user:password@domain.com
```

{% endtab %}

{% tab title="Email + Logs" %}
Add `attach_logs` to your email URL in your `apprise.txt` file:

```shell
attach_logs=mailto://user:password@domain.com
```

{% endtab %}

{% tab title="Native OS notifications" %}
Some operating systems require additional dependencies for notifications to work. Cyberdrop-DL includes the required dependencies for Windows. Follow the url on the OS name to get additional information on how to set them up.

| OS | Syntax|
| ---- | --- |
|[Linux (DBus Notifications)](https://github.com/caronc/apprise/wiki/Notify_dbus) | `dbus://` <br> `qt://` <br> `glib://` <br> `kde://`|
|[Linux (Gnome Notifications)](https://github.com/caronc/apprise/wiki/Notify_gnome) | `gnome://` |
|[macOS](https://github.com/caronc/apprise/wiki/Notify_macosx)  | `macosx://`   |
|[Windows](https://github.com/caronc/apprise/wiki/Notify_windows)| `windows://` |

{% endtab %}

{% tab title="Discord + Logs" %}
Add `attach_logs` to the `webhook_url` config option:

```shell
attach_logs=https://discord.com/api/webhooks/webhook_id/webhook_token
```

{% endtab %}
{% endtabs %}
