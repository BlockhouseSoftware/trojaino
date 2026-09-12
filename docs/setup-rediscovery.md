# Existing-install rediscovery

`DefaultSetupDiscovery.Find()` is read-only and has no caller path or loader inputs.
It uses the native default-profile plan, scans at most 4096 top-level names in each
of LocalApplicationData and the personal skills directory, and reconstructs the
same six-role layout for an existing exact lowercase 32-hex identity. It never
reads interpreter candidates or executes files during discovery.

The `trj-` and `trojaino-local-` prefixes are untrusted hints, not ownership.
One complete runtime/runtime-state/plugin-state/personal-plugin identity is required.
Malformed/case-aliased hints, source/scratch residuals, incomplete or multiple
identities refuse automatic action. Unrelated files are neither read nor changed.
Missing optional `.claude/skills` is allowed; access errors, files in place of
folders and reparse folders are not absence. Native folder/volume/alias checks
precede enumeration. All four selected trees must then authenticate and verify
through the existing `PairState.Load`; hints never authorize deletion.

A returned record proves stored ownership/integrity at that check, not effective
Claude enablement or hook execution. The future setup window must call discovery
before offering install, display retained-state failures, and separately obtain
consent for every lifecycle action. Discovery itself does not install, remove,
change settings, clean residuals or recover crashes. Ambiguous installations need
recovery UX, not a silent new identity. No manual path entry is the intended flow.

`discovery-tests` tests bounded name classification and platform refusal;
`discovery-production-tests` checks compile-time seam absence. `default-tests`
on native Framework installs with the real approved helper, restarts a process
with only fixture OS-folder locations (no remembered identity/component paths),
rediscovers authenticated state, removes using that receipt and confirms absence.
Its native execution must be read at the reviewed SHA; portable tests are not
DPAPI, Windows11, GUI or first-download qualification.

Production source retains the approved user-scope boundary and all existing
ownership/payload gates. No scanner policy, credentials or normal Claude settings
are modified by this change.
