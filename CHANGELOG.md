# Changelog

All notable changes to Trojaino are documented here.

## 0.3.1 - 2026-09-22

- Preserve compiled-code warnings on cached scans and reject obsolete cache records.
- Recognize repeated package arguments, equals-form source options, global npm options and GitHub clone URLs.
- Ask before installs whose source or exact artifact cannot be bound, including mutable Git/plugin sources and nested shell commands. Supported Python requirement forms use the scanned artifact URL and SHA-256, not only a version.
- Detect source-selection environment/configuration overrides without exposing their values.
- Add `/trojaino:doctor`, an offline readiness and legacy-hook migration check, and a visible runtime-started message.
- Document Python prerequisites, Claude Code 2.1.274 minimum, consistent update steps and runtime packaging options.
- Validate installed plugins through the public marketplace, exercise updates, and test the supported Claude minimum and latest versions.

## 0.3.0 - 2026-09-21

Trojaino for Claude Code becomes an install gate: a normal plugin, installed with two commands inside Claude Code, that checks software before Claude installs it and stays out of the way otherwise. 0.2.0 was prepared but never published; its strict inspection-session design is replaced, not shipped.

### Install gate

- The plugin installs with `/plugin marketplace add BlockhouseSoftware/claude-marketplace` and `/plugin install trojaino@blockhouse-software`, and is active from the next session. It needs Python 3.11 or newer as `python3`.
- When Claude runs an install command (npm, npx, pnpm, yarn, bun, pip, uv, uvx, pipx, git clone, `claude mcp add`, `claude plugin install`, `claude plugin marketplace add`), Trojaino resolves the exact package, downloads it from the registry with its checksum verified, unpacks it without running anything, and scans it.
- Clean results continue, pinned to the exact version scanned, and Claude's own permission settings still apply. CAUTION results and anything that cannot be scanned (system installers, private registries, remote MCP servers, compiled code, packages over the size limits, `curl | sh`) go to the user through Claude's permission prompt with the reason. DO NOT RUN results are blocked.
- Only the named package is scanned, not its dependencies, and every result says so.
- Installing what a project already declares (`npm install`, `pip install -r requirements.txt`, `pip install -e .`) passes through untouched. Everything that is not an install passes through untouched.
- Edits to `.mcp.json`, `~/.claude.json` and Claude's plugin, MCP and hook settings are sent to the user to decide.
- Verdicts are remembered per exact package version and scanner build, so the same version is not fetched twice. Reports are kept under `~/.local/state/trojaino/reports` (Windows: `%LOCALAPPDATA%\trojaino\reports`).
- A `package` scan profile reads `dist/` and `build/`, which published npm packages routinely use for their code; the default profile still skips them.
- `/trojaino:scan` checks an npm package, PyPI package, GitHub repository or local folder without installing it.

### Removed

- The strict inspection-session mode: `tjscan setup`, the prepared per-machine plugin copy and its path binding, the receipt launcher, the restricted Node launcher, the native Windows staging backend and the `installer/friendly` setup application. None of these shipped in a published release.

### Staleness signalling

- The plugin reports its own age at session start, at most once every 30 days, and names a newer version when a marketplace catalog Claude Code has already cached advertises one. It makes no network request of its own to do this.
- A session with nothing to report no longer consumes the 30-day window.
- `tjscan check-updates` is the only command that contacts the network outside an install check, and only when run.

### Fixed

- Line endings are pinned to LF by `.gitattributes`, so byte-for-byte integrity checks agree across platforms; the repository boundary check fails on committed CRLF.
- `shipped_source_inventory` sorted by `Path`, which could produce an inventory `inventory_map` rejected.

## 0.2.0 - 2026-09-18 (not published)

Prepared and reviewed but never released. Superseded by the 0.3.0 install gate; the plugin design below was not shipped.

### Claude Code preflight plugin (experimental)

- Added `plugins/trojaino`: a model-invocable `/trojaino:scan` skill, a synchronous PreToolUse execution guard and a receipt-checking source launcher for inspection sessions. The plugin ships disabled and inert; protection requires the explicit prepared-plugin setup described in `docs/personal-plugin-delivery.md`.
- Added the sealed runtime image (`scripts/build_sealed_runtime.py`, `plugins/trojaino/scripts/preflight.py`): one self-contained entry that embeds the scanner source map, intercepts `trojaino.*` imports in memory and never falls through to disk.
- Added `scripts/prepare_preflight_plugin.py`, which binds one approved absolute Python 3.11+ interpreter and a new final destination into literal hook manifests; moved or copied preparations deny.
- Added an experimental native Windows 11 preflight backend (Win32 handles, NTFS checks, protected DACLs, Job Objects) alongside the POSIX backend.

### Windows setup (engineering preview)

- Added `installer/friendly`: a .NET Framework 4.8 WinForms setup program that stages a pinned CPython 3.14.7 embeddable runtime and reviewed source, prepares the personal plugin at its final skills-directory location, persists DPAPI-protected ownership state, and offers consented install, verify and remove actions. Not yet a distributable installer; see `docs/friendly-setup-architecture.md`.
- Added build and provenance tooling: `build_preflight_bundle.py`, `audit_setup_source.py` (Git-object byte provenance with frozen source layouts), `build_windows_setup_payload.py`, `build_setup_resources.py`.

### Marketplace

- Trojaino is distributed through the company-wide `BlockhouseSoftware/claude-marketplace` catalog (`blockhouse-software`), which references `plugins/trojaino` at a release tag. No catalog is kept in this repository.

### CI and scanner

- Added a release-profile self-scan gate on pull requests with a reviewed findings baseline (`.github/release-self-scan-baseline.json`, `scripts/check_release_self_scan.py`).
- Text-extension coverage now includes `.cs`, `.csproj`, `.iss` and `.manifest`.
- Native Windows workflows run on `main`.

## 0.1.6 - 2026-09-07

### Machine contract

- Introduced Machine Contract v1 for JSON scan reports (`schema_version: "1.0.0"`).
- Added immutable `trojaino-core` rule-pack identity and deterministic finding fingerprints.
- Published the checked-in JSON Schema at `schemas/trojaino-report-v1.schema.json`.
- Existing JSON fields and meanings remain compatible; compatible changes are additive within schema v1.

### Rule lifecycle

- Rule IDs are public, unique, and never reused. Retired rules remain documented as retired.
- A material security-meaning change receives a new rule ID and rule-pack version.

### Python packaging

- Added bounded, non-executing checks for malformed `pyproject.toml`, direct build/runtime dependency sources, extra package indexes, and module-level network access in `setup.py`.
- Advanced the `trojaino-core` rule-pack version to `1.1.0`; no verdict threshold changed.

### Verdicts

- No verdict threshold changes in this release.

### Calibration and usability

- Added a reproducible, synthetic 20-target calibration benchmark with versioned summaries and sanitized example reports.
- The Windows GUI now saves reports to a stable `Documents/TrojainoReports` folder instead of changing the default with each scan target.

### Distribution

- Added the tag-only PyPI Trusted Publishing workflow, which builds, validates, and smoke-tests the wheel and source distribution before a separately configured PyPI publish approval.

## 0.1.4.1

- Windows installer and scanner improvements.
