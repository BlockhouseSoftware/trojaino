# Trojaino for Claude Code — preflight pilot 0.1.0

**Experimental, repository-local inspection mode. Not a universal execution firewall.**

This plugin connects the existing local Trojaino scanner to a controlled Claude Code intake session. When asked to try a new MCP server, plugin, or app, Claude can invoke the scan skill automatically. A synchronous hook rejects execution and activation outside the narrow helper workflow. A separate launcher rechecks a receipt before starting supported source.

The intended sequence is **stage → scan → report to Claude → separately requested launch**. The scanner and hook never execute the candidate. A passing scan does not override Claude permissions or certify safety.

## Requirements and tested scope

- Trusted full Trojaino source checkout containing this plugin, Python **3.11+**, and Claude Code with plugin/hook support.
- POSIX backend tested on **macOS**, not yet exercised on Linux. The experimental **native Windows 11** backend uses Win32 handles, NTFS checks, protected DACLs and Job Objects; [Windows setup and verification](../../docs/windows-preflight.md). Its native acceptance tests have not run on this macOS development host. The scanner contract remains unchanged.
- Local absolute source directories, or exact public GitHub URLs of the form `https://github.com/OWNER/REPO/tree/FULL_40_LOWERCASE_HEX_SHA`.
- Launchable entries: `.py`, `.js`, `.cjs`, `.mjs`. Python runs with isolated imports, scanned local modules and the standard library; no site-packages or extra script arguments.
- Optional Node launching requires an explicitly trusted absolute `TROJAINO_NODE` path and an enforcing stable `--permission` capability. Tested with **Node 26.8.1**; unsupported runtimes fail closed. Use a currently patched runtime, not merely the oldest version with that flag.
- Node receives only a read grant for its scanned tree, no additional permission grants. Ordinary ambient dependencies outside that tree are denied. Programs needing external files, writes, native addons, subprocesses, workers, or other restricted capabilities can fail at runtime. Network behavior varies with Node's permission implementation; the tested runtime denies it without an explicit grant. No fallback removes these restrictions.

The core is still Trojaino's heuristic static scanner. It cannot establish complete language, dependency, malware, or runtime safety coverage.

## Load without changing global Claude settings

Keep the plugin **inside its original full trusted checkout** or the equivalent reviewed source-only bundle layout. The portable builder is `scripts/build_preflight_bundle.py`; see the Windows guide. This pilot intentionally does not support copying the plugin alone, marketplace caching, or installing it from PyPI. There is no official Trojaino PyPI package.

First identify your trusted absolute interpreter and checkout paths. Substitute real paths below; the placeholders are not runnable values:

```sh
/absolute/path/to/python3.11 -I -S /absolute/path/to/trojaino/scripts/prepare_preflight_plugin.py /absolute/private/new-trojaino
# Optional, for restricted Node launches:
export TROJAINO_NODE=/absolute/path/to/node

claude plugin validate --strict /absolute/private/new-trojaino/plugins/trojaino
claude --plugin-dir /absolute/private/new-trojaino/plugins/trojaino
```

Launch Claude in an existing **trusted workspace**, never inside an unreviewed candidate checkout. At startup the plugin supplies Claude with the trusted helper/interpreter command prefix. In Claude, inspect `/hooks` to confirm `SessionStart` and `PreToolUse` registration and `/help` to find `trojaino:scan`. If startup context is absent or a hook error appears, stop and correct setup; do not assume protection is active.

The raw source manifest is an **unconfigured template**, not directly loadable. Preparation creates a new private complete source layout and writes the running trusted Python's literal absolute `sys.executable` into both hooks, with literal argument arrays. Claude exec form does not expand `${env:TROJAINO_PYTHON}`. No shell bootstrap or global settings edits are used. Choose a new absolute destination under a trusted user-owned parent (no symlink ancestors); existing destinations are refused. Keep the full prepared layout at that exact path and reprepare after a move or interpreter change. Partial preparation output must not be loaded. The legacy `hook.sh` remains only for POSIX compatibility tests, not registration. Missing-runtime host errors can fall through: stop if startup confirmation is absent. Actual authenticated host integration still requires independent testing.

This mode intentionally blocks ordinary Bash/PowerShell execution and writes, not just recognizable `npm install` strings. Use it for new-software intake, **not as an invisible global add-on to all coding sessions**. Leave the session and restart Claude without `--plugin-dir` for normal development. No global configuration is modified by loading this way.

## Use

Ask Claude, for example:

> Inspect this new MCP before we try it: /absolute/path/to/downloaded-source

Or invoke explicitly:

```text
/trojaino:scan /absolute/path/to/downloaded-source
```

For GitHub, supply an exact full-commit tree URL. A branch, tag, abbreviated hash, registry name, remote MCP endpoint, or installer URL is not accepted. Resolving an intended version is separate from executing it; never use `npx`, `uvx`, pip installation, build steps, or target project hooks to acquire source for inspection.

The skill makes a report-only helper call and reads its JSON before proposing execution. The summary includes the decision, scanner verdict, content digest, scanner/rule identity, and report locations. `scanner_report_path` contains the full scanner JSON with file/line/redacted evidence; source-derived strings remain untrusted data, not instructions.

| Outcome | Automatic route |
| --- | --- |
| NO CRITICAL RISKS FOUND with complete supported coverage | May propose a separate launch; normal Claude permissions remain in force |
| CAUTION / DO NOT RUN | Block; stop for human review |
| Incomplete, unsupported, changed, error, or timeout | Block; no passing fallback |

There is no human-override command in this pilot. Do not delete inconvenient files, select the release profile, or disable hooks merely to obtain a pass. Review exceptional cases outside the automatic route.

## Helper and MCP stdio launcher

These are the underlying commands, with real absolute paths substituted:

```sh
/absolute/python -I -S /absolute/trojaino/plugins/trojaino/scripts/preflight.py scan /absolute/source --state /absolute/private/state
/absolute/python -I -S /absolute/trojaino/plugins/trojaino/scripts/preflight.py launch /absolute/receipt/report.json --entry server.py
```

The scan command writes JSON to stdout; exit 0 means the source gate permits proceeding within normal permissions, exit 2 means deny. The helper uses its trusted checkout rather than importing from the candidate working directory or `PYTHONPATH`.

The launcher verifies the receipt and scanner identity, creates and scans a fresh snapshot, checks the digest, emits its scan result to **stderr**, then starts exact runtime argv (POSIX process replacement; Windows job-contained subprocess with a 300-second lifetime ceiling). **Stdout and stdin are reserved for the child/MCP protocol.** A denied launch exits 2 with empty stdout. A permitted child can still fail with its own runtime exit code and stderr, including Node `ERR_ACCESS_DENIED` for an external dependency. A scan verdict is not a claim that runtime startup succeeded.

For a subsequently approved local MCP configuration, the command can be the trusted Python executable and the args can be the fixed helper `launch` invocation with an existing receipt. Configure that separately only after review; this plugin does not automatically edit native MCP configuration or grant credentials. Do not register a candidate's original `npx`/`uvx` startup command under the assumption that a first-tool-call hook will protect earlier startup.

Commands inside the inspection session must match their tool grammar: Bash uses `shlex.join`; PowerShell uses `&` followed by every argument single-quoted, doubling embedded apostrophes. See the Windows guide for exact examples. Both grammars require canonical spelling, with no environment prefixes, variable expansion, shell chains, redirections, or arbitrary interpreter flags. This strict grammar is deliberate. Use the startup-provided command prefix rather than inventing a shell wrapper.

## Coverage and security boundaries

- Independently inventories staged bytes and rejects links, special files, invalid text, empty/unsupported coverage and unexplained scanner omissions. Ignored directories such as `dist`, `build`, `node_modules`, `.venv`, and `.git` are not silently approved. Ordinary cloned repos containing `.git`, binary assets, compiled output or dependencies can therefore be denied. The policy is conservative; it is not a finding of malware.
- Public GitHub acquisition uses HTTPS to a fixed host, full commit IDs, no proxy inheritance or redirects, bounded download/decompression, and validation before writing archive members. Traversal, links, duplicate/case-colliding names and resource-limit violations are rejected. No target install/build/Git hooks run.
- Default ceilings include 5,000 files, 20,000 entries, 1 MB per file and 20 MB total staged file bytes. Scanner worker timeout is 10 seconds with an internal 8-second scan budget; the helper has a 20-second POSIX signal watchdog or native Windows killable worker,  below the configured 30-second host hook timeout. Large or binary-rich projects may be unsupported by this pilot.
- Receipts bind content and scanner/rule implementation identity; every launch independently rescans. Forging a passing verdict in a receipt does not bypass the fresh scan. Receipts do **not** cryptographically prove that a human or model read/understood a report.
- The report-first ordering is a two-call workflow. `PreToolUse.additionalContext` accompanies a tool result, so it is **not** evidence that Claude saw a scan before that same call executed. Direct standalone use of the launcher cannot prove prior report delivery to an agent.
- **Hooks are not fail-closed infrastructure:** a host timeout, missing hook file or host failure to start it can fall through normal Claude permissions. Controlled errors return explicit denial, but independent launcher validation remains necessary. Plugin disabling/reloading and same-user edits can bypass the integration.
- Native plugin loading, existing MCP startup, other terminals, browser/OS installers, other execution surfaces and a compromised trusted runtime are not universally intercepted. The prehook covers the named execution/write tools in `hooks/hooks.json`; it does not provide OS mediation.
- Node permissions reduce ordinary ambient dependency loading; they are **not an OS sandbox against intentionally malicious launched code**. Python launching is likewise not a sandbox. Same-user tampering and the final check-to-execution race remain outside this pilot's guarantees.
- Private registries, package installation, dependency auditing, binary/app installers, container images, remote MCP services, TypeScript execution/transpilation, extra runtime arguments and credentials are not implemented.
- Reports and snapshots remain on disk under the selected state directory (default `~/.local/state/trojaino-pilot`). The pilot does not upload them or automatically prune them. They can contain sensitive source/evidence; protect the directory and remove only its generated scan directories when no longer needed. Revalidation creates additional snapshots.

## Verification and rollout status

Run from the trusted repository with a Python 3.11+ environment containing the test requirements:

```sh
python -m unittest discover -s tests -v
claude plugin validate --strict plugins/trojaino
```

Tests cover non-execution markers, real scanner results, dangerous lifecycle scripts, receipts and mutation, malformed input, scanner timeouts, archive attacks, report storage, hook decisions, startup context, Python stdio/local imports, and restricted Node imports. POSIX fault-injection tests remain POSIX-only. New native Win32 tests are explicitly skipped off Windows; portable tests run on both. Node tests need a compatible installed runtime. A PowerShell transport run on macOS does not count as Win32 execution.

Local helper/stdio tests and plugin structural validation are **not an authenticated Claude integration test**. Before offering this as an enabled workflow on a user's machine, test a real authenticated session: automatic skill selection, prior report delivery, attempted install denial, clean separate launch, normal permission behavior and restart/reload behavior. Verify the user's OS and runtime versions. Do not label the pilot production-ready based on manifest validation alone.

## Removal

Exit the inspection session and start Claude without `--plugin-dir`. Remove only the environment variables you added if no longer needed. This repository-local loading method creates no global plugin registration to uninstall. Keep any receipts needed by separately configured gated MCP launchers; deleting a receipt intentionally prevents its next startup.

License: AGPL-3.0-only, as in the repository root LICENSE.
