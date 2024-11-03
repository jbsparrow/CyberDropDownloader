# Contributing

## Found an Issue?

If you find a bug in the source code or a mistake in the documentation, you can
[open an Issue](#submitting-an-issue) to the GitHub Repository or you can
[submit a Pull Request](#submitting-a-pull-request-pr) with a fix if you know how to code.

## Want a Feature?

You can *request* a new feature by [opening an issue](#submitting-an-issue). If you would like to *implement* a new feature,
please open an issue or a discussion with a proposal first. If your feature is *small* and easy to implement,
you can craft it and directly [submit it as a Pull Request](#submitting-a-pull-request-pr).

## Submission Guidelines

### Submitting an Issue

Before openning an issue, search through existing issues to ensure you are not opening a duplicate.
You must also [read the wiki](https://script-ware.gitbook.io/cyberdrop-dl/frequently-asked-questions) to learn how to solve most common problems.

If your issue appears to be a bug, and hasn't been reported, open a new issue. Please do not report duplicate issues.
Providing the following information will allow your issue to be dealt with quickly:

- **Overview of the Issue** - always attach you logs to any new issue.
- **Version** - what version of Cyberdrop-DL are you running. You should always update to the latest release before opening an issue since 
the issue may have been fixed already
- **Motivation for or Use Case** - explain what are you trying to do and why the current behavior is a bug for you
- **Operating System** - what OS and version are you using
- **Reproduce the Error** - provide a live example or a unambiguous set of steps
- **Related Issues** - has a similar issue been reported before?
- **Suggest a Fix** - if you can't fix the bug yourself, perhaps you can point to what might be
  causing the problem (line of code or commit)

You can open a new issue by providing the above information at https://github.com/jbsparrow/CyberDropDownloader/issues/new/choose.

### Submitting a Pull Request (PR)

Before you submit your Pull Request (PR) consider the following guidelines:

- Search the [repository](https://github.com/jbsparrow/CyberDropDownloader/pulls) for an open or closed PR
  that relates to your submission. You don't want to duplicate effort.
- Clone the repo and make your changes on a new branch in your fork
- Follow [code style conventions](#code-style)
- Commit your changes using a descriptive commit message
- Push your fork to GitHub
- In GitHub, create a pull request to the `master` branch of the repository. 
- Add a description to your PR. If the PR is small (such as a typo fix), you can go brief. 
If it contains a lot of changes, it's better to write more details.
If your changes are user-facing (e.g. a new feature in the UI, a change in behavior, or a bugfix) 
please include a short message to add to the changelog.
- Wait for a maintainer to review your PR and then address any comments they might have.

If everything is okay, your changes will be merged into the project.

## Setting up the development environment

1. Install a [supported version of Python](https://www.python.org/downloads/). Cyberdrop-DL supports python `3.11` through `3.12`
(python `3.13` is **NOT** supported yet)

2. Clone the repo

```shell
git clone "https://github.com/jbsparrow/CyberDropDownloader"
cd CyberDropDownloader
```

3. Install `pipx` (optional, but recommended): https://pipx.pypa.io/stable/installation/

4. Install `poetry`, the project management package Cyberdrop-DL uses

> If you installed `pipx`:

```shell
pipx install poetry
```

> With regular `pip`:

```shell
pip install poetry
```

5. Install the project's dependencies

```shell
poetry install
```

6. Install the pre-commit hooks:

```shell
poetry run pre-commit install
```

## Code Style

### Standards

`Formatting`: This project uses [ruff](https://docs.astral.sh/ruff) for formatting, linting and import sorting.

`Typechecking`: Typechecking is not enforced but highly recommended.

`Line Width`: We use a line width of 120.

### Code formatting with pre-commit hooks

This project uses git pre-commit hooks to perform formatting and linting before a commit is allowed,
to ensure consistent style and catch some common issues early on.

Once installed, hooks will run when you commit. If the formatting isn't quite right or a linter catches something,
the commit will be rejected and `ruff` will try to fix the files. If `ruff` can not fix all the issues,
you will need to look at the output and fix them manually. When everything is fixed (either by `ruff` itself or manually)
all you need to do is `git add` those files again and retry your commit.

### Manual code formatting

We recommend [setting up your IDE](https://docs.astral.sh/ruff/editors/) to format and check with `ruff`, but you can always run
`poetry run ruff check --fix` then `poetry run ruff format` in the root directory before submitting a pull request.
If you're using VScode, you can set it to [auto format python files with ruff on save](#editor-settings) in your `settings.json`

## Editor settings

If you use VScode and have `ruff` installed as a formatter, you might find the following `settings.json` useful:

```json
{
  "[python]": {
    "editor.formatOnSave": true,
    "editor.defaultFormatter": "charliermarsh.ruff"
  }
}
```
