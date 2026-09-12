# Internal setup transaction — iteration14

This is developer component work, NOT an independently usable installer for Sig.
No GUI, consent/known-folder resolver, settings activation or Windows11 qualification
is supplied. Earlier friendly-setup architecture decisions remain binding; this
slice implements the previously missing composition only.

SetupController.Install snapshots six caller roots once, uses SetupLocations.Check
before writes and exclusively stages compiled approved runtime/source. It captures
the original runtime ownership receipt, creates private empty scratch and calls only
TrustedPreparation.Install. No production-supplied ZIP, hash, executable or callback
confers trust. Caller must be future trusted consent/root-selection code, not a
manual path flow for the recipient. Runtime stays at its lifetime binding location.

On successful preparation, save the DPAPI pair, retire source/scratch and verify
all four persistent trees before returning ownership. Default-disabled identity is
NOT proof against existing enabledPlugins overrides; resolver/lifecycle must address
that before any real Claude-target installation. Harness roots are disposable and
outside Claude discovery. No candidate code is executed.

Cleanup authority is separate from ownership. Before helper call release becomes
unknown. Only normal return or ProcessFailureException.InputsReleased restores it;
generic errors conservatively retain all execution inputs. With released inputs,
attempt original source/scratch cleanup independently, then persistent pair removal
or original plugin removal before runtime. Unknown unreturned plugin paths and
uncertain attribute probes retain the bound runtime. No disk-tree receipt adoption.
Original and every independently attempted cleanup error survive. Inner failed
Stage/Store/Publish owns partial rollback. Unknown partial state may remain and is
not automatically recovered or repurposed.

Cancellation is cooperative before staging and helper invocation, with preparation's
own checks. Once helper/publication returns, persistence+retirement is synchronous;
late cancellation returns a valid verified receipt rather than throwing after
success. This is not atomic, crash-safe, cancellation-until-first-write, IO time
bounded or a descendant-process sandbox. Retained failures still need friendly
recovery UX. A failed persistent all-four predelete may leave all four roots.

SETUP_CONTROLLER_TESTS exposes an inert helper and post-stage phase faults only in
a separate test harness. Portable tests use real compiled staging but a test state
codec and inert plugin, never bundled Python execution. Production-symbol reflection
asserts both public test entry and private callback parameters absent and verifies
exact non-Framework refusal. Native harness separately executes approved Python,
checks complete runtime inventory/bytes, all plugin hashes/default-disabled identity
and literal sealed/hook paths, persists DPAPI and removes in a fresh process.
Exact-SHA native execution must be read before claiming it ran. WindowsServer success
never qualifies Windows11/first-download/SmartScreen/GUI/authenticated Claude.
