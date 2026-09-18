# Native setup staging core — engineering only

This directory is not an independently usable installer. Do not send its test
binary, source, or SDK instructions to end users. A real development-preview WinForms
window and production-symbol x64 WinExe build now exist; neither has completed
the independent first-download/Windows11/Claude acceptance journey.

`Bootstrap.cs` implements pre-Python staging of one build-approved ZIP into a
new private final directory. It authenticates complete archive and member bytes,
validates bounded safe inventory, creates only new files, returns an in-memory
ownership receipt, verifies installed content, and removes only that receipt's
unchanged tree. On write failure it attempts verified nonrecursive rollback.
If a partial file cannot be verified or unknown content appears, it retains the
tree and reports both failure and cleanup refusal. It never activates hooks,
executes Python/candidate code, edits settings, changes PATH, downloads software,
or recursively deletes a tree. Existing destination errors do not trigger cleanup.

The generated calling-assembly adapter now supplies pins from developer-reviewed
inputs via `scripts/build_setup_resources.py`. It independently authenticates the
outer payload, fixed official runtime and separately approved source archive,
ignores the embedded manifest as a trust source, and compiles complete member
hashes. At run time it verifies its embedded resource digest before ZIP parsing
or writes. No end-user hash-input UI exists. A signed/friendly distribution path
is still unfinished. The library API is not a security boundary against malicious
callers in the same process. Receipts are intentionally not serializable and are
not a persistent uninstaller; do not reconstruct one from an untrusted manifest.

The target GUI architecture uses Windows 11's OS-provided .NET Framework 4.8.
Native Framework Server CI now exercises staging, real approved-runtime setup,
DPAPI ownership persistence and fresh-process removal. Those backend checks are
not Windows 11, SmartScreen, GUI or authenticated Claude acceptance. The portable
.NET 10 harnesses on macOS provide additional regression evidence, not native
qualification. `WindowsPreflight.cs` is wired before the first directory
creation: native AMD64 via IsWow64Process2, Fixed+NTFS, literal Windows spelling,
reserved devices, full member-path budgets, non-reparse ancestors, long-name and
final-handle parent equality. It refuses missing/failed probes without fallback.
Portable predicate tests are not proof of these native APIs or NTFS behavior.
The GUI selects the approved known-folder destination; this component
is not a general caller-selected extractor. The user chooses Install, not a path.
macOS identity code uses Darwin's stat64 ABI, not Linux. The approved threat
boundary excludes hostile same-user/admin/compromised-OS races; safeguards remain.

## Reopening an installation

`DefaultSetupDiscovery.Find()` selects existing default-profile identity hints,
then authenticates the exact persisted pair before returning it. It performs no
writes, runtime execution or cleanup. See [rediscovery](../../docs/setup-rediscovery.md)
for bounded enumeration, incomplete-state refusal and native test scope. The
friendly [consent/setup window](../../docs/setup-window.md) now uses this discovery
and the real disabled-install controller. `SetupProgram` guards the window with
an account-specific mutex, and the native workflow builds the embedded WinExe.
Consented local file removal uses fresh authenticated rediscovery and the owned
pair. It does not terminate Claude sessions, change settings or qualify effective
disablement. Effective Claude lifecycle, partial-output recovery and independent-
install qualification remain unfinished.

## Developer-only verification

The dependency-free .NET 10 harness links the actual core, not a rewritten model.
Use an explicit reviewed SDK and set these before its FIRST invocation:

```
DOTNET_CLI_HOME=<private build-tool home>
DOTNET_CLI_TELEMETRY_OPTOUT=1
DOTNET_GENERATE_ASPNET_CERTIFICATE=false
<absolute dotnet> run --project installer/friendly/tests/Bootstrap.Tests.csproj
```

Optional single developer-test argument: the official Python 3.14.7 embed x64
archive. The harness requires the literal published archive digest before reading
its inventory, exercises actual staging/Verify/Remove and compares every vendor
file byte. It NEVER executes that runtime. This is not an installer hash override.

`BOOTSTRAP_TESTS` adds fault-injection callbacks only to the test assembly; no
production build may define it. Tests exercise partial writes and cleanup refusal.
No new test dependencies, NuGet packages, or Python packages are installed.
See `docs/friendly-setup-architecture.md` for vendor/provenance decisions.

`resource-tests/Resources.Tests.csproj` separately compiles the actual generated
adapter plus embedded approved payload, without `BOOTSTRAP_TESTS`. It accepts
explicit developer MSBuild properties `GeneratedPayload` and `PayloadArchive`.
The harness stages runtime and source, independently compares every extracted
byte with the authenticated resource, verifies both receipts and removes them.
`--expect-tamper` is only a negative-test assertion, not an installer mode: compile
unchanged pins with a deliberately changed resource, then require digest refusal
before writes. Restoring a good resource requires a fresh build; do not run the
last tampered test binary as if it were the positive case.

This remains a .NET10 developer TEST assembly, not a Windows end-user executable.

`StagedPayload.cs` provides in-memory two-stage staging/Verify/Remove using ONLY
that compiled adapter. Distinct sibling destinations prevent overlapping receipts.
A later failure rolls back completed owned stages; unverified trees are retained
with original and cleanup errors. Pair Remove verifies both trees before deletion.
It is not atomic deletion, a crash-safe transaction, final-plugin setup, or a
persistent uninstaller. Process exit loses receipts; never reconstruct ownership
from an untrusted file. `transaction-tests/Transaction.Tests.csproj` embeds the
real approved payload with BOOTSTRAP_TESTS solely for injected write/integrity
failure coverage. Resource tests remain separately compiled without callbacks.

Windows11 ordinary-account, download/SmartScreen and actual GUI/lifecycle tests
remain required. No manual security-bypass instructions qualify the installer.
