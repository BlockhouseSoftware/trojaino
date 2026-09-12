# Prepared personal plugin — developer checkpoint

For the current supervised handoff, follow [Sig’s Windows trial guide](sig-windows-trial.md).
The sections below preserve earlier checkpoint evidence, not current blanket
activation prohibitions. The trial explicitly enables only the reviewed plugin
in a separate configuration; Windows and model-driven acceptance remain tests.
Actual macOS SessionStart dispatch plus enable/disable readbacks were subsequently
observed with Claude 2.1.267 in an isolated configuration. Model execution was
blocked by expired login; no authenticated scan/report result is claimed.

Jose approved a separate prepared local plugin, retaining all security safeguards and the Windows release gate. This is not a released Sig guide.

## Explicit preparation

Invoke the reviewed `scripts/prepare_preflight_plugin.py` with an explicitly approved absolute Python 3.11+ path and `-I -S`, supplying a NEW absolute final destination and `--personal-plugin-name trojaino-local-RELEASE-ID`. Replace RELEASE-ID with a distinct lowercase kebab-case identifier for each prepared version. The destination for personal discovery is a fresh directory directly under the user's Claude `skills` directory (or an isolated test configuration's `skills` directory).

The destination basename must equal the personal plugin identity. This prevents two differently named sibling directories produced by this helper from advertising one identity, while exclusive creation prevents reusing the same sibling destination. This is not a global registry: manually authored conflicting plugins or another skills root require separate operator review. Use one approved personal skills root and a new identity for each release.

The helper writes the complete self-contained plugin directly at that final path. It does not alter settings, register a marketplace, enable the plugin, select Python through PATH, or overwrite an existing directory. The manifest is disabled by default. Never move or copy the resulting prepared plugin; reprepare at a new final destination instead.

The marketplace copy remains disabled. The prepared plugin has a separate identity: `trojaino-local-RELEASE-ID@skills-dir`. Marketplace uninstall does not disable or remove this local plugin.

## Separate lifecycle

- Inspect: `claude plugin list --json`. Confirm the exact local identity, final path and `enabled: false` before any activation.
- Activation is NOT qualified yet. Do not treat direct execution of test hook arguments as real Claude hook dispatch evidence.
- Disable using `claude plugin disable trojaino-local-RELEASE-ID@skills-dir`, then verify with plugin list. Close/restart existing inspection sessions; loaded hooks may persist until reload/restart.
- Updates require a fresh directory and distinct identity. Explicitly disable the old identity before activating a reviewed replacement. Never overwrite an existing prepared tree.
- Removal is not marketplace uninstall. Disable the local identity, close its sessions, and remove only the exact user-approved prepared directory after retaining desired evidence. No automatic broad filesystem deletion is provided.

## Verification

Observed RED: the new final-layout test failed because `--personal-plugin-name` was unrecognized. After implementation, the focused test passed and the full suite ran 205 tests, OK with 12 platform skips. The test checks disabled metadata, literal final binding, correct-root success, wrong-root denial and existing-destination refusal.

Real Claude Code 2.1.267 in a disposable macOS `CLAUDE_CONFIG_DIR` discovered `trojaino-local-001@skills-dir`, version 0.1.6, user scope, disabled, at the exact prepared final location. Strict validation of that generated plugin passed. Temporary configuration was removed; normal user plugin configuration was not changed. No activation/model session was run.

## Independent packaging and inactive-lifecycle acceptance

Independent review passed the README transformation fixes using full temporary source fixtures: CRLF and bare-CR inputs prepare successfully; missing, duplicate and reversed section boundaries reject before creating any destination. The latest local full regression run was 208 tests, OK with 12 platform skips; this independent lifecycle review did not rerun the full suite.

Evidence read back by Alpha: `/Users/kaba/trojaino-pilot-evidence/personal-lifecycle-review-19cc563acb454798839e1c388f3ecd38.txt`.

Real Claude Code 2.1.267 in disposable macOS configurations verified version-distinct prepared plugins (fixture versions 0.1.6 and 0.1.7), exact final paths, disabled discovery, strict validation, explicit disable and settings readbacks. Removing only the old disposable plugin left the new one discoverable, disabled and byte-identical. The fixture 0.1.7 is not a release. This establishes inactive side-by-side replacement and removal, not updating a running session or active hook dispatch.

Real hook dispatch, enabled-session disable/reload behavior, native Windows discovery and path spelling/permissions/process checks remain required. No release, publication or rollout is authorized.
