# Native setup window (intermediate engineering slice)

`SetupWindow` is a real Framework WinForms window, not yet a distributable setup
executable or complete installer. It is explicitly labeled a development preview.
It has no Enable, Disable or Remove buttons until their effective integration is
implemented and tested. Do not send it to an independent installer tester yet.

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

The window refuses ordinary close while a worker is active and explains that the
person must wait. It does not claim cancellation during the synchronous commit,
process-kill resistance, Windows shutdown prevention, crash recovery, or a whole
application single-instance guard. Those are not properties of a Form alone.

Native Windows Server Framework tests execute actual controls and handlers in
isolated OS-folder fixtures: unchecked/revoked consent and initial zero writes;
real approved runtime/controller install; busy close; authenticated reopen; changed
state recheck; stale discovery refusal with unknown bytes retained. A separate
production-symbol harness constructs without showing the Form, proving test root
factories absent and initial consent/install state without touching normal profile
settings. Neither is visual/DPI/keyboard or Windows11 acceptance.

Next: guarded STA production executable with embedded approved payload; effective
Claude enable/verify/disable/remove and retained-output recovery; full independent
first-download journey and final QA. Windows11 ordinary-account/SmartScreen and
real authenticated Claude evidence remain mandatory, as does release approval.
