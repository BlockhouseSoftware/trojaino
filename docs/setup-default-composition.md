# Default-plan installation composition

`DefaultSetup.Install(DefaultSetupPlan, CancellationToken)` composes the reviewed
known-folder plan, `SharedParents.Run`, and original `SetupController.Install`.
It is an internal callable entry, not a consent UI or user-facing installer.
Native Framework refusal precedes input handling. Pre-cancellation refuses before
parent writes. The parent helper validates every intended destination before
private exclusive missing-parent creation, repeats full joint preflight, then
invokes the original controller using the plan's immutable exact roots and name.
Only the controller's verified persistent PairState.Record is returned. Nothing
throwing is added after successful return that could lose that ownership record.

The inner controller retains all existing process-lifetime and component/state
rollback obligations. The outer parent helper only removes known empty parents in
reverse order after failure; unknown/unreturned plugin content prevents empty-parent
removal and is retained. Outer cleanup grants no helper-stop or input-tree authority.
Successful installation leaves shared `.claude/skills`; persistent component removal
leaves those shared directories. Cancellation during preflight may temporarily create
parents before the controller observes cancellation and rolls them back. This is
not atomic, crash recovery, cancellation-until-first-write or a bounded-IO guarantee.

The native harness starts with no `.claude/skills`, uses only a test-symbol default
folder plan for isolated fixtures, executes the pinned approved CPython through the
original controller, verifies persistent roots, disabled exact name and final literal
binding, and exercises fresh-process DPAPI removal. Pre-cancel/occupied last-role
cases require no parent writes. Native test success must be read at an exact SHA;
Mac platform refusal and Server CI are not Windows11/GUI/SmartScreen qualification.

Still missing: GUI and explicit consent, installation rediscovery without paths,
effective Claude activation/verification/disable/remove UX and retained-output
recovery, downloadable user handoff and ordinary-account Windows11 first-download
acceptance. Marketplace remains an inert distributor, not the active lifecycle.
No runtime trust/pins, scanner policy, credentials or global configuration changed.
