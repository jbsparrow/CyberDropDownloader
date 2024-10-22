from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from rich.console import Console

from cyberdrop_dl.managers.manager import Manager
from cyberdrop_dl.utils.args.browser_cookie_extraction import get_cookies_from_browser
from cyberdrop_dl.utils.dataclasses.supported_domains import SupportedDomains

if TYPE_CHECKING:
    from typing import Dict

    from cyberdrop_dl.managers.manager import Manager

console = Console()

BROWSERS= ["Chrome", "Firefox" , "Edge", "Safari" , "Opera", "Brave"]
BROWSER_CHOICES = [Choice(b.lower(),b) for b in BROWSERS]
DEFAULT_CHOICE = Choice(-1, "Done")

def browser_prompt(vi_mode: False) -> None:
    return inquirer.select(
            message="Which browser should we load cookies from?",
            choices = BROWSER_CHOICES + [DEFAULT_CHOICE], 
            long_instruction="ARROW KEYS: Navigate | ENTER: Select",
            vi_mode=vi_mode,
        ).execute()

def edit_gofile_api_key_prompt (manager: Manager) -> None:
    console.clear()
    gofile_api_key = inquirer.text(
        message="Enter the GoFile API Key:",
        default=manager.config_manager.authentication_data["GoFile"]["gofile_api_key"],
        long_instruction="You can get your premium GoFile API Key from https://gofile.io/myProfile",
        vi_mode=manager.vi_mode,
    ).execute()
    manager.config_manager.authentication_data["GoFile"]["gofile_api_key"] = gofile_api_key

def edit_imgur_client_id_prompt(manager: Manager) -> None:
    console.clear()
    imgur_client_id = inquirer.text(
        message="Enter the Imgur Client ID:",
        default=manager.config_manager.authentication_data["Imgur"]["imgur_client_id"],
        long_instruction="You can create an app and get your client ID "
                        "from https://imgur.com/account/settings/apps",
        vi_mode=manager.vi_mode,
    ).execute()
    manager.config_manager.authentication_data["Imgur"]["imgur_client_id"] = imgur_client_id

def edit_pixeldrain_api_key_prompt(manager: Manager) -> None:
    console.clear()
    pixeldrain_api_key = inquirer.text(
        message="Enter the PixelDrain API Key:",
        default=manager.config_manager.authentication_data["PixelDrain"]["pixeldrain_api_key"],
        long_instruction="You can get your premium API Key from https://pixeldrain.com/user/api_keys",
        vi_mode=manager.vi_mode,
    ).execute()
    manager.config_manager.authentication_data["PixelDrain"]["pixeldrain_api_key"] = pixeldrain_api_key

def edit_forum_authentication_values_prompt(manager: Manager) -> None:
    """Edit the forum authentication values"""
    while True:
        console.clear()
        console.print("Editing Forum Authentication Values")
        action = inquirer.select(
            message="What would you like to do?",
            choices=[
                Choice(1, "Browser Cookie Extraction"),
                Choice(2, "Enter Cookie Values Manually"),
            ]+[DEFAULT_CHOICE], 
            long_instruction="ARROW KEYS: Navigate | ENTER: Select",
            vi_mode=manager.vi_mode,
        ).execute()

        # Browser Cookie Extraction
        if action == 1:
            browser = browser_prompt(manager.vi_mode)
            if browser == DEFAULT_CHOICE.value:
                continue

            get_cookies_from_browser(manager, browser, SupportedDomains.supported_forums_map.values())
            
        # Enter Cred Values Manually
        elif action == 2:
            for domain in SupportedDomains.supported_forums_map.values():
                ask_username_and_password_prompt(manager, domain)

        return

def ask_username_and_password_prompt( manager: Manager, domain:str,  display_name: Optional[str] = None) -> None:
    if not  display_name:
        display_name = domain
    username = inquirer.text(
        message=f"Enter your {display_name} Username:",
        default=manager.config_manager.authentication_data["Forums"][f"{domain}_username"],
        vi_mode=manager.vi_mode,
    ).execute()
    
    password = inquirer.text(
        message=f"Enter your {display_name} Password:",
        default=manager.config_manager.authentication_data["Forums"][f"{domain}_password"],
        vi_mode=manager.vi_mode,
    ).execute()
    manager.config_manager.authentication_data["Forums"][f"{domain}_username"] = username
    manager.config_manager.authentication_data["Forums"][f"{domain}_password"] = password

def edit_filehost_authentication_values_prompt(manager: Manager) -> None:
    """Edit the filehost authentication values"""
    while True:
        console.clear()
        console.print("Editing Forum Authentication Values")
        action = inquirer.select(
            message="What would you like to do?",
            choices=[
                Choice(1, "Browser Cookie Extraction")
            ]+[DEFAULT_CHOICE], 
            long_instruction="ARROW KEYS: Navigate | ENTER: Select",
            vi_mode=manager.vi_mode,
        ).execute()

        if action == 1:
            browser = browser_prompt(manager.vi_mode)
            domain = inquirer.select(
                message="Which filehost to load cookies from?",
                choices=[Choice(domain) for domain in SupportedDomains.supported_hosts], 
                long_instruction="ARROW KEYS: Navigate | ENTER: Select",
                vi_mode=manager.vi_mode,
            ).execute()

            if browser == DEFAULT_CHOICE.value:
                continue
            
            get_cookies_from_browser(manager, browser, [domain])

        return

        
def edit_jdownloader_authentication_values_prompt(manager: Manager) -> None:
    """Edit the JDownloader authentication values"""
    console.clear()
    jdownloader_username = inquirer.text(
        message="Enter the JDownloader Username:",
        default=manager.config_manager.authentication_data["JDownloader"]["jdownloader_username"],
    ).execute()
    jdownloader_password = inquirer.text(
        message="Enter the JDownloader Password:",
        default=manager.config_manager.authentication_data["JDownloader"]["jdownloader_password"],
    ).execute()
    jdownloader_device = inquirer.text(
        message="Enter the JDownloader Device Name:",
        default=manager.config_manager.authentication_data["JDownloader"]["jdownloader_device"],
    ).execute()

    manager.config_manager.authentication_data["JDownloader"]["jdownloader_username"] = jdownloader_username
    manager.config_manager.authentication_data["JDownloader"]["jdownloader_password"] = jdownloader_password
    manager.config_manager.authentication_data["JDownloader"]["jdownloader_device"] = jdownloader_device


def edit_reddit_authentication_values_prompt(manager: Manager) -> None:
    """Edit the reddit authentication values"""
    console.clear()
    console.print(
        "You can create a Reddit App to use here: https://www.reddit.com/prefs/apps/"
    )
    reddit_secret = inquirer.text(
        message="Enter the Reddit Secret value:",
        default=manager.config_manager.authentication_data["Reddit"]["reddit_secret"],
    ).execute()
    reddit_personal_use_script = inquirer.text(
        message="Enter the Reddit Personal Use Script value:",
        default=manager.config_manager.authentication_data["Reddit"]["reddit_personal_use_script"],
    ).execute()

    manager.config_manager.authentication_data["Reddit"]["reddit_secret"] = reddit_secret
    manager.config_manager.authentication_data["Reddit"]["reddit_personal_use_script"] = reddit_personal_use_script


EDIT_AUTH_OPTIONS = {
    "Edit Forum Authentication Values": edit_forum_authentication_values_prompt,
    "Edit File-Host Authentication Values": edit_filehost_authentication_values_prompt ,
    "Edit JDownloader Authentication Values": edit_jdownloader_authentication_values_prompt,
    "Edit Reddit Authentication Values": edit_reddit_authentication_values_prompt ,
    "Edit GoFile API Key": edit_gofile_api_key_prompt ,
    "Edit Imgur Client ID": edit_imgur_client_id_prompt ,
    "Edit PixelDrain API Key": edit_pixeldrain_api_key_prompt
}

EDIT_AUTH_CHOICES = [Choice(index, option) for index, option in enumerate(EDIT_AUTH_OPTIONS,1)]

def edit_authentication_values_prompt(manager: Manager) -> None:
    """Edit the authentication values"""
    auth = manager.config_manager.authentication_data

    while True:
        console.clear()
        console.print("Editing Authentication Values")
        action = inquirer.select(
            message="What would you like to do?",
            choices=EDIT_AUTH_CHOICES+[DEFAULT_CHOICE],
            long_instruction="ARROW KEYS: Navigate | ENTER: Select",
            vi_mode=manager.vi_mode,
        ).execute()

        if action == DEFAULT_CHOICE.value:
            manager.config_manager.write_updated_authentication_config()
            return
        
        choice = next((c for c in EDIT_AUTH_CHOICES if c.value == action))
        EDIT_AUTH_OPTIONS[choice.name](manager)

        