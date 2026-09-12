# Marketplace verification checkpoint — user-scope approval

**Historical checkpoints below:** separate local-plugin delivery was subsequently
approved and implemented; see personal-plugin-delivery.md and sig-windows-trial.md.
The old cache-copy activation gap is not solved by moving prepared bytes: the
selected route prepares directly at its final personal skills-directory location.
Current local suite: 208 tests run, OK with 12 skips before final trial packaging.
Actual isolated macOS SessionStart/enable/disable worked; model-driven testing
was blocked by expired Claude authentication. Windows acceptance stays pending.

Jose approved: “Proceed with user-scope and 3.” See marketplace-requirements.md for the exact boundary. No privileged service, publication or rollout was authorized.

## Executed locally

Host scope: macOS. Test interpreter: `/Users/kaba/trojaino/.venv/bin/python`. Claude Code: 2.1.267.

- `python -m unittest discover -s tests -q`: 203 tests, OK, 12 platform skips (latest run 15.402s). This is not Windows acceptance.
- `claude plugin validate --strict .`: passed.
- `claude plugin validate --strict plugins/trojaino`: passed.
- `git diff --check`: passed.
- CI path-coverage regression: RED identified missing catalog and marketplace documentation triggers; after adding those paths, both `tests.test_preflight_ci` tests passed. This validates workflow configuration only; no remote workflow run was performed.

## Real isolated CLI lifecycle

Evidence: `/Users/kaba/trojaino-pilot-evidence/marketplace-lifecycle.json`.
Reproduction harness: `/Users/kaba/trojaino-pilot-evidence/check_marketplace_lifecycle.py`.

All state changes used a disposable `CLAUDE_CONFIG_DIR`, empty working directory and copied local source. Normal user Claude settings were not intentionally changed. No model query or candidate activation was issued.

Verified by readback:
- Catalog add and catalog list.
- Plugin install: version 0.1.0, disabled; cached hook manifests empty.
- Disable: CLI reports already disabled with exit 1; subsequent list confirms disabled. Other errors are not accepted.
- Disposable fixture version changed to 0.1.1, catalog refreshed, plugin updated: new version appears and remains disabled.
- Uninstall: plugin list empty.
- Catalog removal: marketplace list empty.

Fixture 0.1.1 is not a published product version. Temporary directories were removed after the test.

## Review corrections

The first lifecycle run actually used source version 0.1.6 and fixture target 0.1.1. It proved a version change/downgrade, not the forward update originally described. The original log is preserved at `/Users/kaba/trojaino-pilot-evidence/marketplace-lifecycle-original-downgrade.json`. The corrected harness pins and asserts the disposable starting version 0.1.0 and target 0.1.1; the rerun passed and its readbacks are in `marketplace-lifecycle.json`. Neither fixture version changes production metadata.

A copied-hook regression was independently reproduced locally: its literal command still ran the original entry despite a different advertised `CLAUDE_PLUGIN_ROOT`. The new regression failed with exit 0 instead of 2 before the fix. The generated prepared entry now rejects a supplied plugin root that differs from its bound root before loading the runtime. Correct-root execution and mismatched-root denial both pass. Missing environment remains supported for explicit standalone CLI use; this check is not authentication against a malicious same-user process. Windows path spelling and actual Claude environment propagation remain unqualified.

After that fix: 204 tests ran, OK, 12 skipped (15.949s). Independent re-review of this new check is still required. Earlier 203-test results above describe the prior checkpoint, not the current test count.

## Not complete

The private prepared runtime deliberately rejects moved paths. Ordinary marketplace caching copies plugin files. An approved, verified activation handoff between those two mechanisms is still missing; the old `--plugin-dir` pilot does not close this gap. The developer lifecycle guide explicitly stops before unsafe activation.

Independent read-only re-review found no new defect in the supplied-root rejection under the approved user-scope boundary and independently reproduced 204 passing tests with 12 skips, both strict manifest checks and the whitespace check. This closes that specific correction's review, not overall marketplace acceptance. Review evidence: `/Users/kaba/.hermes/cache/delegation/subagent-summary-0-20260911_195953_268446.txt`.

The proposed command-source link-mode activation route is not suitable for the Windows target: the official command-source documentation explicitly says Windows refuses link-mode installation. On macOS it still constructs a cache entry containing links; compatibility with the unchanged root binding is not established. Do not implement it as a Windows solution or bypass root checks. Source: https://code.claude.com/docs/en/plugin-marketplaces#command-sources .

Native Windows 11 ordinary-account testing, a supported prepared-runtime activation design, actual Claude hook transport/UI checks, immutable release binding and publication approval remain separate gates.
