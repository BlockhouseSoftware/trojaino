# Default-profile setup location plan

`DefaultSetupPlan.Resolve()` is a read-only native Windows .NET Framework path
resolver for a future consent screen. It is NOT an installer, activation operation,
reservation, ownership record or proof of the terminal's effective Claude profile.

It uses `Environment.GetFolderPath(UserProfile)` and `LocalApplicationData`, never
PATH, current-directory fallback or user-entered runtime/config paths. Empty or
unsafe known folders fail closed. A nonempty process `CLAUDE_CONFIG_DIR` refuses
this default-profile-only flow, even when it spells the normal default directory.
Other processes' environments and credentials are not inspected. A future UI must
explicitly identify the default Claude profile; an absent override in setup cannot
prove every existing Claude terminal uses that profile.

A fresh Guid N identity supplies `trojaino-local-<32lowerhex>` beneath the default
`~/.claude/skills/`. Five distinct `trj-<id>-<role>` roots sit directly beneath OS
LocalApplicationData, avoiding creation/adoption of a shared application parent.
Literal roots and complete compiled member budgets pass SetupLocations.ValidateLayout.
Root arrays are defensive copies; no caller folder/identity injection is compiled
into production. Native parent/volume/alias/absence checks remain the controller's
mandatory prewrite gate; a plan does not perform them or reserve directories.

Missing `.claude/skills` is provisioned by the setup flow itself; users are never
asked to create it, copy paths or edit config. Fresh identity generation
is not a persistent installation registry, duplicate-install detection or consent.
The GUI, activation, effective verification, disable/remove controls and recovery
experience remain unfinished. The current bundle stays default-disabled.

Sources consulted before implementation:
- https://learn.microsoft.com/en-us/dotnet/api/system.environment.getfolderpath?view=netframework-4.8.1
  GetFolderPath can return an empty string when the physical folder is absent.
- https://code.claude.com/docs/en/plugins-reference.md
  Skills-directory personal plugins are discovered in place at `~/.claude/skills/`,
  identity `name@skills-dir`; Marketplace install/disable is a separate lifecycle.

Tests separately cover pure literal mapping/refusals/array isolation, production
symbol non-Framework refusal and actual OS resolution on native Framework. Native
Server tests do not qualify Windows11, first download, SmartScreen or Claude auth.
