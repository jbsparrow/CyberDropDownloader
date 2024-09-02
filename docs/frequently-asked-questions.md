---
description: Common questions or problems.
---

# Frequently Asked Questions

### What does this do? <a href="#what-does-this-do" id="what-does-this-do"></a>

This is a bulk downloader for the supported sites. It supports resumable downloading (you can close and reopen the program at any time and it will pick up where it left off), and keeps track of your download history to avoid downloading files you've already downloaded in the past.

### How do I update this? <a href="#how-do-i-update-this" id="how-do-i-update-this"></a>

If you are using one of the provided start files, it should do so automatically, if it doesn't open up terminal or command prompt and do the following:

`pip install --upgrade cyberdrop-dl-patched`

if you are on mac you may need to do the following:

`pip3 install --upgrade cyberdrop-dl-patched`

### Where is the Downloader.log file? <a href="#where-is-the-downloader.log-file" id="where-is-the-downloader.log-file"></a>

If you are running using one of the new start scripts it'll be in `./appdata/configs/<config>/logs/`

### What do the Scrape Failures and Download Failures mean? <a href="#what-do-the-scrape-failures-and-download-failures-mean" id="what-do-the-scrape-failures-and-download-failures-mean"></a>

Quite simply, almost all of them you see will be HTTP Status codes. Such as: 404 - Not Found (dead link)

You can google what the individual HTTP status' mean.

{% hint style="info" %}
Any "Unknown" error, is usually coding related, or it'll be something like the program not being able to find a file extension for a file.
{% endhint %}

### Why are all the files skipped? <a href="#why-are-all-the-files-skipped" id="why-are-all-the-files-skipped"></a>

By default Cyberdrop-DL keeps track of your download history and will skip all files that you've downloaded in the past to avoid duplicates. You can turn off the behavior by using the --ignore-history cli arg, or ignore\_history in the config.

### The screen is flickering? <a href="#the-screen-is-flickering" id="the-screen-is-flickering"></a>

You can likely blame Microsoft for this one and how ancient the traditional command prompt is. If you are windows 10 I highly suggest you install and use Windows Terminal to run Cyberdrop-DL. Terminal is the default on Windows 11.

### Cyberdrop-DL is not a recognized internal command <a href="#cyberdrop-dl-is-not-a-recognized-internal-command" id="cyberdrop-dl-is-not-a-recognized-internal-command"></a>

This is caused by an improper installation of python. Specifically python not being added to path.

I'd recommend you go back to the quick start guide and follow the steps it says to reinstall python.

{% content-ref url="quick-start/" %}
[quick-start](quick-start/)
{% endcontent-ref %}

### How do I scrape forum threads? <a href="#how-do-i-scrape-forum-threads" id="how-do-i-scrape-forum-threads"></a>

You need to provide Cyberdrop-DL with your credentials or user cookies in order to scrape forums.

You can do this in the UI by selecting 'Manage Configs' -> 'Edit Authentication Values'

Then you can select whether you want to extract cookies from your browser automatically, or provide the details yourself.

### Why are the filenames the way they are? <a href="#why-are-the-filenames-the-way-they-are" id="why-are-the-filenames-the-way-they-are"></a>

Filenames are taken from the website you are trying to download from. Blame whoever uploaded it.

### How do I fix \`\[SSL: CERTIFICATE\_VERIFY\_FAILED]\` <a href="#how-do-i-fix-ssl-certificate_verify_failed" id="how-do-i-fix-ssl-certificate_verify_failed"></a>

This should only appear on mac, so these instructions are for mac users.

Go to your applications folder, find the python folder inside of it. Run the `Install Certificates` file in that folder.

Go back to where you are running Cyberdrop-DL and delete the the `venv` folder if one exists (if not, don't worry). Then try running the program again.

### How do I go back to V4? <a href="#how-do-i-go-back-to-v4" id="how-do-i-go-back-to-v4"></a>

In the start file change the `pip install --upgrade cyberdrop-dl` line to read `pip install cyberdrop-dl==4.2.231` and run `pip uninstall cyberdrop-dl-patched` in order to remove the fixed version of V5.

{% hint style="info" %}
V4 will not receive any new updates. V5 is the only way forward.
{% endhint %}
