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

## Worker supervision

Kaba's completed design response is evidence in
`/Users/kaba/trojaino-pilot-evidence/overnight-20260912/kaba-design-response.json`.
It recommended native bundled-runtime setup and noted unsigned-executable risk.
Its illustrative manifest checker is not accepted production code: incomplete
path/type/duplicate/resource validation, no external trust anchor, and no tested
rollback. Alpha owns implementation and execution. No worker claimed execution
is used as evidence.
