# Blockhouse Marketplace: install, check, update and remove

**Developer acceptance guide, not a released Sig setup guide.** Native Windows 11 testing and the prepared-runtime activation handoff are still release gates. Do not give an unpublished repository URL to users or claim that installing the catalog enables protection.

## Security boundary

This is a user-scope inspection tool. Your account, approved Python and reviewed setup files must already be trusted. It does not protect itself from malicious software already running as you, an administrator, or a compromised operating system. A clean scan is not a promise that software is safe. Do not run candidate code during setup.

## Before starting

Use native Claude Code. These commands were exercised with Claude Code 2.1.267 on macOS, not qualified on Windows 11. Commands below run in a terminal, not in the Claude conversation. Replace `ABSOLUTE_REVIEWED_MARKETPLACE_DIRECTORY` with the actual absolute path to the reviewed marketplace directory. This local path is intentional: there is no approved public release URL yet.

For isolated developer testing, set `CLAUDE_CONFIG_DIR` to a new disposable absolute directory and run from an empty working directory. Do not change your usual Claude configuration. The CLI stores settings and plugins in that directory. No login or model query is required for this local catalog test.

## 1. Add the catalog

```text
claude plugin marketplace add "ABSOLUTE_REVIEWED_MARKETPLACE_DIRECTORY" --scope user
claude plugin marketplace list --json
```

Expected: `blockhouse-tools` appears. Adding a catalog does not install its plugins.

## 2. Install the disabled plugin

```text
claude plugin install trojaino@blockhouse-tools --scope user
claude plugin list --json
```

Expected: `trojaino@blockhouse-tools` appears with `enabled: false`. Its unprepared `hooks/hooks.json` must contain `{"hooks": {}}`. There is no active scanner gate yet. Do not enable this cached copy as a substitute for setup.

In the interactive Claude terminal, `/plugin` should show the installed plugin as disabled. Check its Errors tab. Any error is a stop condition. This UI expectation still needs direct native-Windows verification; CLI manifest validation is not a substitute.

## 3. Check setup status

If there is no trusted command supplied by a prepared plugin's SessionStart message, setup is incomplete. Stop. Do not guess a Python path, install dependencies or try a candidate MCP. The existing `/trojaino:scan` skill instructs the agent to stop when that context is missing; it is not an executable setup command.

The reviewed setup helper accepts a new absolute destination when invoked with an explicitly approved absolute Python 3.11+ executable and `-I -S`. It produces a private copy with literal hooks and path bindings. It does not activate that copy globally.

**Unresolved integration gate:** preparation currently creates a separate private plugin copy. Claude marketplace installation copies plugins into a cache, whereas prepared bindings intentionally reject moved entries. Do not copy a prepared entry into the cache, edit its binding, or claim ordinary marketplace installation completes activation. The supported, tested activation handoff must be finalized before a Sig-facing release guide is published. The earlier `--plugin-dir` pilot is not evidence that marketplace activation works.

## 4. Disable

```text
claude plugin disable trojaino@blockhouse-tools --scope user
claude plugin list --json
```

Expected: `enabled: false`. Claude 2.1.267 returns exit code 1 and says `already disabled at user scope` when the plugin was already disabled. That specific message is harmless; do not ignore other errors. Restart any existing Claude inspection session before assuming its loaded hooks changed. A separate `--plugin-dir` session is not disabled by changing the catalog plugin setting: close that session separately.

## 5. Update deliberately

First disable the plugin and close inspection sessions. Review the new release and its immutable source reference before using it. Keep automatic updates off for this experimental marketplace.

```text
claude plugin marketplace update blockhouse-tools
claude plugin update trojaino@blockhouse-tools --scope user
claude plugin list --json
```

Expected: the reviewed new version appears and remains disabled. The publisher must bump the plugin and catalog versions together. Refreshing a catalog alone is not a plugin update. Restart Claude after updates. A runtime change invalidates old scan receipts: rescan. Do not reuse or overwrite a previous prepared directory; create a fresh one through the reviewed setup flow. Never edit cached executable paths to bypass a moved-binding denial.

Developer evidence uses a disposable local fixture changing 0.1.0 to 0.1.1. That is not a published release or a claim that 0.1.1 is available.

## 6. Remove

Close inspection sessions first.

```text
claude plugin uninstall trojaino@blockhouse-tools --scope user
claude plugin list --json
claude plugin marketplace remove blockhouse-tools --scope user
claude plugin marketplace list --json
```

Expected: the plugin is absent, then the catalog is absent. These commands do not remove your candidate source or independently prepared private layouts. Retain scan evidence as needed; do not automate deletion of paths reported by an untrusted candidate. No blanket filesystem cleanup is part of this guide.

## Evidence and pending checks

The local CLI lifecycle exercised catalog addition, disabled installation, inert cached hooks, already-disabled behavior, an actual fixture version update preserving disabled state, uninstall and catalog removal, with JSON readbacks. No model session, candidate execution or normal-user plugin activation occurred.

Still required: prepared-runtime marketplace activation, native Windows 11 ordinary-account permissions and process checks, real `/plugin` Errors-tab observations, version-pinned distribution and final acceptance review. No merge, publication or rollout is authorized by this document.

## References

- https://code.claude.com/docs/en/plugin-marketplaces
- https://code.claude.com/docs/en/discover-plugins
- https://code.claude.com/docs/en/settings
- Installed CLI help: `claude plugin install --help`, `update --help`, `disable --help`, `uninstall --help`, `marketplace --help`.
