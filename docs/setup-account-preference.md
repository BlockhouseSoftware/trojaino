# Account preference integration

The setup window's Enable and Disable controls edit the user's Claude account
settings through the components below. A settings editor is not effective
protection or a complete installer; see [setup-window.md](setup-window.md) for
the UI contract.

## Document editor

`AccountPreferenceDocument.Edit` is an internal, IO-free transformation. It
accepts only the exact setup identity `trojaino-local-{32 lowercase hex}@skills-dir`
and a Boolean preference. It validates strict UTF-8 JSON, rejects a BOM,
duplicate decoded names in any object, malformed/unpaired Unicode, non-object
settings/map, and non-Boolean map values. Both input and output are bounded to
1 MiB, depth 32 (root is depth zero), and 16,384 values. It changes only the
selected Boolean token or inserts the required member; unrelated UTF-8 bytes,
whitespace, escape spelling and arbitrary numeric lexemes remain exact. It
neither authenticates the supplied identity nor grants filesystem authority.
The controller derives that identity from fresh authenticated discovery and
explicit displayed consent.

Native Framework tests exercise lossless bounded edits and exclusive-handle
refusal of child write/rename and path replacement, preserving both test file
identities and bytes.

## Transaction

`AccountPreferenceTransaction` retains account/installation handles, protects
the exact original and intended settings in a separate immutable recovery
record before any target mutation, and edits through one exclusive target
handle. It never automatically restores, removes recovery records, or deletes
settings. A pending record blocks the next mutation. It retains the original
recovery-root creation receipt and compares it to the acquired root guard
before creating a journal, so a substituted recovery root is never adopted.

Native tests cover the complete existing false-to-true transaction, exact
saved original, unchanged target identity, stale consent, no-op and
second-mutation refusal, original recovery after uninstall, ten boundary
exception cases, and a partial-write fault that must preserve a changed
incomplete target (the injected fault writes through the first differing byte
and retains the original suffix).

### Design rationale

Compare-then-`ReplaceFile` is not an atomic conditional update: a concurrent
Claude save can occur between comparison and publication. A retained
deny-delete handle also prevents our own path replacement. The handle is not
closed, sharing is not relaxed, merge/ACL errors are not ignored, and a stale
whole-file backup is never used to evade this limitation.

For an existing settings file: one retained exclusive read/write handle over
the fixed OS-derived account location, with pinned ordinary ancestors and
same-handle native identity checks. Current bytes are read and validated only
after acquisition; an already-requested preference performs no writes,
including no journal writes. Before any target mutation, a rediscoverable
original-byte recovery record is exclusively created, protected, flushed and
authenticated, preserving original and intended bytes with exact purpose,
location, native identities and operation bindings. This record is kept
separate from the strictly inventoried plugin/runtime state. The lexical edit,
exact EOF, flush and readback then happen through the same held target handle.
Settings files remain user data, never installer-owned deletion objects. The
installer mutex does not coordinate other applications; native share exclusion
and fresh acquisition are required. Absent settings need a separate no-replace
creation path, never an overwrite fallback.

## Preservation and recovery contract

The requirement is safe preservation and understandable recovery, not a
promise that `settings.json` remains unchanged at its original path after every
possible failed write or power loss.

Pre-write refusal leaves settings unchanged. Successful edits preserve every
unrelated byte. Once mutation can begin, the exact original is already safely
retained in the authenticated recovery record. Partial/uncertain outcomes say
so and preserve the original plus secondary errors. Restoration through the
same uninterrupted exclusive handle can be tested; after losing that authority,
automatic stale whole-file rollback is forbidden, because even the same file ID
or plausible partial bytes cannot prove another editor has not changed the
file. Recovery is a fresh, explicit, version-bound choice: preserve the current
version before any approved restoration, retain unknown/conflicting content and
provide a friendly in-app path rather than manual configuration work. Removal
never destroys unresolved original settings records.

Not claimed: arbitrary power-loss survival, kernel transactions, application-
origin DPAPI authenticity against hostile same-user software, or automatic
crash recovery from a flushed byte array.

Success wording distinguishes "Account preference saved; protection not
verified." Project/local/managed preferences can override user preferences.
User `false` is not universal disable and does not unload existing hooks.

## Read-only recovery status

The status reader independently resolves fixed account paths, authenticates the
existing journal, and returns immutable historical identity/preference and
version-hash metadata. Dedicated read-only, shared-read handles pin the record
and current target while classifying Original, Intended, Changed, Replaced or
Missing. A different native file identity wins over equal bytes. Only an
absent recovery root yields null; unknown, partial, unsafe, inaccessible or
invalid records refuse without cleanup. No plaintext settings, mutable byte
arrays or deletion receipts are returned.

The reader does not depend on a current installation and performs no restore,
acknowledgement, settings creation or journal removal. Errors retain primary
and close diagnostics; snapshots are not future write authority.

## Remaining gates

Real fresh Claude enable/scan/disable/re-enable/remove, Windows 11
ordinary-account visual and keyboard use, first-download/SmartScreen and
release approval remain separate gates. Remaining negative cases include
corruption/replay/alias/ACL/size/cleanup failures and read-path temporal
instrumentation.
