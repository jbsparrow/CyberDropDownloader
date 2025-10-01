---
description: Common questions or problems.
icon: comments-question-check
layout:
  title:
    visible: true
  description:
    visible: true
  tableOfContents:
    visible: true
  pagination:
    visible: true
---

# Frequently Asked Questions

## What does this do?

This is a bulk downloader for the supported sites. It supports resumable downloading (you can close and reopen the program at any time and it will pick up where it left off), and keeps track of your download history to avoid downloading files you've already downloaded in the past.

## How do I update this?

If you are using one of the provided start files, it should do so automatically. Keep in mind that they will only update to the newest version within the same major version. ex: if you are using v8 start scripts, they will update to the latest v8 release. When v9 is out, you will need to download the new start scripts

## Why do i get `DDoS-Guard` error downloading from `x` site?

You may need to import cookies. Follow the instructions here: [How to extract cookies (DDoSGuard or login errors) #839](https://github.com/jbsparrow/CyberDropDownloader/discussions/839)

## I'm trying to report a bug and they ask me for a logs file. Where is this file?

By default, it'll be in `./AppData/configs/<config>/logs/`

The `AppData` folder is created inside the folder where you run cyberdrop-dl from

## What does `SCRAPE_FAILURES` and `DOWNLOAD_FAILURES` mean?

Quite simply, almost all of them you see will be HTTP Status codes. Such as: 404 - Not Found (dead link)

You check [this page to learn about what each error code means](https://developer.mozilla.org/en-US/docs/Web/HTTP/Status).

{% hint style="info" %}
Any "Unknown" error, is usually coding related, or it'll be something like the program not being able to find a file extension for a file.
You can report unknown error on the issue tracker: <https://github.com/jbsparrow/CyberDropDownloader/issues>
{% endhint %}

## Why are all the files skipped?

The program tracks your download history and will skip any files you've previously downloaded to avoid duplicates. You can disable this behavior by using the `--ignore-history` CLI argument or setting `ignore_history` to `true` in the config

## The screen is flickering?

This issue is likely related to the limitations of the traditional command prompt, which has remained largely unchanged over time. For Windows 10 users, it's recommended to install and use [Windows Terminal](https://aka.ms/terminal) to run Cyberdrop-DL. Windows Terminal is the default on Windows 11.

## `cyberdrop-dl` is not a recognized internal command

This issue is caused by an improper installation of Python, specifically Python not being added to the system PATH.

It is recommended to revisit the [Getting Started](getting-started/README.md) guide and follow the steps provided to reinstall or use one of the latest start scripts

## How do I scrape forum threads?

You need to import cookies to use as authentication for those sites. Follow the instructions here: [How to extract cookies (DDoSGuard or login errors) #839](https://github.com/jbsparrow/CyberDropDownloader/discussions/839)

## Why are the filenames the way they are?

Filenames are taken directly from the source website. Blame whoever uploaded it.

## How do I fix `[SSL: CERTIFICATE_VERIFY_FAILED]`?

This should only appear on macOS, so these instructions are for mac users.

Go to your applications folder, find the python folder inside of it. Run the `Install Certificates` file in that folder.

Go back to where you are running Cyberdrop-DL and delete the `venv` folder if one exists (if not, don't worry). Then try running the program again.

## A thread/site i follow has new posts but `cyberdrop-dl` is not detecting / downloading them, why?

`cyberdrop-dl` caches requests to made to sites to speed up re-runs and minimize load on those sites. By default, forums are cached for 30 days and any other site is cached for 7 days.

You can run with `--disable-cache` to temporarily disable the cache (CLI only) or change the default values to 0.

See:

[--forum-cache-expire-after](https://script-ware.gitbook.io/cyberdrop-dl/reference/configuration-options/global-settings/rate-limiting-options#forum_cache_expire_after)

[--file-host-cache-expire-after](https://script-ware.gitbook.io/cyberdrop-dl/reference/configuration-options/global-settings/rate-limiting-options#file_host_cache_expire_after)
