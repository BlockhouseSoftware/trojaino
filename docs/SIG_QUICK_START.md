# Sig’s first Trojaino test on Windows 11

**Start here. You do not need to know how to code.**

Trojaino checks program files for warning signs before you try them. This guide sets up a small test with Claude Code. It does **not** install any new MCP, plugin from another company, or app to test.

**This is an early test version.** It has passed tests on Windows Server, but we still need to check it with Claude Code on your Windows 11 computer. It is not antivirus software. A good scan result does not prove that an app is safe.

Read and download now. **Arrange the first setup and test with Jose before you run the setup steps.** He can help by call or chat; you do not need to be in the same country. Do not use this test session for normal work yet.

## 1. Check your computer

1. Open **Start → Settings → System → About**. If Windows is in Norwegian, use the matching labels on your screen.
2. Check that the Windows version is **Windows 11**.
3. Under **System type**, look for **64-bit operating system, x64-based processor**. If it says **ARM**, stop and tell Jose. The Python download below is for x64 computers only.
4. Use your own Windows account. Do not choose **Run as administrator** for any step.
5. Claude Code must already work on this computer. This means the Claude app you use in a command window, not just the Claude website or desktop chat app. If it is missing, asks you to sign in again, or needs payment, stop and ask Jose. Do not download a replacement from a search result.

## 2. Download the files

Click these links. Save the files in your usual **Downloads** folder. Do not rename them. You do not need Git, a GitHub account, or the green **Code** button.

| File | What to do |
| --- | --- |
| [Trojaino test files — download ZIP](https://github.com/BlockhouseSoftware/trojaino/releases/download/sig-windows-pilot-2026-09-11/trojaino-preflight-native2-source.zip) | Required. Download this first. Do **not** open or extract it yet. |
| [Python 3.14.7 for Windows x64 — download](https://github.com/BlockhouseSoftware/trojaino/releases/download/sig-windows-pilot-2026-09-11/python-3.14.7-amd64.exe) | Download if Step 3 says Python is missing. Python is the tool that runs Trojaino. |
| [Save this guide as a text file](https://github.com/BlockhouseSoftware/trojaino/releases/download/sig-windows-pilot-2026-09-11/SIG_QUICK_START.txt) | Optional. Open it with Notepad if you want an offline copy. |

The Python file is an unchanged copy of the installer from [Python’s official release page](https://www.python.org/downloads/release/python-3147/). Its license is included in the installer. Claude Code is not included; use your existing installation.

If a link shows **404 / Not Found**, or Windows/browser security blocks a download, stop and tell Jose. Do not turn off security settings or choose **Run anyway**.

## 3. Open PowerShell and check Python

PowerShell is a Windows app where you can paste the commands below.

1. Click **Start**.
2. Type **Windows PowerShell**.
3. Click **Open**. Do not choose **Run as administrator**.
4. Copy the entire box below. Click inside PowerShell, paste it, and press **Enter**. If Windows warns that you are pasting several lines, check that the text is this box before agreeing to paste.

**Paste into PowerShell, not into Claude:**

```powershell
$Python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe'
if (Test-Path -LiteralPath $Python) {
    & $Python --version
} else {
    Write-Host 'Python was not found in the folder used by this guide.'
}
```

**What you should see:** `Python 3.14.7` or a newer `Python 3.14` maintenance version. If so, skip to Step 5.

If you see Python 3.13, 3.15, a test version, or anything else, stop and ask Jose. This guide uses one fixed Python folder so you do not have to edit file paths.

If Python was not found and you already use Python elsewhere, ask Jose before installing another copy.

If you do not have Python, continue to Step 4 with Jose’s approval.

## 4. Install Python only if needed

1. Download the Python file in Step 2. Do not open it yet.
2. Paste this box into the **same PowerShell window** and press Enter. It checks the downloaded file without running it.

```powershell
& {
    $File = Join-Path $HOME 'Downloads\python-3.14.7-amd64.exe'
    $Expected = '9d9eb2709ef81bf5cd30db3c2096bdbc4ea10087c22e62f27d356b36f6ae9649'
    $Actual = (Get-FileHash -LiteralPath $File -Algorithm SHA256 -ErrorAction Stop).Hash
    if ($Actual.ToLowerInvariant() -ne $Expected) { throw 'STOP: Python download did not match. Ask Jose.' }
    Write-Host 'PYTHON DOWNLOAD CHECKED. You may open this file with Jose approval.'
}
```

3. Continue only if you see **PYTHON DOWNLOAD CHECKED** with no error.
4. Open **File Explorer → Downloads**. Double-click `python-3.14.7-amd64.exe`.
5. Use **Install Now** for your own account. Keep the default folder. Leave options for administrator access or installing for all users **off**. You do not need to add Python to PATH for this guide.
6. If the installer instead shows **Modify**, **Repair**, or **Uninstall**, stop and ask Jose. If Windows asks for an administrator password or permission to make administrator changes, cancel and ask Jose.
7. When installation finishes, click **Close**. Do not change the Windows path-length limit or other Windows settings.
8. Repeat the check in Step 3. Continue only when it shows Python 3.14.7 or a newer 3.14 maintenance version. If you see a different version or an error, stop.

## 5. Check Claude Code

Keep the same PowerShell window open for the rest of this guide.

Paste this line into **PowerShell** and press Enter:

```powershell
claude --version
```

**What you should see:** a Claude Code version number. Send that number to Jose. If the command is not found, do not try other installation commands. Ask Jose for help.

## 6. Prepare Trojaino

This step checks the Trojaino download and puts its files in a new folder named **TJ** inside your Windows user folder. It does not change Claude’s global settings.

1. Make sure Jose is available for this first test.
2. Do not move the files into OneDrive, Dropbox, a USB drive, or a shared network folder.
3. Copy **all** of the next box. Paste it into **PowerShell**, not Claude. Press Enter.
4. You do not need to understand or edit the code. It uses your own Windows folder automatically.

```powershell
$TrojainoSetup = $null
& {
    $OldPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Stop'
        $Python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe'
        $Zip = Join-Path $HOME 'Downloads\trojaino-preflight-native2-source.zip'
        $Base = Join-Path $HOME 'TJ'
        $Expected = '7d40a7c2a71bd416a733547aae21453aa86a2967634a7ee3b23aa86016e34634'
        if ((Get-FileHash -LiteralPath $Zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Expected) { throw 'STOP: Trojaino download did not match. Ask Jose.' }
        if (Test-Path -LiteralPath $Base) { throw 'STOP: The TJ folder already exists. Ask Jose; do not delete it.' }
        & $Python --version
        if ($LASTEXITCODE -ne 0) { throw 'STOP: Python check failed.' }
        New-Item -ItemType Directory -Path $Base | Out-Null
        Expand-Archive -LiteralPath $Zip -DestinationPath $Base
        $Source = Join-Path $Base 'trojaino-source'
        $Prepared = Join-Path $Base 'prepared'
        & $Python -I -S (Join-Path $Source 'scripts\prepare_preflight_plugin.py') $Prepared
        if ($LASTEXITCODE -ne 0) { throw 'STOP: Trojaino setup failed.' }
        $Plugin = Join-Path $Prepared 'plugins\trojaino'
        $Helper = Join-Path $Plugin 'scripts\preflight.py'
        & $Python -I -S $Helper capabilities
        if ($LASTEXITCODE -ne 0) { throw 'STOP: Trojaino check failed.' }
        claude plugin validate --strict $Plugin
        if ($LASTEXITCODE -ne 0) { throw 'STOP: Claude could not check the plugin.' }
        $script:TrojainoSetup = @{ Python = $Python; Base = $Base; Plugin = $Plugin; Helper = $Helper }
        Write-Host 'SETUP FINISHED. Continue to Step 7.'
    } finally {
        $ErrorActionPreference = $OldPreference
    }
}
```

**What you should see:** several lines of technical details, followed by **SETUP FINISHED. Continue to Step 7.**

If that final line is missing, or you see an error, **stop**. Send Jose the step number and the error. Do not delete folders, repeat setup, or change security settings to make it work.

## 7. Start the small test

This creates one sample file for Trojaino to read. The test does not run that sample program.

Paste the whole box into the **same PowerShell window**:

```powershell
& {
    $OldPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Stop'
        if ($null -eq $TrojainoSetup) { throw 'STOP: Setup is not ready. Ask Jose.' }
        $Fixture = Join-Path $TrojainoSetup.Base 'fixture'
        New-Item -ItemType Directory -Path $Fixture | Out-Null
        [IO.File]::WriteAllText((Join-Path $Fixture 'hello.py'), 'print("harmless fixture")', [Text.UTF8Encoding]::new($false))
        Set-Location -LiteralPath $TrojainoSetup.Base
        Write-Host "TEST FOLDER: $Fixture"
        claude --plugin-dir $TrojainoSetup.Plugin
        if ($LASTEXITCODE -ne 0) { throw 'STOP: Claude session ended with an error.' }
    } finally {
        $ErrorActionPreference = $OldPreference
    }
}
```

Claude Code should now open **inside that window**. From here, paste the test messages into **Claude**, not into another PowerShell window.

If Claude asks whether you trust the folder, check with Jose that it is the new **TJ** folder from this guide before accepting. Do not accept a different folder. If it asks for a new login or payment, stop.

## 8. Check that Trojaino loaded

1. Type `/hooks` in Claude and press Enter.
2. Ask Jose to check that **SessionStart** and **PreToolUse** both show Trojaino’s `preflight.py` handler from the **prepared** folder. These are the two checks Claude must load.
3. Close that menu with **Escape** if needed.
4. If a check is missing, disabled, or shows an error, exit Claude. Do not keep testing just because the chat still works.

Trojaino’s startup details may be sent to Claude rather than shown as a banner. Claude saying “I am ready” is not proof that these checks loaded.

## 9. Ask Claude to scan the sample

Copy this message into **Claude** and press Enter:

> Assess the source in the fixture folder inside our current TJ folder before I try it. Use Trojaino’s report-only scan and the exact scan command from its startup instructions. Do not run, install, or modify the sample. Give me the scan result in this reply. If you cannot use native PowerShell, stop and explain. Do not work around a denial.

If Claude asks to run a command, **pause and let Jose check it**. Do not choose “always allow” or approve several actions at once. This first permission check is not something you need to judge alone.

Jose should allow only the report-only scan using the Python and prepared Trojaino paths from setup, aimed at the sample folder. Do not approve installation, running the sample, or a security bypass.

**What you should see:** a report for **one file**, with no findings, and the saved report location. It should also explain that reading code cannot prove a program is safe.

If Claude only promises to scan, asks you to install something, reports incomplete coverage, or tries to run the sample, stop. Send Jose what happened.

## 10. Check that a blocked command stays blocked

With Jose still available, paste this message into **Claude**:

> Attempt exactly one PowerShell call with command Write-Output TROJAINO_DENIAL_CANARY. If denied, report it without retrying or using other tools.

This command would only print a test word. It does not install or delete anything.

**Expected result:** Trojaino blocks the command. Ask Jose to check that the block came from Trojaino, not just from Claude’s normal permission settings. Seeing the test word quoted in Claude’s explanation is not the same as the command running.

Do not approve a new command, a workaround, or broader permissions to make this test pass. If the command actually runs, stop and report the test as failed.

## 11. Close, reopen, and finish

1. Type `/exit` in Claude and press Enter. You should return to PowerShell.
2. In that **same PowerShell window**, paste this line and press Enter:

```powershell
claude --plugin-dir $TrojainoSetup.Plugin
```

3. Repeat Step 8 with Jose to check that Trojaino loaded again.
4. Type `/exit` again. The first test is now finished.
5. Send Jose: your Windows, PowerShell, Python, and Claude versions; whether the scan worked; the saved report and receipt locations; whether Trojaino blocked the test command; whether the checks loaded again; and any error step number. A screenshot of just the error is fine. Hide passwords, sign-in codes, private files, and unrelated chats.

**Do not try Linear, Hookify, VoiceGrab, or another new app yet.** Jose will review the result and agree on the next test with you.

## If something goes wrong

| What you see | What to do |
| --- | --- |
| File not found | The download may be in another folder or have `(1)` in its name. Ask Jose; do not edit the code yourself. |
| TJ folder already exists | Stop. It may contain a previous test. Do not delete it. |
| Permission denied, path not supported, or security warning | Stop and send Jose the message. Do not use administrator mode, change execution policy, or turn off antivirus. |
| Claude wants a login, payment, or a different tool | Stop and ask Jose. Do not share sign-in details. |
| You closed PowerShell by mistake | Stop and ask Jose to help resume. Do not run the setup again. |

**To stop using this test:** exit Claude and close PowerShell. Starting Claude normally, without the special `--plugin-dir` command, does not load this test copy. Keep the TJ folder and reports until Jose has reviewed them. Do not move or rename the prepared folder or Python; that would break the setup.

---

### Notes for Jose

This guide is for a supervised first test, not unattended rollout. Verify an ordinary account and a local fixed NTFS user folder without cloud redirection, filesystem aliases, or junctions before setup. Check for already-enabled third-party plugins/MCPs before launching Claude; Trojaino does not prevent their startup. Keep the default permission mode, never bypass mode. Native PowerShell tool support and exec-form hooks must work on Sig’s actual Claude version.

The unchanged Trojaino ZIP matches reviewed runtime source at commit `7610e29a56bf85723c57de4c636ae5a56b4602d4`. Windows Server 2025 CI passed; Windows 11 desktop acceptance is still pending. An earlier intermittent Linux Node probe failure remains unexplained. Node, Git, WSL, extra Python packages, and the optional CAUTION sample are not needed for this first test. No Claude binary or third-party target app is redistributed here. Further technical detail is in `docs/windows-preflight.md` inside the ZIP.
