# Prepared personal plugin

The marketplace copy of Trojaino is inert. Protection comes from a separately
prepared personal plugin that lives in the user's Claude `skills` directory and
is bound to its final path and one approved interpreter. For a supervised
manual trial, follow the [Windows trial checklist](windows-trial-checklist.md);
the native setup window automates the same steps.

## Explicit preparation

Invoke the reviewed `scripts/prepare_preflight_plugin.py` with an explicitly
approved absolute Python 3.11+ path and `-I -S`, supplying a NEW absolute final
destination and `--personal-plugin-name trojaino-local-RELEASE-ID`. Replace
RELEASE-ID with a distinct lowercase kebab-case identifier for each prepared
version. The destination for personal discovery is a fresh directory directly
under the user's Claude `skills` directory (or an isolated test
configuration's `skills` directory).

The destination basename must equal the personal plugin identity. This prevents
two differently named sibling directories produced by this helper from
advertising one identity, while exclusive creation prevents reusing the same
sibling destination. This is not a global registry: manually authored
conflicting plugins or another skills root require separate operator review.
Use one approved personal skills root and a new identity for each release.

The helper writes the complete self-contained plugin directly at that final
path. It does not alter settings, register a marketplace, enable the plugin,
select Python through PATH, or overwrite an existing directory. The manifest is
disabled by default. Never move or copy the resulting prepared plugin;
re-prepare at a new final destination instead. The generated entry rejects a
`CLAUDE_PLUGIN_ROOT` that differs from its bound root before loading the
runtime, so a copied hook cannot silently run the original entry.

The marketplace copy remains disabled. The prepared plugin has a separate
identity: `trojaino-local-RELEASE-ID@skills-dir`. Marketplace uninstall does
not disable or remove this local plugin.

## Lifecycle

- Inspect: `claude plugin list --json`. Confirm the exact local identity, final path and `enabled: false` before any activation.
- Enable: `claude plugin enable trojaino-local-RELEASE-ID@skills-dir --scope user`, then verify with plugin list. Direct execution of test hook arguments is not evidence of real Claude hook dispatch; check `/hooks` in a fresh session.
- Disable: `claude plugin disable trojaino-local-RELEASE-ID@skills-dir --scope user`, then verify with plugin list. Close/restart existing inspection sessions; loaded hooks may persist until reload/restart.
- Update: requires a fresh directory and distinct identity. Explicitly disable the old identity before activating a reviewed replacement. Never overwrite an existing prepared tree. Side-by-side replacement and removal of the old copy leave the new one discoverable, disabled and byte-identical.
- Remove: not marketplace uninstall. Disable the local identity, close its sessions, and remove only the exact user-approved prepared directory after retaining desired evidence. No automatic broad filesystem deletion is provided.

## Tests

The final-layout test checks disabled metadata, literal final binding,
correct-root success, wrong-root denial and existing-destination refusal. The
README transformation accepts CRLF and bare-CR inputs and rejects missing,
duplicate or reversed section boundaries before creating any destination.

Real hook dispatch, enabled-session disable/reload behavior, native Windows
discovery and path spelling/permissions/process checks remain acceptance gates.
