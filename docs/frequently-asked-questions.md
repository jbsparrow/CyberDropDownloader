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
  outline:
    visible: false
  pagination:
    visible: true
---

# Frequently Asked Questions

<details>
<summary>What does this do?</summary>
This is a bulk downloader for the supported sites. It supports resumable downloading (you can close and reopen the program at any time and it will pick up where it left off), and keeps track of your download history to avoid downloading files you've already downloaded in the past.

</details>


<details>
<summary>How do I update this?</summary>

If you are using one of the provided start files, it should do so automatically, if it doesn't open up terminal or command prompt and do the following:

```shell
pip install --upgrade cyberdrop-dl-patched
```

if you are on macOS you may need to do the following:

```shell
pip3 install --upgrade cyberdrop-dl-patched
```

</details>
<details>
<summary> Why do i get DDoS-Guard Error downloading from <X> sites? </summary>

You may need to import cookies. Follow the instructions here: [How to extract cookies (DDoSGuard or login errors) #839](https://github.com/jbsparrow/CyberDropDownloader/discussions/839)

</details>

<details>

<summary> Where is the downloader.log file? </summary>

If you are running using one of the new start scripts it'll be in `./AppData/configs/<config>/logs/`

</details>

<details>
<summary> What does SCRAPE_FAILURES and DOWNLOAD_FAILURES mean? </summary>

Quite simply, almost all of them you see will be HTTP Status codes. Such as: 404 - Not Found (dead link)

You check [this page to learn about what each error code means](https://developer.mozilla.org/en-US/docs/Web/HTTP/Status).

{% hint style="info" %}
Any "Unknown" error, is usually coding related, or it'll be something like the program not being able to find a file extension for a file.
{% endhint %}

</details>

<details>
<summary> Why are all the files skipped? </summary>

By default, the program tracks your download history and will skip any files you've previously downloaded to avoid duplicates. You can disable this behavior by using the `--ignore-history` CLI argument or setting `ignore_history` to `true` in the config

</details>

<details>
<summary> The screen is flickering? </summary>

This issue is likely related to the limitations of the traditional command prompt, which has remained largely unchanged over time. For Windows 10 users, it's recommended to install and use [Windows Terminal](https://aka.ms/terminal) to run Cyberdrop-DL. Windows Terminal is the default on Windows 11.

</details>

<details>
<summary> cyberdrop-dl is not a recognized internal command </summary>

This issue is caused by an improper installation of Python, specifically Python not being added to the system PATH.

It is recommended to revisit the [Getting Started](getting-started/README.md) guide and follow the steps provided to reinstall Python correctly

</details>

<details>
<summary>  How do I scrape forum threads? </summary>

You need to provide Cyberdrop-DL with your credentials or user cookies in order to scrape forums.

You can do this in the UI by selecting `Manage Configs` -> `Edit Authentication Config`

Then you can select whether you want to extract cookies from your browser automatically, or provide the details yourself.

</details>

<details>
<summary> Why are the filenames the way they are? </summary>

Filenames are taken directly from the source website. Blame whoever uploaded it.

</details>

<details>
<summary> How do I fix [SSL: CERTIFICATE_VERIFY_FAILED]? </summary>

This should only appear on macOS, so these instructions are for mac users.

Go to your applications folder, find the python folder inside of it. Run the `Install Certificates` file in that folder.

Go back to where you are running Cyberdrop-DL and delete the the `venv` folder if one exists (if not, don't worry). Then try running the program again.

</details>

<details>
<summary> How do I go back to V5? </summary>

In the start file change the `pip install --upgrade cyberdrop-dl...` line to `pip install cyberdrop-dl=<6.0`.

You also need to run `pip uninstall cyberdrop-dl-patched` in order to remove any current version.

{% hint style="info" %}
Version 5 will no longer receive updates. Version 6 is the only supported version moving forward.
{% endhint %}

</details>
