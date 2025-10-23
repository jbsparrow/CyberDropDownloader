# type: ignore[reportPrivateImportUsage]
import sys
from pathlib import Path

from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from InquirerPy.separator import Separator
from InquirerPy.validator import EmptyInputValidator, PathValidator

from cyberdrop_dl.ui.prompts.defaults import DEFAULT_OPTIONS, DONE_CHOICE


def ask_text(message: str, validate_empty: bool = True, **kwargs):
    options = DEFAULT_OPTIONS | kwargs
    return inquirer.text(
        message=message,
        validate=EmptyInputValidator("Input should not be empty") if validate_empty else None,
        **options,
    ).execute()


def ask_choice(choices: list[Choice], *, message: str = "What would you like to do:", **kwargs):
    options = DEFAULT_OPTIONS | kwargs
    return inquirer.select(message=message, choices=choices, **options).execute()


def ask_multi_choice(choices: list[Choice], *, message: str = "What would you like to do:", **kwargs):
    return ask_choice(choices, message=message, multiselect=True, **kwargs)


def ask_checkbox(choices: list[Choice], *, message: str = "Select multiple options:", **kwargs):
    options = DEFAULT_OPTIONS | {"long_instruction": "ARROW KEYS: Navigate | SPACE: Select | ENTER: Confirm"} | kwargs
    return inquirer.checkbox(message=message, choices=choices, **options).execute()


def ask_choice_fuzzy(choices: list[Choice], message: str, validate_empty: bool = True, **kwargs):
    options = (
        DEFAULT_OPTIONS
        | {"long_instruction": "ARROW KEYS: Navigate | TYPE: Filter | TAB: select, ENTER: Finish Selection"}
        | kwargs
    )
    custom_validate = options.pop("validate", None)
    validate = (
        EmptyInputValidator("Input should not be empty")
        if validate_empty and custom_validate is None
        else custom_validate
    )
    return inquirer.fuzzy(
        message=message,
        choices=choices,
        validate=validate,
        **options,
    ).execute()


def ask_path(message: str = "Select path", *, validator_options: dict | None = None, **kwargs) -> Path:
    options = DEFAULT_OPTIONS | {"default": str(Path.home())} | kwargs
    return Path(
        inquirer.filepath(message=message, validate=PathValidator(**(validator_options or {})), **options).execute()
    )


def ask_file_path(message: str = "Select file path", **kwargs) -> Path:
    options = DEFAULT_OPTIONS | kwargs
    validator_options = {"is_file": True, "message": "Input is not a file"}
    return ask_path(message, validator_options=validator_options, **options)


def ask_dir_path(message: str = "Select dir path", **kwargs) -> Path:
    options = DEFAULT_OPTIONS | kwargs
    validator_options = {"is_dir": True, "message": "Input is not a directory"}
    return ask_path(message, validator_options=validator_options, **options)


def ask_toggle(message: str = "enable", **kwargs):
    options = DEFAULT_OPTIONS | {"long_instruction": "Y: Yes | N: No"} | kwargs
    return inquirer.confirm(message=message, **options).execute()


def enter_to_continue(message: str = "Press <ENTER> to continue", **kwargs):
    if "pytest" in sys.modules:
        return
    options = DEFAULT_OPTIONS | {"long_instruction": "ENTER: continue"} | kwargs
    msg = f"\n{message}"
    return inquirer.confirm(message=msg, qmark="", **options).execute()


def create_choices(
    options_groups: list[list[str]] | dict[str, list[list[str]]],
    append_last: Choice = DONE_CHOICE,
    *,
    disabled_choices: list[str] | None = None,
):
    if isinstance(options_groups, dict):
        options_groups = list(options_groups.values())
    disabled_choices = disabled_choices or []
    options = [option for group in options_groups for option in group]
    choices = []
    for index, option in enumerate(options, 1):
        enabled = option not in disabled_choices
        choices.append(Choice(index, option, enabled))
    choices.append(append_last)

    separator_indexes = []
    for group in options_groups:
        separator_indexes.append(len(group) + (separator_indexes[-1] if separator_indexes else 0))

    for count, index in enumerate(separator_indexes):
        choices.insert(index + count, Separator())

    return choices
