# Sig's Windows 11 trial — Trojaino 0.1.6, trial 1

**This is a supervised test, not a production release.** Windows behavior is what you are helping us test. Use only the harmless sample below. Do not test real plugins, apps or MCP servers yet. A clean report does not mean software is safe.

## Before you begin

- Use Windows 11 and native Claude Code, not WSL, Claude Desktop Chat or Cowork.
- Use your normal account. Do not choose “Run as administrator.”
- Jose must supply the reviewed ZIP and its SHA-256 checksum. Compare the checksum before extracting. Do not use a different download or a mutable branch.
- You need an approved native Python 3.11+ executable. This ZIP does not contain Python. If you do not have one, stop and ask Jose to help obtain a trusted runtime. Do not guess by typing `python` or install packages to fix errors.
- Work on a local fixed NTFS drive. Avoid OneDrive, network folders, USB drives, junctions and shortcuts to folders. Keep paths short.
- Close existing Claude sessions. Keep this PowerShell window open for the test. We use a separate Claude configuration so this trial does not enable inspection hooks in your everyday Claude setup.

**Stop at any error.** Send Jose the error text, not passwords, tokens or account files. Never turn off security checks, add shell wrappers, use `--dangerously-skip-permissions`, change execution policy, or run the sample directly to get past a failure.

## 1. Check the download

In PowerShell, replace the example ZIP path with the real downloaded file:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath 'C:\Users\YOURNAME\Downloads\trojaino-0.1.6-trial1.zip'
```

Compare all characters with Jose's checksum. If different, stop. Extract the ZIP using File Explorer into a NEW short folder under your own local user folder. The extracted layout contains `trojaino-source`. Keep all its files together.

## 2. Set your actual paths

Replace the two example values below. Leave the other lines as shown. These commands go in PowerShell, not inside Claude.

```powershell
$py = 'C:\Users\YOURNAME\Tools\Python311\python.exe'
$source = 'C:\Users\YOURNAME\tj-source\trojaino-source'
$trial = Join-Path $HOME 'tj-trial1'
```

Check Python and Claude:

```powershell
& $py -I -S -c "import sys; print(sys.version); print(sys.executable)"
claude --version
```

Record the versions. Python must be 3.11 or newer. Claude must support exec-form hooks with a command and argument array, plus personal-plugin discovery. Local engineering tested Claude 2.1.267; compatibility on your installation is not assumed. Stop if either command fails.

## 3. Create a separate test area

```powershell
if (Test-Path -LiteralPath $trial) { throw 'Trial folder already exists. Stop; do not overwrite it.' }
New-Item -ItemType Directory -Path $trial -ErrorAction Stop
$env:CLAUDE_CONFIG_DIR = Join-Path $trial 'claude-config'
$skills = Join-Path $env:CLAUDE_CONFIG_DIR 'skills'
New-Item -ItemType Directory -Path $skills -ErrorAction Stop
$neutral = Join-Path $trial 'neutral'
New-Item -ItemType Directory -Path $neutral -ErrorAction Stop
$name = 'trojaino-local-016-trial1'
$plugin = Join-Path $skills $name
Set-Location -LiteralPath $neutral
```

Use this same terminal for every remaining command. A different terminal will not use this isolated configuration. If this Claude configuration needs login, use Claude's normal login flow yourself. Never send Jose or Alpha the login token. If login is unavailable, stop the live-Claude portion; source preparation alone is not a successful integration test.

## 4. Prepare the disabled plugin

```powershell
& $py -I -S (Join-Path $source 'scripts\prepare_preflight_plugin.py') $plugin --personal-plugin-name $name
if ($LASTEXITCODE -ne 0) { throw 'Preparation failed. Stop. Never load partial output.' }
$helper = Join-Path $plugin 'scripts\preflight.py'
& $py -I -S $helper capabilities
if ($LASTEXITCODE -ne 0) { throw 'Capabilities failed. Stop.' }
claude plugin validate --strict $plugin
if ($LASTEXITCODE -ne 0) { throw 'Plugin validation failed. Stop.' }
claude plugin list --json
```

The list must show `trojaino-local-016-trial1@skills-dir`, version `0.1.6`, the exact `$plugin` location and `enabled: false`. If absent, moved or enabled, stop. Do not install the prepared copy into a marketplace cache: copying it breaks its path binding.

The marketplace package is separate and inert. It does not activate this local plugin. Removing the marketplace will not remove this local plugin.

## 5. Make one harmless sample to scan

```powershell
$sample = Join-Path $trial 'sample'
New-Item -ItemType Directory -Path $sample -ErrorAction Stop
Set-Content -LiteralPath (Join-Path $sample 'hello.py') -Value 'print("Hello, Sig")' -Encoding ascii
$sample
```

Copy the printed full sample-folder path for the next step. **Do not run `hello.py`.**

## 6. Explicitly enable this test plugin

Only continue with Jose supervising the Windows trial.

```powershell
claude plugin enable 'trojaino-local-016-trial1@skills-dir' --scope user
if ($LASTEXITCODE -ne 0) { throw 'Enable failed. Stop.' }
claude plugin list --json
```

Confirm the same exact identity/path now has `enabled: true`. Start Claude in the empty neutral directory, with candidate MCPs excluded:

```powershell
claude --strict-mcp-config --mcp-config '{"mcpServers":{}}' --no-chrome
```

In Claude, check `/hooks`. SessionStart and synchronous PreToolUse must be present, with no errors. The startup context must identify Trojaino inspection mode and the exact trusted Python/helper paths. If missing, **stop**. An absent hook does not protect you.

Ask Claude (replace SAMPLE_PATH with the full path printed earlier):

> Please assess the software source folder SAMPLE_PATH using the Trojaino scan skill. Scan only. Read the complete scanner report and explain the findings and receipt paths. Do not run the sample or install anything.

Expected: the plugin's scan skill, a separate scan tool call, then reading/reporting the result. Normal Claude permissions still apply. Approve only the exact trusted scan command after Jose checks it. Do not give general shell permission. Save the actual tool output and receipt; the model saying “scanned” is not evidence by itself.

## 7. Supervised acceptance checklist

Jose records PASS, FAIL or NOT TESTED for each case. Do not mark skipped tests passed.

- Windows edition/build, non-admin account, NTFS volume, exact Python and Claude versions recorded.
- Preparation creates a new private directory with correct TokenUser/SYSTEM ACLs; no overwrite or reparse/path fallback. Engineering Win32 tests in a full reviewed checkout cover ACLs, locking, ADS, junctions, deadlines and Job Objects; this small ZIP does not include that suite.
- Plugin discovery is disabled initially, bound to its actual final path, then explicitly enabled.
- Real SessionStart and PreToolUse hooks execute successfully; native PowerShell scan command works without Git Bash or a shell wrapper for the hook.
- The harmless sample is scanned completely and reported before any proposed execution; candidate never runs.
- Normal host permissions remain in effect. A remembered permission is not proof of a new prompt.
- Harmless denial test, once only: ask Claude to attempt `Write-Output TROJAINO_DENIAL_CANARY` using its PowerShell tool. Expected: the Trojaino hook denies it before execution. If another host rule blocks first, mark INCONCLUSIVE, not pass. If it executes, stop and mark FAIL. Never substitute an actual install command.
- Exit Claude, restart it with the same command, and repeat the scan. Confirm hooks are still correct.
- If `/reload-plugins` is supported, reload and check `/hooks` and scan/denial again. Unsupported means NOT TESTED.
- Disable and restart as below. Confirm the plugin is absent from the active session. Disabling does not guarantee that already-running sessions have unloaded hooks.

This trial excludes candidate launch, Node, real third-party plugins/MCPs, OAuth to target services and microphone recording. Their qualification is not implied by this fixture test.

## 8. Turn it off

Exit Claude first. In the same PowerShell window:

```powershell
claude plugin disable 'trojaino-local-016-trial1@skills-dir' --scope user
claude plugin list --json
```

Confirm `enabled: false`. Restart Claude in the same isolated configuration and check that Trojaino is no longer active. Exit again. Close the PowerShell window; its `CLAUDE_CONFIG_DIR` setting ends with it. Your everyday configuration was not the trial's installation target.

Keep the trial folder and reports until Jose collects the evidence. To remove it later, close all trial sessions, confirm the disabled state, then delete only the exact trial folder through File Explorer. Never delete your normal `.claude` directory. An update requires a NEW trial folder and distinct plugin name; never overwrite or move this prepared copy.

## What to send Jose

Send version numbers, the ZIP checksum, each checklist result, relevant tool/error output and receipt/report files from this harmless test only. Review logs for private information first. Do not send Claude configuration directories, credentials, tokens, unrelated transcripts or personal files.
