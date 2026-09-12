# Transient shared Claude parents

`SharedParents.Run(DefaultSetupPlan, Action)` is an internal, consent-time adapter,
not a GUI or installer. The production entry accepts only the private default-plan
object, snapshots its six roots, validates complete compiled member budgets and
mutual layout, checks native existing parents and refuses every occupied setup
root before writing. Only missing `.claude` and `skills` under that plan's profile
can be created. The profile/local-data roots must already exist. Native alias,
volume, architecture and reparse checks remain unchanged. Permission/IO errors
are not converted into permission to create/adopt content.

Creation uses private exclusive `Bootstrap.CreateEmpty`. After creation the original
whole-plan `SetupLocations.Check` runs again, then the caller action. These checks
are not reservations or an atomic transaction. The caller still owns component
installation, input lifetime and cleanup; parent cleanup grants none of that authority.
On failure only original returned empty-parent receipts can be removed, child
before parent. All cleanup attempts occur, preserving the primary and each failure.
Unknown/replaced/unreturned content remains. Existing `.claude` files are never
adopted or modified. Empty receipts for parents cannot remove a parent's populated
child: child cleanup must precede parent cleanup. On success shared directories
remain; there is no persistent parent uninstaller ownership.

Portable fault tests exercise actual directory creation, reverse rollback,
existing settings preservation, failed gate/no writes, unknown content in either
parent, exclusive child collision and same-empty replaced directory refusal.
The separate native entry harness has no `SharedParents.TestRun`; it uses the
compile-time `DefaultSetupPlan.TestCreate` only to isolate OS-folder fixture roots
without changing normal user config. Native Framework full prewrite behavior is
separate from the Mac production-entry platform-refusal test. Server evidence is
not Windows11 or ordinary-account first-download/SmartScreen evidence.

Not finished: consent/GUI/controller composition, persistent install discovery,
effective activation/verification/disable/remove/recovery, signed/downloadable
artifact delivery and actual nontechnical Windows11 acceptance. Marketplace copy
remains inert with separate local lifecycle. No changes to vendor schemas, runtime
provenance/pins, candidate execution policy or existing trial artifacts.
