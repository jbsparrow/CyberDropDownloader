---
description: >-
  Due to the recent DDOS attacks on SimpCity, I have made some changes to
  Cyberdrop-DL.
---

# SimpCity Support Dropped

### Removal of SimpCity Scraping Support

Support for scraping SimpCity has been removed temporarily. I understand this may disappoint some users, but hopefully after reading this, you will understand why I made this decision. Following the recent DDOS attacks, SimpCity has implemented the following security measures to protect their website:

* SimpCity has implemented a DDOS-Guard browser check.
* Access is now restricted to [whitelisted email domains](https://simpcity.su/threads/emails-august-2024.365869/).
* [New rate limits](https://simpcity.su/threads/rate-limit-429-error.397746/) have been introduced to protect the site.

### Why Scraping SimpCity Has Been Disabled

Cyberdrop-DL allows users to scrape a model’s entire thread quickly, downloading large amounts of content. While convenient, this has created several issues:

* Large-scale scraping can result in downloading content you may never view.
* Such scraping puts a significant strain on SimpCity’s servers, particularly during DDOS attacks.
* Scraping provides no direct benefit to SimpCity, and in light of these attacks, they have chosen not to support automated scraping.

For these reasons, ~~SimpCity has removed the Cyberdrop-DL thread~~, and I have disabled scraping for their site in order to reduce the strain on their servers.

The Cyberdrop-DL thread has been reinstated following the release of [Cyberdrop-DL version 5.6.30](https://pypi.org/project/cyberdrop-dl-patched/5.6.30/).

### How to Reduce the Impact of Cyberdrop-DL Usage

To help reduce the load on other websites, the `update_last_forum_post` setting has been enabled by default in all users' configs. This setting speeds up scrapes by picking up where the last session left off, rather than re-scraping entire threads.

You can disable this setting if you want to, but I strongly advise against it.

Additionally, I have made adjustments to the default rate-limiting settings to further lessen the impact on websites.

### Usage Best Practices

I encourage you to be mindful of how you use Cyberdrop-DL. Here are some tips to minimize the strain on websites:

* Avoid running multiple scraping sessions repeatedly in a short span of time.
* Regularly clean up your URLs file by removing links you no longer need, and reducing how often you run the program.
* Be selective with what you download. It’s helpful to quickly scan content to avoid downloading files you'll delete later.

### Alternative to Scraping SimpCity

If you wish to continue downloading from SimpCity, you can use a Tampermonkey script like this one: [SimpCity Tampermonkey Forum Downloader](https://simpcity.su/threads/forum-post-downloader-tampermonkey-script.96714/).
