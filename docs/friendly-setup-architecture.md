# ADR: Explicit Windows setup

Status: implemented in slices; not yet an independently usable installer.
This design replaces a source-only/manual trial UX with the smallest reviewed,
user-consented pinned-runtime setup mechanism. It does not permit security
bypass instructions, automatic candidate execution, or claims of native
Windows 11 qualification.

## Why not a marketplace command source

Official Claude Code documentation was checked before implementation:
- https://code.claude.com/docs/en/plugin-marketplaces#command-sources
- https://code.claude.com/docs/en/plugin-marketplaces#copy-mode-and-link-mode
- https://code.claude.com/docs/en/plugins-reference#plugin-init

Command sources run a shell command and copy its output into the plugin cache,
and re-run in background sessions. Link mode is unsupported on Windows. Copy
mode does not preserve a final-path-bound sealed entry. Command sources are
therefore not a supported activation route for this runtime. No invented
install hook or schema extension is used. The marketplace stays inert
discovery/documentation; the separate personal skills-directory plugin is the
enable/disable/remove authority.

## Runtime provenance

The initial build input is the official CPython 3.14.7 Windows x64 embeddable
ZIP, not a Python chosen from PATH. The build verifies its exact pinned SHA-256:
`d297e5ff019966817ad8502465176139f2d3d840fa4ed84b13bed399a6ab1f15`
(https://www.python.org/ftp/python/3.14.7/python-3.14.7-embed-amd64.zip,
published digest at https://www.python.org/downloads/release/python-3147/).
This is HTTPS publisher-page provenance and exact byte pinning, not Sigstore or
Authenticode verification.

Per https://docs.python.org/3/using/windows.html#the-embeddable-package, the
embeddable package is designed for application-local distribution and has no
pip or Tcl/Tk. Its isolated `_pth` configuration stays unchanged; no
site-packages or dependencies are added; the Python license and every vendor
file are preserved. Initial platform support is x64 only; ARM64 must refuse
until a separately reviewed runtime and real tests exist.

The bundled runtime and reviewed setup executable are trust anchors. A manifest
inside a ZIP is not authenticity. The native launcher has the payload digest
compiled into reviewed code/resources, validates it before extracting or
launching Python, and executes only the absolute private runtime.

## Setup contract

A native, ordinary-account setup window with explicit consent and Install,
Verify, Disable and Remove actions. No PowerShell security bypasses, Python-path
entry, config-file editing, elevation or remote assistance. An unsigned binary
that triggers a blocking SmartScreen warning is an unresolved usability gate,
not an instruction to click through.

Setup validates a pinned offline payload before writing it, creates only fresh
private versioned directories, and prepares the disabled plugin directly in its
final skills location using the guarded writer and sealed binding. It never
relocates prepared hooks. Complete integrity/readiness verification precedes a
separate explicit enable action. Settings changes are user-consented, narrowly
scoped, preserve unrelated settings and are read back. Existing-destination
refusal preserves all previous bytes. Failed preparation never activates a
partial plugin. Rollback/removal proves ownership and never recursively deletes
an unverified or substituted tree.

Verification distinguishes installed-disabled, enabled, actual SessionStart
hook evidence and authenticated scan evidence. A built EXE or macOS execution
cannot stand in for these. Disable/removal warns to close/restart existing
sessions. Marketplace removal does not remove this separately installed
component.

## Native bootstrap

The setup program is a C# Windows GUI on the OS-provided .NET Framework 4.8
(4.8.1 on Windows 11 22H2 and newer), not an Inno overwrite installer and not a
PowerShell launcher. .NET is never installed and the process never elevates.
.NET single-file self-contained was considered and rejected: it adds another
bundled runtime and native-library extraction before application code.

References:
- https://learn.microsoft.com/en-us/dotnet/framework/get-started/system-requirements
- https://learn.microsoft.com/en-us/dotnet/api/system.io.compression.ziparchive
- https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createdirectoryw
- https://learn.microsoft.com/en-us/dotnet/core/deploying/single-file/overview

The native core receives immutable build-authorized archive and file hashes
from the executable's compiled resources. No caller-facing override, archive
manifest, PATH runtime or downloaded candidate supplies trust. It validates the
exact archive hash before ZIP parsing, exact safe member inventory/types and
bounded decompression, then each file's digest before any filesystem side
effect.

`CreateDirectoryW` with a private security descriptor provides exclusive root
creation (`Directory.CreateDirectory` accepts existing directories and is
unsuitable). Files are created with `CreateNew` only. Reparse ancestors are
refused. An in-memory receipt of created paths/hashes is kept; the complete
tree is inspected before removal; unknown trees are never recursively deleted.
POSIX exclusive `mkdir` lets the same transaction tests run on macOS but does
not certify Win32 ACLs, reparse handling or locks. No extraction runs Python.

## Windows eligibility

Before the first directory creation: require a literal drive-qualified Windows
path, existing non-reparse ancestors and a local fixed NTFS volume. Reject UNC,
device, drive-relative, slash-normalized, dot-component, ADS, trailing-dot/space,
reserved-device and over-budget paths. Bound the final member paths without
requiring long-path registry changes. Preserve valid Unicode/spaces in user
names. Check the existing parent with `GetLongPathNameW` rather than a tilde
test. Never silently normalize or rebind.

Use `IsWow64Process2`'s native-machine output for x64 eligibility, not
`GetNativeSystemInfo`, which can report emulated x64 on ARM64. Missing API or
probe failures refuse setup rather than falling back.

References:
- https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file
- https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getlongpathnamew
- https://learn.microsoft.com/en-us/windows/win32/api/wow64apiset/nf-wow64apiset-iswow64process2
- https://learn.microsoft.com/en-us/windows/win32/api/sysinfoapi/nf-sysinfoapi-getnativesysteminfo
- https://learn.microsoft.com/en-us/dotnet/api/system.io.driveinfo.drivetype
- https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfinalpathnamebyhandlew
- https://learn.microsoft.com/en-us/windows/win32/sysinfo/image-file-machine-constants

## Components

**Compiled resource adapter** (`scripts/build_setup_resources.py`). Renders
developer-supplied literal outer/source pins and the fixed official runtime pin
into one explicitly named embedded C# resource with full validation and
recomputation. Its complete digest is checked before opening ZIP structure;
complete compiled inner archive/member pins are then passed to the native
stager. `StageRuntime`/`StageSource` have no hash or runtime-path override and
do not run Python, prepare a plugin, activate hooks or persist a receipt.

**Two-stage staging transaction** (`StagedPayload.cs`). Joins the compiled
runtime and source stages. Requires distinct literal sibling destinations,
returns only after verifying both complete trees, and rolls back completed
stages if the later operation fails. Each cleanup independently proves
ownership/integrity; unknown content is retained and both the original failure
and cleanup refusal are reported. Pair Remove verifies both trees before the
first deletion. This is predelete validation, not atomic deletion.
`CaptureRuntime` returns the original runtime ownership receipt; `RemoveSource`
retires only the reviewed source after helper inputs are released.

**Source-byte provenance audit** (`scripts/audit_setup_source.py`). A
developer-only gate that authenticates an approved source ZIP before parsing,
validates a literal full commit, derives the exact source inventory from
immutable Git tree objects and a versioned layout allowlist, then compares
every selected blob's size and bytes. Git replacement objects are disabled.
Symlink/non-regular blobs, missing/extra/altered files and a non-canonical
derived manifest refuse. Neither archived nor Git source is imported, checked
out or executed. Historical layouts stay frozen so older archives still audit.

**Transactional preparation output** (`prepare_preflight_plugin.py --plan`).
Renders the same disabled personal-plugin bytes, bound to the supplied final
location and the executing approved interpreter, into a deterministic
in-memory ZIP on stdout. It never creates the final plugin, enables it,
executes candidate code, changes settings or selects another Python. A
user-supplied ZIP/manifest/hash or stdout from an arbitrary process never
authorizes writes.

**Authenticated preparation** (`TrustedPreparation.Render` / `Install`).
Accepts only the private-constructor `StagedPayload` receipt and derives the
approved Python and source helper internally. Validates native eligibility,
literal identity/final path, new destination and a separate private empty
scratch sibling created exclusively through `Bootstrap.CreateEmpty`. Runs only
approved Python `-I -S -B` with the helper's `--plan`, no shell/PATH/runtime
override, a cleared child environment except `SystemRoot`/`TEMP`/`TMP`, and
binary stdout/stderr. Bounded readers, timeout and cancellation refuse partial
output. `Install` passes authenticated bytes only to a private publisher that
requires the exact reviewed member set, recomputes digests against the
helper's canonical manifest, enforces 16 MiB compressed / 8 MiB per member /
16 MiB aggregate budgets, and repeats archive/type/path/hash validation before
exclusive private writes. `Kill()+WaitForExit` is not a sandbox or crash
recovery; process failures surface as `ProcessFailureException` with
`InputsReleased`, and generic exceptions confer no cleanup authority.

**Ownership snapshot and persistent state** (`ReceiptCodec`, `StateStore`,
`PairState`). `ReceiptCodec` serializes only a verified owned Bootstrap
receipt (exact root/object paths, native identities, sizes, hashes) with
Framework `ProtectedData` CurrentUser and fixed application/version entropy;
other build targets refuse; no plaintext fallback. Protected bytes are bounded
to 2 MiB before Unprotect and the versioned binary schema is bounded after
authentication. `StateStore` writes a new private state directory and an
exclusively created `receipt.bin` bound to exact directory text and native
identities; Load parses only after authentication and verifies both component
and state inventories; existing state is refused, never overwritten.
`PairState` composes the bound runtime and disabled final plugin as four
literal non-overlapping roots, verifies all four before any deletion, and
removes plugin+state before runtime+state. None of this is atomic, resumable or
crash-safe; a mid-delete I/O failure stops removal and can leave a partial
tree. CurrentUser DPAPI does not authenticate the originating application or
exclude hostile same-user/admin activity.

References:
- https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.protecteddata.protect?view=netframework-4.8
- https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.protecteddata.unprotect?view=netframework-4.8
- https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.dataprotectionscope?view=netframework-4.8

**Six-role prewrite gate** (`SetupLocations.Check`). A read-only prerequisite,
not the transaction. Refuses unsupported runtimes before probes, snapshots root
strings, and jointly checks runtime, source, scratch, final plugin, runtime
state and plugin state: literal spelling, role equality/ancestry refusal, exact
staging sibling parents and a matching personal-plugin basename. Path budgets
use compiled inventory arrays generated from the approved archives. Native
Check requires all existing supported non-reparse parents and all absent
destinations; it never creates directories or adopts ownership, and its return
is not a reservation.

Further components — the default-profile plan, shared-parent provisioning,
rediscovery, the controller transaction, account preference editing and the
setup window — each have their own document in this directory.

## Test tiers

Portable tests (macOS/Linux) exercise decision logic, fault injection and
byte-exact behavior with test-only symbols that production builds omit. Native
Windows Server Framework tests compile production symbols, execute the approved
Python, write real DPAPI state and re-load it in a fresh process; they run at
an exact commit SHA in CI. Neither tier is Windows 11 ordinary-account,
first-download/SmartScreen, visual/keyboard or authenticated-Claude
qualification; those remain release gates.
