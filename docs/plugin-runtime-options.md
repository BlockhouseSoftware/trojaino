# Runtime packaging decision for 0.3.1

0.3.1 retains one portable, sealed Python plugin payload and an explicit Python 3.11+ prerequisite. The two plugin commands do not install Python. The new readiness check and OS-specific recovery guide make missing prerequisites visible.

A bundled runtime could eliminate Python setup, but requires release artifacts for Windows x64/ARM64, macOS x64/ARM64 and supported Linux targets, a launcher that selects them, verified checksums, signing/notarization where applicable, license notices, and a runtime security-update policy. Cross-platform install tests must cover machines without Python. Native Claude Code installations do not imply that Node.js is installed, so replacing Python setup with an npm launcher would introduce another prerequisite.

Possible follow-up: publish platform archives containing the sealed scanner and a minimal runtime, referenced by immutable checksums. The launcher must not execute an unverified download. Validate archive size, install latency, upgrade behavior, offline behavior and missing-platform recovery before changing distribution. Do not recreate the old per-machine prepared plugin.

This is a packaging evaluation, not a claim that 0.3.1 bundles Python. Runtime bundling was identified as a later-release improvement in the 0.3.0 review; the immediate patch addresses correctness and readiness first.
