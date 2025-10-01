---
description: >-
  Due to the recent DDOS attacks on SimpCity, I have made some changes to
  Cyberdrop-DL.
icon: building-circle-xmark
---

# SimpCity Support Dropped

## Removal of SimpCity Scraping Support

Support for scraping SimpCity has been removed temporarily. This may be disappointing to some users, but the explanation provided should clarify the reasoning behind this decision. Following the recent DDOS attacks, SimpCity has implemented the following security measures to protect their website:

* SimpCity has implemented a DDOS-Guard browser check.
* Access is now restricted to [whitelisted email domains](https://simpcity.su/threads/emails-august-2024.365869/).
* [New rate limits](https://simpcity.su/threads/rate-limit-429-error.397746/) have been introduced to protect the site.

## Why Scraping SimpCity Has Been Disabled

Cyberdrop-DL allows users to scrape a model’s entire thread quickly, downloading large amounts of content. While convenient, this has created several issues:

* Large-scale scraping can result in downloading content you may never view.
* Such scraping puts additional load on their servers, particularly during DDOS attacks.
* Scraping provides no direct benefit to SimpCity, and in light of these attacks, they have chosen not to support automated scraping.

For these reasons, SimpCity has removed the Cyberdrop-DL thread, and scraping for their site has been disabled in order to reduce the strain on their servers.

## How to Reduce the Impact of Cyberdrop-DL Usage

To help reduce the load on other websites, the `update_last_forum_post` setting has been enabled by default in all users' configs. This setting speeds up scrapes by picking up where the last session left off, rather than re-scraping entire threads.

You can disable this setting if you prefer, but it is strongly discouraged.

In addition, the default rate-limiting settings have been adjusted to further reduce the impact on websites.

## Usage Best Practices

I encourage you to use the program responsibly. Here are some tips to help minimize the impact on websites:

* Avoid running multiple scraping sessions repeatedly in a short span of time.
* Regularly clean up your URLs file by removing links you no longer need, and reducing how often you run the program.
* Be selective with what you download. It’s helpful to quickly scan content to avoid downloading files you'll delete later.

## Alternatives to Scraping SimpCity

If you wish to continue downloading from SimpCity, you can use Tampermonkey scripts like these ones:

* [SimpCity Tampermonkey Forum Downloader](https://simpcity.su/threads/forum-post-downloader-tampermonkey-script.96714/).
* [Forums Link Grabber](https://github.com/Garcarius/forumslinkgraber)
