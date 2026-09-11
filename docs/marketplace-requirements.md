# Trojaino Claude Code marketplace requirements

**Status:** implementation requirements — supervised development only

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
