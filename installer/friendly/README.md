# Native setup staging core — engineering only

This directory is not an independently usable installer. Do not send its test
binary, source, or SDK instructions to Sig. No GUI or end-user EXE exists here.

`Bootstrap.cs` implements pre-Python staging of one build-approved ZIP into a
new private final directory. It authenticates complete archive and member bytes,
validates bounded safe inventory, creates only new files, returns an in-memory
ownership receipt, verifies installed content, and removes only that receipt's
unchanged tree. On write failure it attempts verified nonrecursive rollback.
If a partial file cannot be verified or unknown content appears, it retains the
tree and reports both failure and cleanup refusal. It never activates hooks,
executes Python/candidate code, edits settings, changes PATH, downloads software,
or recursively deletes a tree. Existing destination errors do not trigger cleanup.

Trust inputs must be supplied by the reviewed calling assembly's compiled build
resources, not a user input or manifest supplied alongside an untrusted ZIP.
The build resource generator and signed/friendly distribution path are unfinished.
The library API is not a security boundary against malicious callers in the same
process. Receipts are intentionally not serializable and are not a persistent
uninstaller; do not reconstruct one from an untrusted on-disk manifest.

The target GUI architecture uses Windows 11's OS-provided .NET Framework 4.8.
The current core has only been compiled/executed with .NET 10 on macOS. Native
Framework compilation, Win32 ACL/NTFS identity tests, and Windows 11 usability
remain gates. Native code currently requires NTFS for receipt identity. Path
spelling/volume eligibility must be fully preflighted before the eventual GUI
accepts a destination; this component is not a general caller-selected extractor.
Only an approved caller-chosen final path is within the tested staging contract.
macOS identity code uses Darwin's stat64 ABI, not Linux. The approved threat
boundary excludes hostile same-user/admin/compromised-OS races; safeguards remain.

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
