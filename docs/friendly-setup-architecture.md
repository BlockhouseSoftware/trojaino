# ADR: Explicit Windows setup, overnight 2026-09-12

Status: implementation in slices; NOT an independently usable Sig installer.
Jose's overnight direction replaces the rejected source-only/manual trial UX and
permits the smallest reviewed, user-consented pinned-runtime setup mechanism.
It does not permit publication, security bypass instructions, automatic candidate
execution, or claims of native Windows 11 qualification.

## Vendor feasibility (checked before implementation)

Official Claude documentation retrieved 2026-09-12:
- https://code.claude.com/docs/en/plugin-marketplaces#command-sources
- https://code.claude.com/docs/en/plugin-marketplaces#copy-mode-and-link-mode
- https://code.claude.com/docs/en/plugins-reference#plugin-init

Command sources run a shell command and subsequently copy its output into the
cache. They re-run in background sessions. Link mode explicitly is unsupported
on Windows. Copy mode does not preserve a final-path-bound sealed entry.
Therefore it is not a supported true Marketplace activation solution for this
runtime. No invented install hook or schema extension will be used. Retain the
previously approved separate personal skills-directory plugin: Marketplace is
inert discovery/documentation only, not the enable/disable/remove authority.

## Runtime provenance decision

Use the official CPython 3.14.7 Windows x64 embeddable ZIP as the initial build
input, not a Python chosen from PATH. The build verifies its exact pinned SHA-256:
`d297e5ff019966817ad8502465176139f2d3d840fa4ed84b13bed399a6ab1f15`.
URL: https://www.python.org/ftp/python/3.14.7/python-3.14.7-embed-amd64.zip
Published digest: https://www.python.org/downloads/release/python-3147/
Downloaded archive independently hashed to this value on 2026-09-12. This is
HTTPS publisher-page provenance and exact byte pinning, NOT a completed Sigstore
or Authenticode verification. Do not execute the downloaded runtime on this Mac.
No claim of CPython 3.14 compatibility until its tests actually run on Windows.

Official embedding guidance:
https://docs.python.org/3/using/windows.html#the-embeddable-package
The embeddable package is designed for application-local distribution and has
no pip or Tcl/Tk. Keep its isolated `_pth` configuration unchanged; do not add
site-packages or install dependencies. Preserve the Python license and every
vendor file. Initial platform support is x64 only; ARM64 must refuse until a
separate reviewed runtime and actual tests exist. Sig's architecture is unknown.

The bundled runtime and reviewed setup executable are trust anchors. A manifest
inside a ZIP is not authenticity. The eventual native launcher must have the
payload digest compiled into reviewed code/resources, validate it BEFORE
extracting or launching Python, and execute the absolute private runtime only.
The release binary itself needs an approved provenance/distribution path.

## Chosen setup contract

Target a native, ordinary-account setup window with explicit consent and Install,
Verify, Disable and Remove actions. No PowerShell security bypasses, Python-path
entry, config-file editing, elevation or remote assistance. An unsigned binary
that triggers a blocking SmartScreen warning is an unresolved usability gate,
not an instruction to click through. No code-signing spend is authorized.

Setup must validate a pinned offline payload before writing it, create only fresh
private versioned directories, and prepare the disabled plugin directly in its
final skills location using the existing guarded writer and sealed binding.
It must not relocate prepared hooks. Complete integrity/readiness verification
precedes a separate explicit enable action. Settings changes, if needed, must
be user-consented, narrowly scoped, preserve unrelated settings and be read back.
Existing destination refusal preserves all previous bytes. Failed preparation
must not activate a partial plugin. Rollback/removal must prove ownership and
must not recursively delete an unverified or substituted tree.

Verification must distinguish installed-disabled, enabled, actual SessionStart
hook evidence and authenticated scan evidence. A warm Ollama model, a green
archive test, a built EXE or macOS execution cannot stand in for these.
Disable/removal must warn to close/restart existing sessions. Marketplace removal
does not remove this separately installed component.

## First implementation slice

Build-time offline payload validation and deterministic packaging: pin complete
runtime bytes before parsing, strictly validate ZIP names/types/duplicates and
resource budgets, preserve the complete runtime and source inventories, bind
source archive digest and source commit in metadata, and exclusively create a
new trial artifact. This is a real packaging component, not a launcher. It does
not solve the native bootstrap on its own and must never be marketed as setup.
Subsequent slices: native pre-Python bootstrap, final-location transactional
installation, UI/lifecycle verification, Windows CI at exact SHA, native Windows
11 first-run and blocked-download UX. Existing 0.1.6 trial artifacts stay intact.

## Native bootstrap decision (iteration 2, before implementation)

Choose a C# Windows GUI on the OS-provided .NET Framework 4.8, not Inno's
conventional overwrite installer and not a PowerShell launcher. Microsoft's
system-requirements table lists .NET Framework 4.8 on original Windows 11 and
4.8.1 on 22H2 and newer. Do not install .NET or elevate if missing. The GUI and
native Windows build/execution remain unfinished; portable core tests are not
Windows acceptance.

Sources checked 2026-09-12:
- https://learn.microsoft.com/en-us/dotnet/framework/get-started/system-requirements
- https://learn.microsoft.com/en-us/dotnet/api/system.io.compression.ziparchive
- https://learn.microsoft.com/en-us/dotnet/api/system.io.filemode
- https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createdirectoryw
- https://learn.microsoft.com/en-us/dotnet/core/deploying/single-file/overview

.NET single-file self-contained was considered but not selected: it adds another
bundled runtime and native-library extraction before application code. The OS
Framework avoids that bootstrap chain. A privately unpacked Microsoft SDK is only
Mac development tooling, HTTPS/SHA512 pinned, with no PATH/global-config changes.
It is not part of Sig's installation or evidence of .NET Framework execution.

The native core receives immutable build-authorized archive and file hashes from
the executable's compiled resources. No caller-facing override, archive manifest,
PATH runtime or downloaded candidate supplies trust. Validate exact archive hash
before ZIP parsing, exact safe member inventory/types and bounded decompression,
then each file's digest before any filesystem side effect. A future build adapter
must generate these constants from reviewed immutable inputs and verify all bytes.

CreateDirectoryW with a private security descriptor provides exclusive Windows
root creation; Directory.CreateDirectory alone is unsuitable because it accepts
existing directories. CreateNew files only. Refuse reparse ancestors. Keep an
in-memory receipt of created paths/hashes, inspect complete tree before removal,
never recursive-delete unknown trees. User-scope threat boundary still applies;
hostile same-user races are excluded, not described as repaired. POSIX exclusive
mkdir permits exercising the same transaction tests on Mac; it does not certify
Win32 ACLs, reparse handling or locks. No extraction runs Python. Final-location
plugin preparation and enablement are separate later operations, not hidden
side effects of authenticating/staging a runtime.

## Windows eligibility decision (iteration 3; now implemented, unqualified)

This decision was recorded before code. The checks are now implemented and
portable-tested, but native Windows execution remains unqualified.

Before the first directory creation, require a literal drive-qualified Windows
path, existing non-reparse ancestors and a local fixed NTFS volume. Reject UNC,
device, drive-relative, slash-normalized, dot-component, ADS, trailing-dot/space,
reserved-device and over-budget paths. Bound the final member paths too, without
requiring long-path registry changes. Preserve valid Unicode/spaces in user names.
Check the existing parent with GetLongPathNameW rather than assuming a tilde test
is sufficient to exclude short-name aliases. Never silently normalize/rebind.

Use IsWow64Process2's native-machine output for x64 eligibility, NOT
GetNativeSystemInfo: Microsoft documents that the latter can report emulated x64
on ARM64. Missing API/probe failures refuse setup, not fallback to PATH or ARM
emulation. Portable tests can exercise the decision logic but cannot validate
Win32 calls or NTFS behavior; actual Windows execution remains a release gate.
Sources checked before code, 2026-09-12:
- https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file
- https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getlongpathnamew
- https://learn.microsoft.com/en-us/windows/win32/api/wow64apiset/nf-wow64apiset-iswow64process2
- https://learn.microsoft.com/en-us/windows/win32/api/sysinfoapi/nf-sysinfoapi-getnativesysteminfo
- https://learn.microsoft.com/en-us/dotnet/api/system.io.driveinfo.drivetype

- https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfinalpathnamebyhandlew
- https://learn.microsoft.com/en-us/windows/win32/sysinfo/image-file-machine-constants

## Compiled resource adapter checkpoint (iteration 3)

`scripts/build_setup_resources.py` implements the previously chosen compiled trust
anchor: developer-supplied literal outer/source pins and a fixed official runtime
pin, full validation/recomputation, exact outer inventory, no trust in payload.json.
The source commit remains explicitly declared, not proven by a hash or manifest.
Release preparation must independently bind source bytes to the reviewed commit.

Generated C# uses one explicitly named embedded resource. Its complete digest is
checked before opening ZIP structure; complete compiled inner archive/member pins
are then passed to the native stager. StageRuntime/StageSource have no hash or
runtime-path override. They do NOT run Python, prepare a plugin, activate hooks or
persist an uninstall receipt. This is not the finished transaction across both
stages; the future controller must own rollback of the earlier stage if the later
stage/preparation fails. No successful-setup claim is made by this adapter.

The real existing engineering payload was embedded, built and exercised on Mac:
all37 runtime files and48 source files compared byte-for-byte, both receipts
verified and removed; no content executed. A separately corrupted resource built
against unchanged compiled pins was rejected before any destination write.
This is a .NET10 test assembly without fault-injection symbols, NOT Framework4.8
or native Windows evidence. Existing trial bytes were preserved unchanged.

Attempted Framework4.8 tooling path: Microsoft's official reference-only NuGet
package1.0.3 downloaded and SHA512 checked against its publisher catalog, with
inventory inspected before use. Extracting its named reference DLLs into private
build evidence was approval-blocked by the shell security layer. No bypass,
package install, package-target execution, global config or Windows qualification.
Framework target compilation remains blocked pending an approved extraction/build
path or a native Windows runner with its OS-provided references.
- https://learn.microsoft.com/en-us/dotnet/framework/migration-guide/reference-assemblies
- https://www.nuget.org/packages/Microsoft.NETFramework.ReferenceAssemblies.net48/1.0.3

## Two-stage staging transaction checkpoint (iteration 4)

`StagedPayload.cs` now joins the compiled approved runtime and source stages.
It requires distinct literal sibling destinations, returns only after verifying
both complete trees, and rolls back completed stages if the later operation
fails. Each cleanup independently proves ownership/integrity; unknown content
is retained and both the original failure and cleanup refusal are reported.
Pair Remove verifies BOTH trees before the first deletion, then uses the existing
nonrecursive removal. This is predelete validation, not atomic filesystem deletion:
a later I/O failure may leave partially removed files. No crash recovery exists;
in-memory receipts are lost on process exit. Do not infer persistent uninstall.

Actual Mac resource tests exercise the complete pinned payload, source refusal,
prior-byte preservation, overlap refusal and pair lifecycle. Separate test-only
fault injection exercises final-pair integrity, full/partial writes in either
stage, and each unknown-tree rollback refusal. No archive content is executed.
This is still only staging; final personal-plugin preparation, persistent lifecycle,
GUI and native Windows qualification remain unfinished.

## Source-byte provenance audit (iteration 4)

`scripts/audit_setup_source.py` is a separate developer-only gate. It authenticates
an explicitly approved source ZIP before parsing, validates a literal full commit,
derives exact source inventory from immutable Git tree objects and the versioned
independent allowlist, then compares EVERY selected blob's size and bytes. Git
replacement objects are disabled. Symlink/nonregular blobs, missing/extra/altered
files and a noncanonical derived manifest refuse. Neither archived source nor
Git source is imported, checked out, filtered or executed. The developer supplies
an absolute trusted Git executable; it is not end-user runtime discovery.

The preserved source-c038a6c.zip actually matched all47 source files plus its
derived manifest against c038a6c34399f615a622c8c685f8497d0b5dc237 using source-layout-v1.
Its SHA256 remains bc3dd90ae6a440f71d9214bf01ea1d90a14500ab1b124a2ac21fb663529e166c.
Layout-v2 explicitly adds this architecture document for subsequent bundles.
This closes that specific source-byte provenance gap, not source review, approved
native execution, payload-signing/distribution or Sig's independent-install goal.
Existing package metadata still says declared; future build gates must run the
auditor against their exact source inputs before compiling trust adapters.

## Transactional preparation output decision (iteration 5; before code)

To let the native controller own final-plugin writes/receipts rather than ask
Python to partially publish a tree, add an explicit `--plan` mode to the already
reviewed preparation helper. It renders the SAME disabled personal-plugin bytes,
bound to the supplied final location and this executing approved interpreter,
into a deterministic in-memory ZIP on stdout. It never creates the final plugin,
enables it, executes candidate code, changes settings or selects another Python.
Only personal-plugin mode is eligible; existing destinations still refuse.

This is an authenticated transformation design, not an archive trust shortcut.
The future native caller must verify its compiled source/runtime staging before
executing this exact helper, use the literal approved Python with -I -S, capture
bounded output without a shell and own the new-tree transaction. A user-supplied
ZIP/manifest/hash or stdout from an arbitrary process must NEVER authorize writes.
The archive itself is not a downloadable installer or an activation artifact.
Controller integration, output validation/budgets, cancellation, persistent
lifecycle and native execution remain separate unimplemented gates.

## Authenticated preparation process boundary (iteration 7)

The separate native feasibility harness actually passed on WindowsServer2025 at
5afc52a6335dbe9226192f2c3fd1fc66f9f40183: approved CPython3.14.7 executed the reviewed
--plan helper, produced8 rendered plugin files, and exact bytes/digests/bindings,
disabled identity and Verify/Remove passed. Compiled-resource tampering refused
before writes. This is NOT Windows11, GUI or authenticated Claude scan evidence.

The next production slice is `TrustedPreparation.Render`: it accepts only the
private-constructor StagedPayload receipt and derives the exact approved Python
and source helper internally. It validates native eligibility, literal matching
personal identity/final path, new destination and separate private empty scratch
sibling created exclusively through Bootstrap.CreateEmpty. Render requires the
scratch ownership receipt, not a caller-supplied directory path, and verifies its
empty inventory/identity before and after execution. Unknown scratch content is
retained, never deleted by Render. It verifies both staged input trees before and
after execution. It runs
only approved Python -I -S -B and helper --plan, with no shell/PATH/runtime override,
cleared child environment except SystemRoot/TEMP/TMP, and binary stdout/stderr.
Concurrent bounded readers, timeout and cancellation refuse partial output;
post-start errors terminate/wait for the trusted helper and preserve cleanup
errors. Unknown stop state requires retaining staged trees, never publication.

The reviewed helper does not spawn descendants. Kill()+WaitForExit is NOT a
sandbox, process-tree containment or crash recovery. Future helper changes adding
subprocesses require new containment review. No candidate code executes. Only a
test-symbol build exposes private runner injection to a reviewed self-child EXE.
Native Framework execution of this new boundary remains pending its exact CI SHA.
Mac process tests are not proof of Windows APIs or the approved Python runtime.

This component returns authenticated transformation bytes only: it does NOT parse
or publish a plugin, remove staging, persist receipts, activate Claude or implement
user consent/UI. Source receipt verification is authority, not an arbitrary ZIP's
self-reported manifest. Complete output validation/publication, durable lifecycle,
friendly GUI and Windows11 first-download acceptance remain unfinished. Existing
inert Marketplace/separate local-plugin lifecycle and all protection gates remain.

## Authenticated final publication (iteration 8)

`TrustedPreparation.Install` now calls Render internally, checks cancellation and
input receipts again, and passes authenticated bytes only to a private publisher.
No production caller can supply a plan ZIP, hashes or executable to this method.
The exact eight reviewed personal-plugin members are required; recomputed digests
must match the helper's exact canonical local manifest encoding. The manifest is
an integrity consistency check, never the trust anchor. Compressed16MiB, each8MiB
and aggregate16MiB expanded budgets are enforced. Bootstrap independently repeats
archive/type/path/hash validation before exclusive private writes and returns a
verified in-memory receipt. Partial write failure uses its existing guarded
rollback; unknown content is retained with original and cleanup errors.

Cancellation currently gates rendering and entry into final publication; final
bounded validation/write is synchronous, not a cancellable or crash-safe commit.
This slice does not remove staged runtime/source/scratch, persist receipts, enable
hooks or change settings. The controller must retain the bound runtime for the
plugin lifetime; it is not disposable staging after publication. A whole-setup
transaction and persistent safe lifecycle are still unfinished.

Portable injected inert-output tests cover exact bytes, inventory/manifest/type/
budget refusals, existing-byte preservation, partial write rollback and unknown
content retention. TestPublish exists only under PREPARATION_TESTS. Real native
harness now calls production Install and compares every final byte against the
independently generated approved-helper output; exact-SHA CI remains pending for
this new code. Prior658318c native Server2025 Render/process/scratch passed, not
Windows11/GUI/authenticated Claude. No ready installer is claimed.

## Authenticated ownership snapshot (iteration 9)

`ReceiptCodec` is a bounded snapshot component, NOT state-file persistence or a
persistent uninstaller. It serializes only a verified owned Bootstrap receipt,
including exact root/object paths, native identities, file sizes and hashes.
Production Seal/Open use OS Framework ProtectedData byte[] APIs with CurrentUser
and fixed application/version entropy; no packages or plaintext fallback. Other
build targets refuse. CurrentUser does not authenticate the originating app or
exclude hostile same-user/admin activity (outside the approved threat boundary).

Official API contracts checked before implementation2026-09-12:
- https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.protecteddata.protect?view=netframework-4.8
- https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.protecteddata.unprotect?view=netframework-4.8
- https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.dataprotectionscope?view=netframework-4.8

Protected bytes are limited to2MiB before Unprotect; only after authentication is
the explicit versioned binary schema parsed (1MiB,4096 entries,4096-byte UTF8
strings, bounded regular member paths/size/hash/type/hierarchy, canonical order).
Expected literal root and separate future state-file path are bound in the record.
Open verifies complete actual object identities/inventory/bytes before returning
an ownership receipt. Moved/changed/replaced/unknown trees refuse; no disk-tree
or user-manifest adoption. Codec performs no writes or deletion. Test-only raw
codec methods compile solely with RECEIPT_TESTS, never production symbols.

Portable tests prove schema/lifecycle/refusal and unsupported-platform behavior,
NOT DPAPI. Separate native production-symbol harness tests actual OS DPAPI and
no plaintext test entry points; native qualification remains pending for this
slice until exact-SHA CI is read. This is not Windows11/first-download/GUI proof.
Exclusive private state-file creation, safe receipt-file removal, persistence
failure/crash semantics, whole controller and friendly lifecycle remain unfinished.
DPAPI output alone must not be called durable ownership-safe uninstall.

## Persistent single-component state (iteration 10)

StateStore now writes a NEW private state directory and exclusively created
receipt.bin for one already verified component receipt. The outer Framework
CurrentUser DPAPI envelope binds exact state directory text, actual new directory
and file native identities, and the inner ReceiptCodec protected receipt. No
self-file hash is persisted inside itself: authenticated object identities plus
cryptographic contents and exact one-file inventory are the state authority.
Loaded ciphertext hash/length are recomputed only to verify those authenticated
objects still contain the bytes read; arbitrary disk inventory is never adopted.

Load bounds ciphertext before DPAPI, parses only after authentication, checks
version/strict UTF8/string/inner-length/trailing-data budgets and literal location,
then verifies both component and state inventories/identities/bytes. Store performs
real Load readback before success. Existing state is refused, not overwritten.
Write failures use a live ownership receipt whose partial bytes come only from the
owned file handle. Original write plus snapshot and guarded-cleanup failures are
retained. Unknown/replaced/unreadable state refuses cleanup and retains content;
the component is never removed because saving its state failed.

Remove verifies both complete trees before deleting the component, then the state.
This is NOT atomic or crash-recoverable: partial deletion may leave state referring
to a partially missing component; profile/DPAPI loss also blocks automatic removal.
No recovery fallback adopts files or weakens integrity. These are unfinished UX
and multi-component controller requirements, not qualified uninstall behavior.
No settings/activation/GUI or independently usable artifact is supplied here.

Separate test-symbol builds expose only inert plaintext codec and fault injection;
production symbols refuse off native Windows Framework. Portable roundtrip,
replacement/move/unknown/budget/schema and partial-write rollback tests do not prove
DPAPI. Native harness compiles production symbols, writes real DPAPI state and
launches its own reviewed test EXE to Load/Remove in a fresh process; exact-SHA
native result is required before claiming execution. Even that is WindowsServer
component evidence, not Windows11 ordinary-account/first-download/GUI qualification.

## Persistent pair lifecycle (iteration 11)

PairState composes two independently authenticated component/state records: the
bound runtime and disabled final plugin. Four exact literal nonoverlapping roots
are required. Save verifies both component receipts before writing, saves each
state exclusively, then verifies all four trees before success. On failure it
removes only successfully saved state containers, not components; unknown content
is retained and original plus every failed cleanup is preserved. Failed inner
Store owns its own partial-state rollback. Load requires explicit expected roots
and authenticates both records; no search, disk-tree adoption or plaintext fallback.

Remove verifies ALL FOUR before any deletion, then removes plugin+state before
runtime+state. This is not atomic, resumable, crash-safe or a whole installer.
A mid-delete I/O failure stops removal and can leave a partial tree; friendly
recovery and setup controller/consent/activation/UI remain unfinished. Caller role
labels are not independently authenticated pair membership: the trusted controller
must select the exact intended roots. Same-user/admin exclusions remain unchanged.

Portable inert test-symbol fixtures exercise nonempty pair reload/removal, aliases,
prewrite verification, partial-save rollback, all-four unknown inventory predelete
refusal and conserved cleanup errors. Production-symbol harness refuses on Mac;
real Framework DPAPI and fresh-process pair Load/Remove require exact-SHA native CI.
Prior365523a native single-component StateStore passed, not this new pair slice.
No candidate code executes; no Windows11/first-download/GUI qualification claimed.

## Typed preparation lifetime failures (iteration 12)

TrustedPreparation now reports bounded process failures as a sealed
ProcessFailureException with InputsReleased. True means launch was not attempted
or the approved child exited and all created reader tasks completed; it does NOT
prove tree ownership, authorize publication, cover descendants or provide crash
recovery. Generic exceptions outside this boundary confer no cleanup authority.
An attempted Start with no observable process conservatively retains input trees.
Kill failure does not skip independent bounded exit confirmation. All ordinary
operation, reader/stop and explicitly guarded Dispose errors are preserved; using
must not mask the original failure. False requires retaining runtime/source/scratch.
Any controller cleanup still must verify exact ownership/integrity separately.

Official Microsoft Kill/WaitForExit/Close API docs rechecked before code. Kill is
asynchronous and Dispose/Close is not termination proof. Test-only self-child stop,
reader-uncertainty and disposal-fault adapters are absent from production-symbol
builds. Injected uncertainty happens after stopping the actual fixture; this is
failure-path simulation, not a physical Windows process-kill failure reproduction.
Portable tests do not qualify Framework, Windows11 or a complete installer. This
slice supplies a prerequisite for controller rollback, not the controller or GUI.

## Bound runtime ownership handoff (iteration 12)

StagedPayload.CaptureRuntime verifies both staged trees and returns its original
runtime ownership receipt. RemoveSource verifies both again and removes only the
reviewed source. Caller must capture first and establish helper input release
before source retirement; these internal filesystem operations do not track a
process or infer stop authority. Unknown content in either tree refuses before
source deletion. After source retirement, a new capture from the incomplete pair
refuses; the earlier original runtime receipt remains usable for later verified
persistence/removal. No runtime relocation, disk-tree adoption, new archive trust,
whole controller or crash recovery is introduced. Portable tests compare EVERY
runtime byte after retirement and prove original receipt Verify/Remove; native
Framework exact-SHA evidence remains a separate gate.

## Worker supervision

Kaba's completed design response is evidence in
`/Users/kaba/trojaino-pilot-evidence/overnight-20260912/kaba-design-response.json`.
It recommended native bundled-runtime setup and noted unsigned-executable risk.
Its illustrative manifest checker is not accepted production code: incomplete
path/type/duplicate/resource validation, no external trust anchor, and no tested
rollback. Alpha owns implementation and execution. No worker claimed execution
is used as evidence.
