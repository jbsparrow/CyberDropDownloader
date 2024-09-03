---
description: These are all of the configuration options for Authentication.
---

# Authentication

<details>

<summary>Forums</summary>

In order to scrape links/content from forums, you need to provide Cyberdrop-DL with your login details so it can access the website. This section also includes cookies for the support forums.

If you use the cookie extractor to load the XF\_User\_Cookies into the program, you don't need to provide the program with credentials. If you ever log out of the forum in your browser though, you will need to use the cookie extractor again to get new cookies.

It is best to leave the authentication parameter for SimpCity blank, as they have made their forum public and have asked users scraping the website not to use logged in users.

***

* \<forum>\_xf\_user\_cookie

This is the value for the cookie I was talking about above. If you want to only use credentials, you can leave this blank.

* \<forum>\_username

This is your username for the forum. Again, if you use the cookie, you don't need to provide this.

* \<forum>\_password

This is your password for the forum. Again, if you use the cookie, you don't need to provide this.

</details>

<details>

<summary>GoFile</summary>

If you decide to pay for GoFile Premium (faster downloads, etc) you can provide your API key to Cyberdrop-DL in order for the program to use it.

***

* gofile\_api\_key

You can get your API key here: [https://gofile.io/myProfile](https://gofile.io/myProfile)

</details>

<details>

<summary>Imgur</summary>

In order to scrape images from Imgur, you'll need to create a client on Imgurs website.

[https://api.imgur.com/oauth2/addclient](https://api.imgur.com/oauth2/addclient)

Some examples of what to put in for what it asks for:

* Application Name: Cyberdrop-DL
* OAuth2 without a callback URL
* Website: \<really doesn't matter>
* Email: Your email
* Description: Cyberdrop-DL client

***

* imgur\_client\_id

After generating the client above, you will need to give Cyberdrop-DL the client ID.

</details>

<details>

<summary>JDownloader</summary>

Under JDownloader 2 settings -> MyJDownloader

You will set an email, password, and device name (then connect).

***

* jdownloader\_username

Provide Cyberdrop-DL the email from above

* jdownloader\_password

Provide Cyberdrop-DL the password from above

* jdownloader\_device

Provide Cyberdrop-DL the device name from above

</details>

<details>

<summary>PixelDrain</summary>

If you decide to pay for PixelDrain premium (faster downloads, etc) you can provide your API key to Cyberdrop-Dl in order for the program to use it.

***

* pixeldrain\_api\_key

You can get your API key here: [https://pixeldrain.com/user/api\_keys](https://pixeldrain.com/user/api\_keys)

</details>

<details>

<summary>Reddit</summary>

In order to scrape files from Reddit, you'll need to create an app on reddits website (it's free).

[https://www.reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)

Some examples of what to put in for what it asks for:

* name: Cyberdrop-DL
* script
*
*

***

* reddit\_personal\_use\_script
* reddit\_secret

after generating the app, you will need to give Cyberdrop-DL these values.

</details>
