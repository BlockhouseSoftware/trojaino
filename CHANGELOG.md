# Changelog

All notable changes to Trojaino are documented here.

## 0.2.0 - 2026-09-18

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
