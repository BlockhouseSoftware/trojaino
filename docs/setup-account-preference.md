# Account preference integration — engineering checkpoint

The friendly window does not yet implement Enable or Disable. A pure document
editor is not a settings writer, effective protection, or an independently usable
installer. The existing native missing-controls RED remains intentional until the
whole consented transaction is implemented.

## Implemented document behavior

`AccountPreferenceDocument.Edit` is an internal, IO-free transformation. It
accepts only the exact setup identity `trojaino-local-{32 lowercase hex}@skills-dir`
and a Boolean preference. It validates strict UTF-8 JSON, rejects a BOM, duplicate
decoded names in any object, malformed/unpaired Unicode, nonobject settings/map,
and non-Boolean map values. Both input and output are bounded to 1 MiB, depth 32
(root is depth zero), and 16,384 values. It changes only the selected Boolean token
or inserts the required member; unrelated UTF-8 bytes, whitespace, escape spelling
and arbitrary numeric lexemes remain exact. It neither authenticates the supplied
identity nor grants filesystem authority. The future controller must derive that
identity from fresh authenticated discovery and explicit displayed consent.

Portable RED/GREEN and independent differential review are recorded in
`/Users/kaba/trojaino-pilot-evidence/continuous09-document-review.json`. Native
Framework compilation at `70e2f0d` failed because the new compiler invocation read
machine csc.rsp in addition to explicit pinned references. The reviewed `/noconfig`
correction at `62c217ab65eb2be6a3b70931b243c3b771585e5f` compiled and ran the
actual native Framework document tests and real self-child settings-lock negatives.
The exact native handoff annotation was decoded and checked in
`/Users/kaba/trojaino-pilot-evidence/continuous09-native-document-lock-decoded.json`.
It proves lossless bounded edits and exclusive-handle refusal of child write/rename
and our own path replacement, preserving both test file identities and bytes.
The overall native job remains intentionally RED at the missing account-enable
controls; later full transaction assertions did not run. Native Windows Server
primitive evidence is not settings publication, journal recovery, GUI activation
or Windows11 acceptance.

## Transaction experiment — not yet connected to the window

`AccountPreferenceTransaction` now has an unfinished existing-file implementation
and an isolated native fixture harness. It retains account/installation handles,
protects exact original and intended settings in a separate immutable recovery
record before any target mutation, and edits through one exclusive target handle.
It never automatically restores, removes recovery records, or deletes settings.
A pending record blocks the next actual mutation. Missing settings and guided
recovery resolution are not implemented; no Enable control calls this code yet.

The initial missing-type RED and portable platform-refusal compile are recorded
in `continuous10-transaction-red.txt` and
`continuous10-transaction-portable-corrected.txt`. These are NOT native transaction
GREEN. Early independent review `continuous10-transaction-early-review.json`
permits isolated testing but found a discarded newly-created recovery-root receipt.
The native regression at `afea30138547af4b8e6cb0f1f1f710506739d213` actually reached
`ASSERT: recovery root substitution was adopted before account mutation` after
the ten boundary-exception cases. The correction now retains the original
creation receipt and compares it to the acquired root guard before creating a
journal. Native correction at `f3a7f7a232851bcdbb63dac2465cb88337ca3102`
passed the root-retention assertions and all ten boundary cases. The same native
run passed the complete existing false-to-true transaction, exact saved original,
unchanged target identity, stale consent, no-op and second-mutation refusal, and
original recovery after uninstall. The job still fails at the separate missing
account-enable UI controls. These boundary exceptions are not physical I/O failures.
A separate native test at `0c89759bc162cc569cfaf62b3fb6222812d725d1` then failed
`ASSERT: partial fault did not preserve a genuinely changed incomplete target`.
Only after that RED, the test-symbol injection was corrected to write through the
first differing byte, retaining the original suffix. Native `52a3d2fbd5bdce7eda06eb50a1ea2fb2492f23d4`
passed that exact changed-partial assertion plus the full account transaction
suite; the job still fails at the missing account-enable UI. Production whole-write
semantics are unchanged. No complete recovery or UX claim follows.

## Transaction design selected for native testing

Compare then ReplaceFile is not an atomic conditional update: a concurrent Claude
save can occur between comparison and publication. A retained deny-delete handle
also prevents our own path replacement. Do not close the handle, relax sharing,
ignore merge/ACL errors or use a stale whole-file backup to evade this limitation.

For an existing settings file, the reviewed direction is one retained exclusive
read/write handle over the fixed OS-derived account location, with pinned ordinary
ancestors and same-handle native identity checks. Read/validate the current bytes
only after acquisition; an already-requested preference performs no writes,
including no journal writes. Before ANY target mutation, exclusively create,
protect, flush and authenticate a rediscoverable original-byte recovery record.
Preserve both original and intended bytes with exact purpose, location, native
identities and operation bindings. Keep this separate from the strictly inventoried
plugin/runtime state; do not add unknown files to an existing ownership receipt.
Then perform the lexical edit, exact EOF, flush and readback through the same held
target handle. File settings remain user data, never installer-owned deletion
objects. The installer mutex does not coordinate other applications; native share
exclusion and fresh acquisition are required.

This direction is an unfinished writer experiment, not a qualified transaction.
Native acquisition, write ordering, temporal fault tests, protected journal discovery, fresh-process
recovery and a real window transaction are required. Absent settings needs a
separate no-replace creation path, never an overwrite fallback. Native primitive
sharing tests alone prove neither publication nor journal durability.

## Preservation and recovery contract

Jose requires safe preservation and understandable recovery, not a fabricated
promise that settings.json remains unchanged at its original path after every
possible failed write or power loss. The earlier design review inferred that
stronger guarantee; its rejection of unjournaled in-place updates is valid, but
that inference is not a user-approved scope requirement.

Pre-write refusal leaves settings unchanged. Successful edits preserve every
unrelated byte. Once mutation can begin, the exact original must already be safely
retained in the authenticated recovery record. Partial/uncertain outcomes must say
so and preserve original plus secondary errors. A same-uninterrupted-exclusive-
handle restoration can be tested; after losing that authority, automatic stale
whole-file rollback is forbidden. Even same file ID or plausible partial bytes
cannot prove another ordinary editor has not changed the file. Recovery is a
fresh explicit version-bound choice; preserve the current version before any
approved restoration, retain unknown/conflicting content and provide a friendly
in-app path rather than manual configuration homework. Removal must not destroy
unresolved original settings records.

The storage failure model and durable journal discovery require native evidence.
Do not claim arbitrary power-loss survival, kernel transactions, application-origin
DPAPI authenticity against hostile same-user software, or automatic crash recovery
from a flushed byte array. The direct user-scope, ownership, unknown-content,
concurrency and nontechnical-user requirements are unchanged.

Success wording must distinguish “Account preference saved; protection not
verified.” Project/local/managed preferences can override user preferences. User
false is not universal disable and does not unload existing hooks. Real fresh
Claude enable/scan/disable/re-enable/remove, Windows11 ordinary-account visual and
keyboard use, first-download/SmartScreen and release approval remain separate gates.

## Read-only recovery status experiment

Native `ff26873b7bb9e3dc7444856d5be498c02c7e889d` actually failed
`ASSERT: authenticated read-only account recovery status is missing` after the
real transaction and uninstall. The new reader was authored after this RED.
It independently resolves fixed account paths, authenticates the existing journal,
and returns immutable historical identity/preference and version-hash metadata.
Dedicated read-only, shared-read handles pin the record and current target while
classifying Original, Intended, Changed, Replaced or Missing. A different native
file identity wins over equal bytes. Only absent recovery root yields null;
unknown, partial, unsafe, inaccessible or invalid records refuse without cleanup.
No plaintext settings, mutable byte arrays or deletion receipts are returned.

The reader does not depend on a current installation and performs no restore,
acknowledgement, settings creation or journal removal. Errors retain primary and
close diagnostics; snapshots are not future write authority. Null/Unavailable
presentation, version lengths, typed issue guidance and actual window integration
are not implemented by this bounded reader. Existing-file transaction no-op and
second-mutation refusal rules are unchanged.

Native followup tests require shared-read compatibility, immutable properties,
all five classifications, same-byte replacement, unknown record preservation and
a self-child receiving only fixture OS folders after uninstall. Their new native
execution is pending; portable compile/platform refusal is not GREEN for DPAPI.
Remaining negatives include corruption/replay/alias/ACL/size/cleanup failures and
read-path temporal instrumentation. Friendly recovery display and fresh version-
bound consent/restoration remain engineering, not a user configuration chore.

Detailed read-only design reviews, including required native fault and recovery
cases, are `continuous09-settings-design-review.json` and
`continuous09-journal-design-review.json` in the evidence directory. They approve
bounded implementation experiments, not the full feature or release.
