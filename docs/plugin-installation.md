# Install Trojaino for Claude Code

Use Claude Code **2.1.274 or newer** and **Python 3.11 or newer**, available as `python3` (or `python`). Git is required to download the marketplace; on Windows, keep Git Bash installed with Git for Windows. You do not need pip, a virtual environment, a source checkout, or a prepared personal plugin.

## Check prerequisites

In a terminal, run `claude --version` and `python3 --version`.

- **Windows:** follow the [Windows quick start](windows-quick-start.md). Python Install Manager supplies `python3`; after installing it, run `py install default` and reopen the terminal.
- **macOS:** install Python 3.11+ from [python.org](https://www.python.org/downloads/macos/), reopen the terminal, and check `python3 --version`. An older system Python does not meet the requirement.
- **Linux:** install your distribution's Python 3.11+ package and check `python3 --version`. If its default Python is older, use a supported distribution package/version; avoid replacing the operating system's Python in place.

Update Claude Code using its supported updater if it is older than 2.1.274. Close and reopen Claude after changing PATH or installing Python. Python is currently an external prerequisite; installing the plugin does not install Python.

## Install inside Claude Code

```text
/plugin marketplace add BlockhouseSoftware/claude-marketplace
/plugin install trojaino@blockhouse-software
```

Restart Claude Code, then run `/trojaino:doctor`. **Ready** means the offline checks passed: runtime, version, packaged files, registration and execution of both hooks, including a known deny fixture. **Needs attention** gives the next action. The fixture is scanned as text; no package is installed and no fixture script is run.

Starting in 0.3.1, a native launcher checks Python before starting the scanner: PowerShell on Windows (dispatched through Git Bash), and sh on macOS/Linux. It tries `python3`, then `python`, and uses the first interpreter that supports Python 3.11+ in isolated mode. It does not install a runtime or change your settings.

If Python is missing, too old or cannot start, Claude receives an explicit **Trojaino cannot start** message with a setup link and instructions to restart Claude and run `/trojaino:doctor`. The doctor skill uses the same launcher, so it can report **Needs attention** even without Python. No installations are checked in this state; normal Claude permissions still apply. The warning is also returned on covered tool calls if Python becomes unavailable during a session.

This is a startup readiness check, not a pre-install check. Claude can still list the plugin as installed and enabled without Python. With a working runtime, the startup message confirms it started; `/hooks` lists configuration and is not a readiness test. Organizational policies may override local settings.

From a terminal, the equivalent install commands start with `claude plugin` instead of `/plugin`.

## Update inside Claude Code

```text
/plugin marketplace update blockhouse-software
/plugin update trojaino@blockhouse-software
```

Restart Claude Code and run `/trojaino:doctor` again. Refreshing the marketplace first makes the new release pin available. The plugin remains enabled across an ordinary update.

## Migrate an earlier prepared plugin

Install the marketplace version, then run `/trojaino:doctor`. If it reports an older Trojaino plugin or legacy hooks:

1. In `/plugin`, disable the old prepared Trojaino entry; keep `trojaino@blockhouse-software` enabled.
2. Back up the affected Claude settings before editing. Review the `hooks` entries and remove only the old Trojaino launcher entries. Preserve unrelated hooks and settings.
3. Restart Claude Code and run `/trojaino:doctor` until it reports Ready.

Doctor only diagnoses migration; it never edits settings. Do not run two Trojaino hook installations together.

## Remove

Run `/plugin uninstall trojaino@blockhouse-software` and restart Claude. Existing scan reports are retained locally.

## Separate command-line scanner

`pip install trojaino` installs the standalone `tjscan` scanner. It does not register the Claude Code plugin and is not required for the two-command plugin installation.
