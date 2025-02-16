---
description: These are all of the configuration options for Authentication.
icon: user-lock
---

# Authentication

All the options in these list are optional. The default value for all of them is an empty `str`

| Type  | Default |
| ----- | ------- |
| `str` | `""`    |

<details>

<summary>Coomer</summary>

In order to scrape your favorites from coomer, you need to provide Cyberdrop-DL with your coomer `session` cookie.

## `session`

Once you have put your `session` cookie into the authentication file, you can add `https://coomer.su/favorites` to the URLs file, and Cyberdrop-DL will scrape your favorites.

</details>

<details>

<summary>Forums</summary>

In order to scrape links/content from forums, you need to provide Cyberdrop-DL with your login details so it can access the website. This section also includes cookies for the support forums.

If you use the cookie extractor to load the `XF_User` cookies into the program, you don't need to provide these credentials. If you ever log out of the forum in your browser though, you will need to use the cookie extractor again to get new cookies.

It is best to leave the authentication parameter for SimpCity blank, as they have made their forum public and have asked users scraping the website not to use logged in users.

In order to set specific authentication values for a config instead of the global values, make an `authentication.yaml` file in the config folder.

## `xf_user_cookie`

This is the value for the `XF_User` cookie mentioned above. If you want to only use credentials, you can leave this blank.

## `username`

This is your username for the forum. Again, if you use cookies, you don't need to provide this.

## `password`

This is your password for the forum. Again, if you use cookies, you don't need to provide this.

</details>

<details>

<summary>GoFile</summary>

If you decide to pay for GoFile Premium (faster downloads, etc.) you can provide your API key to Cyberdrop-DL in order for the program to use it.

## `api_key`

You can get your API key here: [https://gofile.io/myProfile](https://gofile.io/myProfile)

</details>

<details>

<summary>Imgur</summary>

In order to scrape images from Imgur, you'll need to create a client on Imgur's website.

[https://api.imgur.com/oauth2/addclient](https://api.imgur.com/oauth2/addclient)

Some examples of what to put in for what it asks for:

- Application Name: `Cyberdrop-DL`

- OAuth2 without a callback URL

- Website: `<really doesn't matter>`

- Email: `your_email@domain.com`

- Description: `Cyberdrop-DL client`

## `client_id`

After generating the client above, you will need to give Cyberdrop-DL the client ID.

</details>

<details>

<summary>JDownloader</summary>

Under JDownloader 2 settings -> MyJDownloader

You will set an email, password, and device name (then connect).

## `username`

Provide Cyberdrop-DL the email from above

## `password`

Provide Cyberdrop-DL the password from above

## `device`

Provide Cyberdrop-DL the device name from above

</details>

<details>

<summary>PixelDrain</summary>

If you decide to pay for PixelDrain premium (faster downloads, etc.) you can provide your API key to Cyberdrop-DL in order for the program to use it.

## `api_key`

You can get your API key here: [https://pixeldrain.com/user/api_keys](https://pixeldrain.com/user/api_keys)

</details>

<details>

<summary>Real-Debrid</summary>

In order to download files from sites supported by real-debrid, you'll need to get the API token from your account.

## `api_key`

You can get your API key here (you must be logged in): [https://real-debrid.com/apitoken](https://real-debrid.com/apitoken)

</details>

<details>

<summary>Reddit</summary>

In order to scrape files from Reddit, you'll need to create an app on reddit's website (it's free): [https://www.reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)

Select `script` as the app type. Any name can be used. The redirect URI value isn't important, but it is required. You can use fake URL like `http://your_username.cyberdrop-dl`. Click `create app` to get your credentials.

![reddit_personal_script_setup_1](../../assets/reddit_personal_script_setup_1.png)
![reddit_personal_script_setup_2](../../assets/reddit_personal_script_setup_2.png)

After generating the app, you need to give Cyberdrop-DL these values:

## `personal_use_script`

Copy the value of `presonal_use_script`

## `secret`

Copy the value of `secret`

</details>
