# Native setup window

`SetupWindow` is a Framework WinForms window opened by the zero-argument STA
`SetupProgram`. The launcher holds a Global, Windows-account-SID-specific mutex
through the window lifetime; a second copy refuses before discovery. An
abandoned mutex never confers filesystem ownership: normal authenticated
rediscovery still runs. This is same-account coordination, not process-crash
recovery.

The native build compiles a production-symbol x64 GUI executable with the exact
approved payload embedded and an `asInvoker`, `uiAccess=false` manifest. The
native metadata harness checks that executable without running its
normal-profile entry, and rejects a separate linked-payload negative artifact.
The window is labeled a development preview. Consented file removal is a
separate operation, not effective disablement of running sessions.

## Install

Opening starts read-only authenticated rediscovery on a background worker.
Install is unavailable until discovery establishes absence and the person
checks the initially unchecked consent. The text explains bundled pinned
Python, user scope, reviewed preparation, the separate local plugin, the
disabled default and that marketplace removal does not control this separate
plugin. No path or interpreter inputs, configuration editing, account login or
candidate execution are offered.

Install rechecks discovery before invoking the real `DefaultSetup` composition
and does not start another identity on a stale absent display. Worker
completion returns the original verified persisted result. Reopening finds
existing records; file integrity is always distinguished from Claude
activation and protection. "Recheck files" runs the same authenticated
discovery, not a superficial existence check. Unknown or incomplete state
disables Install and is left untouched. Failure wording allows retained
partial output rather than promising atomic rollback. Read-only details are
local; no automatic upload occurs.

## Remove

"Remove local files" becomes available only after authenticated rediscovery
and a separate unchecked consent. The person confirms all Claude Code sessions
are closed and deliberately authorizes removal of the separate plugin and
bundled runtime. This is the person's assertion, not proof that processes
stopped. The worker redoes discovery, verifies the entire owned pair and uses
the plugin-first removal primitive; it confirms authenticated absence before
reporting Removed. Shared parents, other skills, Claude settings and the
marketplace copy are untouched. Existing settings entries are not removed or
interpreted as universal disablement. The deleted in-place plugin is absent
from future discovery; already loaded hooks are not unloaded. Other
profiles/installations are not checked.

Every operation clears all consent checkboxes. Unknown content or partial
removal refuses further Install/Remove until authenticated discovery succeeds.
A mid-removal error can leave only part of the pair; reopening cannot safely
adopt unknown leftovers. Removal failures say to keep all Claude Code sessions
closed, that removal may have stopped partway and some files may remain, and
preserve the original error and details rather than suggesting manual folder
deletion.

## Finish removal (recovery)

The current "Finish removal" implementation handles one exact default identity
with runtime plus protected runtime-state remaining, plugin and plugin-state
absent, and every original runtime directory still present. It authenticates
both DPAPI layers and location/schema bindings, copies only original surviving
file metadata, rejects every unknown/replaced/changed entry, and verifies the
entire state container before deletion. Normal Open/Load/Verify still refuse
missing files. No missing file is recreated, no disk ownership is adopted, and
the original receipt is not mutated. A separate unchecked closed-session
consent is bound to the displayed runtime root; read-only details show the
authenticated runtime and protected-state locations before consent is enabled.
Each click reauthenticates, and full/absent/different/ambiguous state requires
recheck. The UI never grants Install, ordinary Remove or activation from a
recoverable remainder.

Missing directories, state-only leftovers, partial plugin removal, unknown or
corrupt state and all other incomplete combinations remain refused. This is not
general crash recovery, repair, or proof of the historical cause of the
remaining files.

## Close behavior

The window refuses ordinary close while a worker is active and explains that
the person must wait. It does not claim cancellation during the synchronous
commit, process-kill resistance, Windows shutdown prevention or crash recovery.
The application guard belongs to `SetupProgram`, not to a Form constructed in
isolation.

## Tests

The native harness keeps a persistent `Application.Run(ApplicationContext)`
loop across a twice-repeated journey, including closed/reopened fixture forms,
and checks UI-thread affinity; an earlier standalone `DoEvents` harness was
invalid because completion control events ran off the UI thread. Native
Windows Server Framework tests execute actual controls and handlers in isolated
OS-folder fixtures: unchecked/revoked consent and initial zero writes; real
approved runtime/controller install; busy close; authenticated reopen; changed
state recheck; stale discovery refusal with unknown bytes retained; removal with
unchecked/revoked consent, recheck revocation, stale unknown-state refusal
before deletion, all-four-tree removal and unrelated settings/skill-byte
preservation. The locked-runtime-file case (verification succeeds, plugin is
retired, runtime deletion fails with `IOException`) checks retained bytes,
disabled actions and a refused reopen with identical survivor inventory. A
production-symbol harness constructs without showing the Form. None of this is
visual/DPI/keyboard or Windows 11 acceptance.

## Remaining work

Complete recovery qualification, effective Claude enable/verify/disable, other
retained-output recovery, a distributable signed installer, the full
independent first-download journey and final QA. Windows 11 ordinary-account
and SmartScreen behavior and real authenticated Claude evidence remain
mandatory gates.
