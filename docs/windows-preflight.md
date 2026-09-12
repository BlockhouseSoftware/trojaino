# Native Windows 11 preflight pilot

**Current trial:** use [Sig’s Windows trial guide](sig-windows-trial.md) for the
separate prepared personal-plugin route. The `--plugin-dir` commands below are
legacy engineering reference, not the current marketplace handoff. Do not mix
the two installation or removal procedures.

**Implemented, experimental, not Windows-validated in this development environment.**
The Win32 acceptance tests must run on a real Windows host before rollout. macOS
unit tests, a real PowerShell run on macOS, and Claude manifest validation do not
prove NTFS behavior or authenticated Windows Claude integration.

This is an inspection workflow, not antivirus or an OS sandbox. Do not start
Claude in an unreviewed checkout, load candidate native plugins, register their
MCP servers, install dependencies, or supply credentials to inspect source.

## Prerequisites

- Native Windows 11, ordinary non-elevated account, **local fixed NTFS** volume.
  UNC/network/removable drives, ReFS/FAT, WSL paths, device paths, junctions,
  symlinks, cloud placeholders and 8.3 aliases are deliberately unsupported.
- A trusted CPython **3.11+ `python.exe`**, architecture matching the host. Use a
  patched python.org runtime or a reviewed organization's runtime. No packages,
  pip, Git Bash, POSIX emulation or system-wide configuration changes are needed.
  The existing Trojaino scanner EXE/installer is **not** this plugin's interpreter.
- Current native Claude Code supporting command hooks with an `args` array.
  Exec form does **not** support `${env:NAME}` interpolation. Preparation below
  writes a literal absolute interpreter and args. Update through your approved
  channel when that schema is unsupported; never drop `args` into shell mode.
- PowerShell tool availability in Claude for the no-Git-Bash workflow. Current
  Claude supports native PowerShell; check `/help` and `/hooks` on the actual
  installation. If this tool is absent, stop and correct Claude setup rather than
  pretending a Bash command runs in PowerShell. Git Bash is optional, not required
  by the hook or scanner.
- Optional Node: explicitly trusted absolute `node.exe` supporting enforced
  `--permission`. Every launch probes it. Flags are never removed as a fallback.

References: [Claude hooks](https://code.claude.com/docs/en/hooks),
[Claude setup](https://code.claude.com/docs/en/setup).

## Private, portable distribution

Keep the complete trusted source layout, not just `plugins/trojaino`. The helper
imports `trojaino/` relative to that layout, never candidate cwd or PYTHONPATH.
From a reviewed checkout, build an allowlisted, source-only archive:

```powershell
& 'C:\Trusted\Python311\python.exe' 'C:\Trusted\trojaino\scripts\build_preflight_bundle.py' 'C:\Private\trojaino-preflight-source.zip'
Get-FileHash -Algorithm SHA256 -LiteralPath 'C:\Private\trojaino-preflight-source.zip'
```

The builder emits the ZIP SHA-256 and a per-file `MANIFEST.sha256.json` inside the
archive. It refuses to overwrite an existing archive. It includes scanner source,
plugin metadata/scripts/skill, license and setup docs; not `.git`, `.venv`, caches,
evidence or credentials. The ZIP is not signed and an internal manifest is not
an authenticity proof: compare its external hash through a trusted independent
channel before extracting. No artifact is published by this command.

Extract to a short, local, user-owned directory (e.g. under your own `Tools`
folder). A separately verified python.org Windows embeddable runtime can be used
as the explicit interpreter for a no-install deployment; do not copy a macOS
venv or claim the source ZIP contains Python. Do not enable site imports or
install candidate dependencies into the trusted runtime. Use the full checkout
when running the development test suite; the small runtime ZIP omits tests.

## Start without global settings changes

Use your **actual** paths in a trusted PowerShell terminal; these are examples:

```powershell
$env:TROJAINO_PYTHON = 'C:\Users\Alice\Tools\Python311\python.exe'
$repo = 'C:\Users\Alice\Tools\trojaino-source'
$prepared = 'C:\Users\Alice\Tools\trojaino-prepared'
& $env:TROJAINO_PYTHON -I -S (Join-Path $repo 'scripts\prepare_preflight_plugin.py') $prepared
# Stop on any preparation error. Destination must be NEW, under a trusted parent.
$helper = Join-Path $prepared 'plugins\trojaino\scripts\preflight.py'
$plugin = Join-Path $prepared 'plugins\trojaino'
# Optional:
$env:TROJAINO_NODE = 'C:\Program Files\nodejs\node.exe'

& $env:TROJAINO_PYTHON -I -S $helper capabilities
claude --version
claude plugin validate --strict $plugin
claude --plugin-dir $plugin
```

The raw source hook manifest is an **unconfigured template**: never load it
directly. Preparation uses the running Python's absolute `sys.executable`, not
environment interpolation, and preserves the complete trusted import layout.
Keep the prepared directory at its exact path; reprepare after moving it or
changing Python. Never load partial output after an error. Preparation creates
a protected TokenUser/SYSTEM directory on Windows and mode 0700 on POSIX;
the existing parent must be trusted and user-owned. It does not secure against
same-user/admin tampering. The bundle includes both preparation and build helpers.

These terminal setup commands are not the canonical tool-call spelling used
inside the guarded session. No `Set-ExecutionPolicy`, profile edits, credential
changes or global plugin registrations are required. Hooks launch the configured
Python executable with a literal argument array, without `sh`, `bash`, `cmd` or
PowerShell wrapping. This transport is independent of the execution tool;
authenticated Claude integration on each host still requires verification.

**Stop if SessionStart context is absent**, hook errors appear, or `/hooks` does
not show synchronous SessionStart and PreToolUse handlers. Missing interpreter,
missing files, old schema and host failures can prevent hooks starting; host
errors are not a reliable fail-closed boundary. Independent launcher checks are
still required. `capabilities` reports actual host/interpreter and command
prefixes, but explicitly does not claim a filesystem or authenticated-Claude test.

## Canonical calls inside Claude

SessionStart supplies the actual trusted prefix. For PowerShell, the only
accepted grammar is ampersand plus **every argument single-quoted**, separated by
one space; double an embedded apostrophe. Use single quotes even around `-I`,
`-S`, `scan`, `launch` and options:

```powershell
& 'C:\Trusted\Python\python.exe' '-I' '-S' 'C:\Trusted\trojaino-source\plugins\trojaino\scripts\preflight.py' 'scan' 'C:\Intake\O''Brien project' '--state' 'C:\Users\Alice\tj-state'
```

Read/report that result first. Only for a separately requested clean launch:

```powershell
& 'C:\Trusted\Python\python.exe' '-I' '-S' 'C:\Trusted\trojaino-source\plugins\trojaino\scripts\preflight.py' 'launch' 'C:\Users\Alice\tj-state\scan-ID\report.json' '--entry' 'server.py'
```

Use the actual receipt path, not `scan-ID`. No variables, double-quoted strings,
subexpressions, pipelines, redirection, extra statements, newlines, backgrounding,
profiles or arbitrary interpreter flags are accepted. Typographic quotes
U+2018 through U+201F are rejected, even inside path arguments. Metacharacters inside
literal path arguments remain data. For the optional Bash tool, use its startup
prefix (forward-slash Windows executable/helper paths) and exact `shlex.join`
quoting, **not PowerShell spelling**. Hook authorization never evaluates a shell
string. Both grammars preserve normal Claude permissions on supported calls.

## Windows boundary details

- Validate raw names before normalizing: reject ADS colons, reserved DOS devices
  (including extension aliases), trailing dots/spaces, traversal, control
  characters, wildcard characters, malformed drive paths, surrogates, paths of
  240 or more UTF-16 units, and components over 255 UTF-16 units, before native
  I/O. Keep source/state paths short; nested staged paths count too.
- Hold every source/state ancestor using native handles without delete/write
  sharing; open the final component with `FILE_FLAG_OPEN_REPARSE_POINT` and
  inspect the handle. Reject all reparse types, hardlinked files, offline/recall
  attributes and named streams on files **and directories**. Failed stream,
  filesystem, sharing, token or security-descriptor queries deny; no lstat-only
  or POSIX-flag fallback exists. Normal read sharing remains allowed.
- New job/stage directories receive protected DACLs granting full access only
  to the process TokenUser SID and SYSTEM, with inheritable child ACEs. Existing
  ancestors are validated, not recursively chmodded or re-ACLed. Administrators
  and same-user tampering remain outside this pilot's security boundary.
- Source copies use native exclusive creation and bounded reads. Archive names
  are rejected before extraction, including implicit parent case/Unicode aliases.
- Windows hook stdin parsing, scans and launch planning run in trusted isolated
  workers with a 20-second parent deadline. Workers join kill-on-close Job
  Objects before starting descendants; failed job assignment aborts. Termination
  closes the job and kills descendants. Scanner deadline remains 10 seconds;
  the scanner's internal budget remains 8 seconds. Hook host deadline is 30.
- Windows child launch preserves stdin/stdout and emits the receipt to stderr.
  It is bounded to **300 seconds**, unlike POSIX process replacement. It is a
  short inspection launch, not an indefinitely running production MCP daemon.
  Job cleanup applies on launcher exit. Node still receives only scanned-tree
  reads and no addon/write/child-process permission grants.
- Reports and generated snapshots are intentionally retained for review. A
  timeout can leave a partial job without a valid receipt; it cannot authorize
  launch. Temporary output handles close and child processes are terminated.
  Exit all inspection/launcher processes before removing only generated `scan-*`
  folders you no longer need. Do not treat partial folders as passing reports.
  The default state directory remains `~/.local/state/trojaino-pilot` for receipt
  compatibility; `--state` may select a shorter private local NTFS location.

## Native verification before rollout

From a trusted full checkout, with Python and a patched compatible Node on PATH:

```powershell
& $env:TROJAINO_PYTHON -m unittest discover -s tests -v
& $env:TROJAINO_PYTHON -m unittest discover -s tests -p test_preflight_windows.py -v
```

Native tests cover real scan/receipt/launch, directory and file ADS, junctions
(including ancestors/state), hardlinks, file write/rename exclusion, DACLs,
blocked stdin timeout, job descendant termination, PowerShell invocation and
restricted Node sibling/ambient dependency behavior. Non-Windows runs skip these
explicitly; simulated platform flags are not acceptance evidence. Older POSIX
fault-injection tests stay POSIX-only. Cross-platform grammar, archive, worker,
bundle and plugin tests run independently. CI configuration is not a CI result.

Then run a real authenticated Windows Claude session, without registering target
MCPs: verify automatic skill selection, report delivery before a separate
launch, ordinary install/PowerShell/Bash denial, normal permission behavior,
clean child stdio, malformed hook input, missing-runtime behavior and restart.
Capture OS, Python, Claude and Node versions plus command output. Do not label
this ready for end users until the Win32 and live-Claude evidence exists.

Removal: exit Claude and restart without `--plugin-dir`; remove only environment
variables you set in that terminal. This setup does not install global hooks.
