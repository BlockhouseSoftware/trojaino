# Windows validation without a dedicated test PC

Use hosted Windows checks for repeatable engineering evidence. Do not substitute a green hosted-runner result for an ordinary Windows 11 user's installation experience.

## Repeatable, model-free checks

The **Install gate** workflow exercises:

- the unit suite on Windows and macOS;
- actual unsupported Python 3.10 and supported Python 3.11, plus absent/broken interpreter cases;
- plugin installation and update through the actual Claude plugin manager;
- the minimum supported Claude version and the currently available version;
- the exact pushed candidate through the production GitHub `git-subdir` source;
- doctor readiness, installed hook execution, legacy-hook diagnosis and payload damage;
- actual manager disable → Needs attention → enable → Ready → uninstall, with registration readback and preservation of unrelated settings. Each doctor invocation must preserve settings bytes exactly.

Pull requests run these checks without an authenticated model session. For an intentional manual run, select the exact branch under **Actions → Install gate → Run workflow**:

- Leave **run_live** unchecked for model-free validation. This input defaults to false.
- Select **public_install** only to additionally verify the currently published marketplace release. A candidate test and a published-release test are different evidence.
- Enable **run_live** only with separate approval for billable authenticated Claude sessions. A missing API key is a skip, not a live PASS.

Record the workflow run, full tested commit SHA, OS/runner image, actual Claude and Python versions, executed assertions, skips and failure logs. A moving `latest` label is not an exact version. Retain the original failed attempt when rerunning a transient infrastructure failure. Do not change a product test to hide a network failure.

The unit, plugin, standalone executable and installer jobs test different artifacts. Read the failed step: a release self-scan failure is not a failed unit test. Changes to shipped source require reviewed inventory updates; do not suppress scanner findings to obtain green CI.

## Supplemental Windows 11 ARM checks

Manual runs also include a **Windows 11 ARM platform / model-free** job. It checks the actual Windows client product type and caption, OS architecture and Python runtime architecture before running the unit suite and candidate plugin-manager checks. With `public_install` selected, it also checks the published release. It records the candidate commit and runtime versions without starting an authenticated model session.

This supplements the default Windows Server x64 jobs; it does not establish Windows 11 x64 equivalence or ordinary-user usability. A failure here must remain visible even when the Server jobs pass. Interpreter-absence cases are particularly important: successful installation on a preprovisioned runner does not test recovery on a machine without Python.

## What hosted Windows does not prove

Neither the default Server jobs nor the supplemental Windows 11 ARM job proves an ordinary Windows 11 desktop journey. These remain separate checks:

- Installing prerequisites with the real Windows installation tools, without administrator elevation or developer provisioning.
- Store aliases and PATH refresh after installation; opening a genuinely new terminal.
- The user's real Claude installation method, profile and permissions.
- First-download reputation/SmartScreen behavior, readable messages and keyboard accessibility.
- A fresh authenticated Claude session enforcing the gate, rather than just a direct hook test.

Do not ask a nontechnical tester to disable antivirus, bypass SmartScreen, edit interpreter paths, or repair configuration to make an acceptance test pass. A blocked step is evidence, not a request to weaken protection.

## A small support report, not a machine dump

When a user encounters a problem, collect only what distinguishes the failing step:

1. Which numbered step of the [Windows quick start](windows-quick-start.md) failed.
2. The exact error or a cropped screenshot of it. Review the crop for private text before sharing.
3. The **Ready / Needs attention** status and suggested actions from `/trojaino:doctor`, if the command can start.
4. The visible Trojaino, Claude Code and Python version numbers, if already available. Do not require more commands when the native launcher itself cannot start.
5. Windows version/architecture and whether the installation was the marketplace plugin or the separate command-line scanner, if known.

Do not request complete settings files, environment-variable dumps, API keys, conversation logs, project files, home-directory archives or a remote-access session. Doctor does not upload a report. Raw CI/model-session logs are not automatically suitable for end-user support.

A report of a historical failure without its step, message and artifact/version is **unreproduced**. Passing today's CI does not establish the historical cause. Build a failing test from recovered evidence before claiming to have fixed that incident.
