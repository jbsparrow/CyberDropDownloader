---
description:
icon: android
---

# Installing cyberdrop-dl on Android

Cyberdrop-dl is a terminal app. That means you need a terminal emulator to run it. The defacto choice in Android is [termux](https://termux.dev/en/).

{% hint style="info" %}
Most of the dependencies need to be compiled from source. A rust compiler is required. This means the installation could take several minutes, especially on low end phones
{% endhint %}

{% hint style="warning" %}
Compiling from source also requires a lot of extra storage. You will need at least 3.4GB just for the installation of CDL
{% endhint %}

## 1. Install `termux`

Termux wiki: [https://wiki.termux.com/wiki/Installation](https://wiki.termux.com/wiki/Installation)

Install termux from [F-droid (recommended)](https://f-droid.org/packages/com.termux/) or from the [Google Playstore (restricted version)](https://play.google.com/store/apps/details?id=com.termux):

## 2. Install `cyberdrop-dl-patched`

Run the following commands inside termux

```shell
# Get storage access permission
termux-setup-storage

# Install dependencies
pkg upgrade -y
pkg install rust which micro libjpeg-turbo python uv -y

# Install CDL and setup appdata folder
uv tool install cyberdrop-dl-patched
uv tool update-shell
mkdir /sdcard/cyberdrop-dl
echo 'alias cyberdrop-dl="cyberdrop-dl --portrait --appdata-folder /sdcard/cyberdrop-dl"' >> ~/.bashrc
source ~/.bashrc
```

## How to update `cyberdrop-dl-patched`?

Run this command inside termux:

```shell
uv tool upgrade cyberdrop-dl-patched
```
