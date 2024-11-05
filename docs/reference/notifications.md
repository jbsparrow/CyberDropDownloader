---
description: These are the options to setup notifications from CDL.
---

# Notifications

Cyberdrop-DL generates a report at the end of a run with stats about all the downloads, total runtime, errors, deduplication report, etc. By default, this report is only shown in the console and at the end of the main log file.

You can set up CDL to sent you the report via discord, email, a native notification of your OS, telegram and many other services.

## Notifications via Discord.

To get notifications via discord, you need to provide a discord `webhook_url` inside the `setting.yaml` of the config you are running.

You can learn how to setup a webhook following the [official discord guide](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks).

Optionally, you can add the tag `attach_logs=` as a prefix to your webhook url. This will tell CDL to include a copy of the main log as an attachment to Discord. 

## Notifications to other services (via Apprise)

Cyberdrop-DL uses [Apprise](https://github.com/caronc/apprise) to send notifications to any of the services than they support.

### How to setup Apprise

To send notifications via Apprise, you need to create an `apprise.txt` file inside `AppData/Configs/<config_name>`, where `<config_name>` if the config you want to use. The file must contain a list of URLs and they must be in the format of one of the supported apprise services.

You can check the full list of supported services [here](https://github.com/caronc/apprise/wiki) and the URL format than each one uses [here]( https://github.com/caronc/apprise?tab=readme-ov-file#supported-notifications).
 
Apprise services also support the `attach_logs=` tag to send the main log as an attachment.

### Troubleshooting Apprise notifications

Cyberdrop-DL will show you a message at the end of a run telling you if the apprise notifications were successfully sent or not. If you are having trouble getting notifications via Apprise, follow their [troubleshooting guide](https://github.com/caronc/apprise/wiki/Troubleshooting).


## Examples

To get notifications via email, use this URL format in your `apprise.txt` file: 

> mailto://user:password@domain.com

With the tag `attach_logs` it would look like this: 

> attach_logs=mailto://user:password@domain.com

Using `attach_logs` on the `webhook_url` config option: 

> attach_logs=https://discord.com/api/webhooks/webhook_id/webhook_token

