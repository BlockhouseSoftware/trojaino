# ADR: Sealed marketplace runtime image

Status: implemented locally; user-scope boundary explicitly approved by Jose in Telegram (“Proceed with user-scope and 3.”). Independent review under that approved boundary and native Windows acceptance remain required. See marketplace-requirements.md for the recorded decision; same-user concurrent mutation is excluded, not claimed prevented.

## Trust boundary

The explicit, reviewed Python interpreter (including its standard library) and
reviewed generated `scripts/preflight.py` are trust anchors. A user-scope Python
plugin cannot protect either from arbitrary code already running as that same
user, an administrator, a debugger, or a compromised OS. This architecture does
not claim otherwise. Authenticity comes from an externally reviewed/pinned
release, not a hash stored beside the executable it purportedly authenticates.

The runtime import boundary starts after Python has read the trusted entry.
No candidate code runs during scanning. Candidate launch remains the existing
restricted inspection-session workflow, not an OS sandbox.

## Decision

Generate one self-contained entry from reviewed source and a small bootstrap.
The entry embeds the complete Python source map and literal version. Imports of
`trojaino` and all its submodules are intercepted by a memory-only loader; an
absent module raises rather than falling through to disk. Ambient `trojaino.*`
modules are evicted. No `.pyc` files are written or loaded. Runtime metadata does
not consult the interpreter directory, installed packages, or checkout parents.

Worker processes receive the captured source map and bootstrap through a bounded
pipe capsule. A digest passed independently in argv is checked before executing
the capsule. That digest binds parent-to-child transport; it is not a signature
or publisher identity. Workers do not reopen the entry, runtime tree, or source
checkout. The short child bootstrap avoids Windows command-line length limits.
Hook input follows the capsule on the pipe; the parent enforces a process timeout
without waiting indefinitely on the hook input reader.

Scanner identity binds the captured source map and version. Receipts from the
old disk-runtime implementation are intentionally incompatible: rescan with the
new image rather than authorizing across different runtime identities.

## Build and preparation

`build_sealed_runtime.py` renders deterministically from canonical source; the
checked-in generated entry must match a fresh render byte for byte. The only
source transformation replaces the discovery-based package initializer with the
literal build version. No target code or source module is imported by the builder.

Preparation must construct all final bytes (including hooks and their manifest)
before publication and write through pinned directory descriptors/Windows handles.
No post-copy path-based patching of executable manifests. The destination is new,
private and explicit; existing destinations are rejected within the approved
user-scope boundary. This is not an atomic no-substitution guarantee against a
hostile same-user process. Descriptor/handle checks resist the tested path
redirections; the precise limitations below remain part of the contract.

## Preparation verification limits

Creation, metadata capture, and directory open are separate OS calls. We compare
the captured identity to the held identity, reject nonempty acquired directories,
use exclusive file creation, and verify exact directory inventories. This detects
the reproduced substitutions; it does not prove that a malicious same-user process
could never substitute an empty private directory before the first metadata read.
POSIX ancestor names are rechecked against held descriptors before success, but
those checks are not an atomic namespace transaction. A privileged or same-user
concurrent writer remains outside an absolute publication-integrity guarantee.
If that stronger guarantee is required, setup needs a separate OS authority, not
another path check. This limitation remains explicit for independent acceptance.
Windows holds all acquired directory and exclusive file handles until publication;
its actual sharing and ACL behavior still requires native verification.

Worker output is written to a temporary file and checked after process completion.
The scanner's report budget limits normal output; the transport check itself is
not a live disk-quota enforcement mechanism.

## Acceptance evidence and limits

Tests cover standalone scan, generated hook prefix, worker/source identity,
entry/runtime replacement, corrupt capsule rejection before execution, and
preserved hook input. The ordinary source API remains available for its existing
unit tests; marketplace workers have no disk-import fallback.

Native Windows job containment, pipe behavior, ACLs, path locking and Claude hook
transport still require actual Windows execution. macOS test results cannot
qualify these. Release publication, installation and user rollout remain gated.
