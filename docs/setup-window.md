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

Every operation clears both consents. Unknown content or partial removal refuses
further Install/Remove until authenticated discovery succeeds. A mid-removal error
can leave only part of the pair; reopening cannot safely adopt unknown leftovers.
The failure screen preserves details rather than suggesting manual folder deletion.
Automatic partial-removal recovery remains unfinished; this is not crash recovery.

The window refuses ordinary close while a worker is active and explains that the
person must wait. It does not claim cancellation during the synchronous commit,
process-kill resistance, Windows shutdown prevention or crash recovery. The
application guard belongs to `SetupProgram`, not to a Form constructed in isolation.

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

Next: native executable qualification and a distributable installer build path;
effective Claude enable/verify/disable and retained-output recovery; full independent
first-download journey and final QA. Windows11 ordinary-account/SmartScreen and
real authenticated Claude evidence remain mandatory, as does release approval.
