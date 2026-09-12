# Native setup window (intermediate engineering slice)

`SetupWindow` is a real Framework WinForms window, opened by the zero-argument STA
`SetupProgram`. The launcher holds a Global, Windows-account-SID-specific mutex
through the window lifetime; another copy refuses before discovery. An abandoned
mutex never confers filesystem ownership: normal authenticated rediscovery still
runs. This is same-account coordination, not process-crash recovery.

The native build compiles a production-symbol x64 GUI executable with the exact
approved payload embedded and an `asInvoker`, `uiAccess=false` manifest. The native
metadata harness checks that actual executable without running its normal-profile
entry, and rejects a separate linked-payload negative artifact. Build output is
engineering-only, not published or a qualified independently downloadable installer.
The window is explicitly labeled a development preview.
It has no Enable or Disable buttons yet. Consented file removal is a separate
operation, not effective disablement of running sessions. Do not send this preview
to an independent installer tester yet.

Opening starts read-only authenticated rediscovery on a background worker. Install
is unavailable until discovery establishes absence and the person checks the
initially unchecked consent. The text explains bundled pinned Python, user scope,
reviewed preparation, separate local plugin, disabled default and the fact that
marketplace removal does not control this separate plugin. No path or interpreter
inputs, configuration editing, account login or candidate execution are added.

Install rechecks discovery before invoking the real `DefaultSetup` composition.
It does not start another identity on a stale absent display. Worker completion
returns the original verified persisted result. Reopening finds existing records;
file integrity is always distinguished from Claude activation and protection.
Recheck files runs the same authenticated discovery, not a superficial existence
check. Unknown or incomplete state disables Install and remains untouched by the
window. Failure wording allows retained partial output rather than promising
atomic rollback. Read-only details are local; no automatic upload occurs.

Remove local files becomes available only after authenticated rediscovery and a
separate unchecked consent. The person confirms all Claude Code sessions are
closed and deliberately authorizes removal of the separate plugin and bundled
runtime. This is the person's assertion, not proof that processes stopped. The
worker redoes discovery, verifies the entire owned pair and uses the original
plugin-first removal primitive; it confirms authenticated absence before reporting
Removed. Shared parents, other skills, Claude settings and the marketplace copy
are untouched. Existing settings entries are not removed or interpreted as
universal disablement. The deleted in-place plugin is absent from future discovery;
already loaded hooks are not unloaded. Other profiles/installations are not checked.

Every operation clears all consent checkboxes. Unknown content or partial removal refuses
further Install/Remove until authenticated discovery succeeds. A mid-removal error
can leave only part of the pair; reopening cannot safely adopt unknown leftovers.
Removal failures explicitly say to keep all Claude Code sessions closed, that
removal may have stopped partway and some files may remain. The failure screen
preserves the original error and details rather than suggesting manual folder deletion.
The native harness locks the approved runtime file with read sharing: verification
succeeds, the plugin is retired, runtime deletion fails with IOException. It then
checks retained runtime bytes/state, disabled actions, and a refused reopen with
identical survivor inventory, native identities and hashes. This is a real locked-file
failure, not simulated crash recovery; native execution must pass at the reviewed SHA.
The current Finish removal implementation handles only one exact default identity
with runtime plus protected runtime-state remaining, plugin and plugin-state absent,
and every original runtime directory still present. It authenticates both DPAPI
layers and location/schema bindings, copies only original surviving file metadata,
rejects every unknown/replaced/changed entry, and verifies the entire state container
before deletion. Normal Open/Load/Verify still refuse missing files. No missing file
is recreated, no disk ownership is adopted, and the original receipt is not mutated.
A separate unchecked closed-session consent is bound to the displayed runtime root;
each click reauthenticates, and full/absent/different/ambiguous state requires recheck.
The UI never grants Install/ordinary Remove/activation from a recoverable remainder.
Native GREEN at the exact reviewed SHA is still required for this new path.

The companion native test deterministically retires one known approved-runtime fixture
file after the real lock failure, so the missing-file branch is reached before recovery.
It tests unknown content in BOTH runtime and runtime-state after consent, requiring
whole survivor inventory/identity/hash preservation before retry. Additional native
fixtures require refusal of a second authentic identity and of stale consent when
only a different authentic remainder is discoverable. A production-symbol test
checks that recovery starts disabled and unchecked. These added tests still require
actual native execution; portable schema results do not qualify DPAPI or UI behavior.
Shared parents, settings and unrelated skills are compared by original identities
and exact hashes.

Missing directories, state-only leftovers, partial plugin removal, unknown or corrupt
state and all other incomplete combinations remain refused. This is not general
crash recovery, repair, or proof of the historical cause of the remaining files.
Further recovery cases remain engineering work.

The window refuses ordinary close while a worker is active and explains that the
person must wait. It does not claim cancellation during the synchronous commit,
process-kill resistance, Windows shutdown prevention or crash recovery. The
application guard belongs to `SetupProgram`, not to a Form constructed in isolation.

The window harness keeps a persistent `Application.Run(ApplicationContext)` loop
across the entire twice-repeated journey, including closed/reopened fixture forms.
It checks UI-thread affinity and retains every consent/removal/preservation assertion.
The earlier standalone `DoEvents` harness was invalid: exact native diagnostic
`d4d3a32` recorded completion control events on threads 3/7 while the UI owned thread 1.
The production launcher already uses a persistent `Application.Run(window)` loop;
no production state ordering or ownership checks were changed to hide that failure.
Nested test waits still pump events; this is not visual or keyboard qualification.

Native Windows Server Framework tests execute actual controls and handlers in
isolated OS-folder fixtures: unchecked/revoked consent and initial zero writes;
real approved runtime/controller install; busy close; authenticated reopen; changed
state recheck; stale discovery refusal with unknown bytes retained. Removal tests
exercise actual controls, unchecked/revoked consent, recheck revocation, stale
unknown-state refusal before deletion, all-four-tree removal and unrelated Claude
settings/skill-byte preservation. A separate
production-symbol harness constructs without showing the Form, proving test root
factories absent and initial consent/install/removal state without touching normal profile
settings. Neither is visual/DPI/keyboard or Windows11 acceptance.

Next: qualify the new recovery journey natively and produce a distributable installer;
effective Claude enable/verify/disable and other retained-output recovery; full independent
first-download journey and final QA. Windows11 ordinary-account/SmartScreen and
real authenticated Claude evidence remain mandatory, as does release approval.
