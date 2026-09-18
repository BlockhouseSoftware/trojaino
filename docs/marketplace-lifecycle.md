# Blockhouse Software marketplace: install, check, update and remove

**Developer acceptance guide.** Native Windows 11 testing and the prepared-runtime activation handoff are release gates. Installing the catalog does not enable protection.

## Security boundary

This is a user-scope inspection tool. Your account, approved Python and reviewed setup files must already be trusted. It does not protect itself from malicious software already running as you, an administrator, or a compromised operating system. A clean scan is not a promise that software is safe. Do not run candidate code during setup.

## Before starting

Use native Claude Code. Commands below run in a terminal, not in the Claude conversation. The catalog lives at `https://github.com/BlockhouseSoftware/claude-marketplace`; for offline developer testing, substitute the absolute path of a reviewed local clone.

For isolated developer testing, set `CLAUDE_CONFIG_DIR` to a new disposable absolute directory and run from an empty working directory. Do not change your usual Claude configuration. The CLI stores settings and plugins in that directory. No login or model query is required for this local catalog test.

## 1. Add the catalog

```text
claude plugin marketplace add BlockhouseSoftware/claude-marketplace --scope user
claude plugin marketplace list --json
```

Expected: `blockhouse-software` appears. Adding a catalog does not install its plugins.

## 2. Install the disabled plugin

```text
claude plugin install trojaino@blockhouse-software --scope user
claude plugin list --json
```

Expected: `trojaino@blockhouse-software` appears with `enabled: false`. Its unprepared `hooks/hooks.json` must contain `{"hooks": {}}`. There is no active scanner gate yet. Do not enable this cached copy as a substitute for setup.

In the interactive Claude terminal, `/plugin` should show the installed plugin as disabled. Check its Errors tab. Any error is a stop condition.

## 3. Check setup status

If there is no trusted command supplied by a prepared plugin's SessionStart message, setup is incomplete. Stop. Do not guess a Python path, install dependencies or try a candidate MCP. The `/trojaino:scan` skill instructs the agent to stop when that context is missing; it is not an executable setup command.

The reviewed setup helper accepts a new absolute destination when invoked with an explicitly approved absolute Python 3.11+ executable and `-I -S`. It produces a private copy with literal hooks and path bindings (see [personal-plugin-delivery.md](personal-plugin-delivery.md)). It does not activate that copy globally.

**Integration boundary:** preparation creates a separate private plugin copy at its final skills-directory location. Claude marketplace installation copies plugins into a cache, and prepared bindings intentionally reject moved entries. Do not copy a prepared entry into the cache, edit its binding, or claim ordinary marketplace installation completes activation.

## 4. Disable

```text
claude plugin disable trojaino@blockhouse-software --scope user
claude plugin list --json
```

Expected: `enabled: false`. Claude Code returns exit code 1 and says `already disabled at user scope` when the plugin was already disabled. That specific message is harmless; do not ignore other errors. Restart any existing Claude inspection session before assuming its loaded hooks changed. A separate `--plugin-dir` session is not disabled by changing the catalog plugin setting: close that session separately.

## 5. Update deliberately

First disable the plugin and close inspection sessions. Review the new release and its tag before using it. Keep automatic updates off for this experimental marketplace.

```text
claude plugin marketplace update blockhouse-software
claude plugin update trojaino@blockhouse-software --scope user
claude plugin list --json
```

Expected: the reviewed new version appears and remains disabled. The publisher bumps the plugin version and the catalog's pinned tag together. Refreshing a catalog alone is not a plugin update. Restart Claude after updates. A runtime change invalidates old scan receipts: rescan. Do not reuse or overwrite a previous prepared directory; create a fresh one through the reviewed setup flow. Never edit cached executable paths to bypass a moved-binding denial.

## 6. Remove

Close inspection sessions first.

```text
claude plugin uninstall trojaino@blockhouse-software --scope user
claude plugin list --json
claude plugin marketplace remove blockhouse-software --scope user
claude plugin marketplace list --json
```

Expected: the plugin is absent, then the catalog is absent. These commands do not remove your candidate source or independently prepared private layouts. Retain scan evidence as needed; do not automate deletion of paths reported by an untrusted candidate. No blanket filesystem cleanup is part of this guide.

## Pending checks

Still required before rollout: prepared-runtime marketplace activation, native Windows 11 ordinary-account permissions and process checks, real `/plugin` Errors-tab observations, and final acceptance review.

## References

- https://code.claude.com/docs/en/plugin-marketplaces
- https://code.claude.com/docs/en/discover-plugins
- https://code.claude.com/docs/en/settings
- Installed CLI help: `claude plugin install --help`, `update --help`, `disable --help`, `uninstall --help`, `marketplace --help`.
