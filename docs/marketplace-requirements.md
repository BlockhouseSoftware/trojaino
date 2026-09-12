# Trojaino Claude Code marketplace requirements

**Status:** supervised trial preparation; Windows qualification pending

Jose’s current instruction authorizes Alpha to resolve non-Windows blockers,
choose recommended implementation decisions, and prepare a Sig Windows 11 test
package. This permits a reviewed local trial snapshot and private handoff to Jose;
it is not production rollout, target activation or a claim of Windows qualification.

## Goal

Make Trojaino discoverable and installable from a Blockhouse-controlled **Claude Code marketplace**. This replaces the manual `--plugin-dir` test path only after marketplace-specific acceptance is complete.

This work does **not** add support for Claude Desktop Chat or Cowork. It does **not** make Trojaino an antivirus, an operating-system sandbox, or an automatic approval system.

## Non-negotiable safety rules

1. The marketplace package must never select an arbitrary `python` executable from `PATH`, shell aliases, or the current directory.
2. The marketplace package must not auto-install Python, Node, packages, MCPs, target plugins, or target applications.
3. A missing, moved, untrusted, or unsupported interpreter must fail closed: no hook execution authorization and no permissive fallback.
4. A plugin installed before local setup is complete must remain disabled. It must not start hooks, launch a target, or claim protection.
5. No candidate source, plugin, MCP, or application may be executed while being prepared, packaged, validated, or scanned.
6. Marketplace source, plugin version, package contents, and release documentation must be bound to a reviewed Git commit.
7. Marketplace installation is not a substitute for Windows 11/native-Claude/ordinary-account acceptance testing.

## Approved user-scope boundary

Jose approved the user-scope boundary in the Alpha Telegram DM: “Proceed with user-scope and 3.” This authorizes completing lifecycle documentation, install/update/remove checks, regression testing and review closure without adding a privileged installer or service.

The trusted local account, reviewed Python interpreter and reviewed setup source are trust anchors. Protection against malicious concurrent processes already running as that same user, administrators or a compromised OS is outside scope. The new-directory requirement applies within that boundary: reject existing destinations, nonempty acquired directories, unsafe paths and file overwrites; retain exclusive creation, identity checks and all verified safeguards. The reproduced empty-directory substitution by a hostile same-user process is an acknowledged excluded attack, not a fixed defect or a guarantee of atomic publication.

Native Windows 11 acceptance remains mandatory before rollout. This approval does not authorize publication, merge, release, or weakening candidate-code isolation.

## Approved separate local-plugin delivery

Jose explicitly approved: “Approve the separate prepared local plugin; preserve security safeguards and Windows release gate.” The marketplace installation remains disabled and inert. Explicit trusted preparation may create a fresh self-contained plugin directly at its final personal skills-directory location, with a distinct version-qualified identity and disabled default. Enablement is a separate visible action. Updates create new identities/directories without overwriting prior copies. Marketplace uninstall does not disable or remove this local plugin; its lifecycle must be documented separately. This amends the marketplace-only activation goal, not runtime binding, isolation, no-overwrite safeguards, or the native Windows release gate.

## Delivery model

- **Publisher:** Blockhouse Software.
- **Marketplace:** a Blockhouse-controlled Git repository, initially a separate `trojaino-marketplace` repository.
- **Plugin source:** a self-contained, versioned Trojaino marketplace package; no paths outside the package after install.
- **Install scope:** user scope for the initial pilot, disabled by default.
- **Updates:** explicit version bumps and reviewed release notes. No mutable branch is a release artifact.
- **Support target:** native Claude Code only. Claude Desktop Chat and Cowork are out of scope.

## Stories

### MKT-001 — Catalog and package contract

As a user, I can add a Blockhouse marketplace and see a clearly described Trojaino entry before deciding to install it.

**Acceptance criteria**

- A strict-valid `.claude-plugin/marketplace.json` exists at the marketplace repository root.
- The catalog uses a non-reserved kebab-case marketplace name and identifies Blockhouse as owner.
- The Trojaino entry has a name, display name, description, semantic version, repository/homepage, license, and tags.
- The entry describes it as an experimental, disabled-by-default, Claude Code-only inspection-session plugin.
- The package layout contains only the plugin’s own files; no `../` dependency or top-level `bin/` directory is allowed.
- Automated tests verify catalog schema, source path containment, plugin metadata parity, and rejection of unsafe/mutable release references.

### MKT-001A — Self-contained package boundary

As a marketplace user, I receive every Trojaino runtime file inside the installed plugin directory and never resolve code from the marketplace checkout, its parent, or an ambient package.

**Acceptance criteria**

- The installed plugin copy runs its preflight entrypoint without importing from a path outside `${CLAUDE_PLUGIN_ROOT}`.
- No plugin script adds a parent directory to `sys.path`, invokes a shell to discover code, or relies on an ambient `trojaino` package.
- An isolated copied-package test proves the entrypoint imports only bundled runtime files under an explicit trusted interpreter.
- The plugin has no symlinks escaping its root, no `../` runtime references, and no Node dependency-install surface.
- An unprepared disabled installation has no active executable hook command; its setup/status path is non-executing.

### MKT-002 — Disabled-before-setup lifecycle

As a user, I can install the marketplace plugin without starting its hooks before the local runtime has been explicitly prepared.

**Acceptance criteria**

- The marketplace entry and plugin manifest default to disabled.
- A clear, non-executing status command explains that setup is incomplete.
- Enabling the unprepared plugin must fail closed with an actionable error; it must not invoke a shell fallback or target code.
- Tests demonstrate that unprepared installation has no executable hook command.

### MKT-003 — Explicit local runtime binding

As a user, I can bind one approved local Python executable through a deliberate setup flow, then obtain a complete private prepared plugin copy with literal executable paths.

**Acceptance criteria**

- Setup requires an absolute Python path supplied explicitly by the user or a reviewed installer.
- Setup validates native platform constraints, absolute path, supported Python version, and destination safety before copying files.
- Setup creates a new private prepared directory; it never overwrites an existing copy.
- The hook manifest contains literal, validated executable and helper paths only after preparation.
- A moved interpreter or prepared directory invalidates the configuration and denies operation.
- Tests cover positive setup and denial for PATH-only, relative, symlink/reparse, unsupported-version, existing-destination, and moved-path cases.

### MKT-004 — Marketplace lifecycle and documentation

As a nontechnical user, I can install, inspect, disable, update, and remove the plugin without a hidden global configuration change.

**Acceptance criteria**

- Documentation uses plain English and distinguishes adding a marketplace from installing a plugin.
- Documentation provides the exact installation, verification, disable, update, and removal commands.
- Documentation states that first install is disabled, and explains the separate explicit setup step.
- Documentation says what `/plugin` and its Errors tab should show after each action.
- CI validates the marketplace catalog and package, including a clean clone/install fixture where supported.

## Test and review gates

1. Every behavior change follows RED → GREEN → REFACTOR with saved command output.
2. Run the full existing test suite and marketplace-specific tests after each completed story.
3. Run `claude plugin validate --strict` for the marketplace and plugin paths where the installed Claude Code version supports it.
4. Before a story is accepted, an independent reviewer checks its diff for source substitution, path escape, unsafe runtime discovery, shell fallback, hook activation before setup, secrets, and update rollback gaps.
5. Windows Server CI is evidence only. A supervised Windows 11/native-Claude/ordinary-account acceptance test remains a release gate.
6. Astra performs final QA only after all development stories and code-review fixes are complete.

## Explicitly out of scope

- Publishing to Anthropic’s official or community marketplace.
- An `.exe` or `.msi` installer.
- Automatic Python/Node installation.
- Claude Desktop Chat/Cowork support.
- Activating Linear, Hookify, VoiceGrab, or any target service.
- Merging, release publication, or user rollout without recorded approval.
