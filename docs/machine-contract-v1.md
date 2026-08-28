# Trojaino Machine Contract v1

Machine Contract v1 makes Trojaino's JSON report safe to consume in local automation, CI, and future integrations. It is a contract for deterministic scanner output; it is not a safety guarantee and it never delegates suppressions to the scanned repository.

## Compatibility

`schema_version` is `"1.0.0"`. Within schema v1, existing fields retain their names and meanings, and compatible changes are additive. A breaking report change requires a new schema version.

`scanner_version` identifies the Trojaino build. `rule_pack` identifies the deterministic rule set. `scan_profile` records the selected profile while retaining the existing top-level `profile` field for compatibility.

## Rule IDs

Every finding has a unique public rule ID from the immutable central registry in `trojaino/rules/registry.py`. Rule IDs are never reused. Retire an obsolete ID instead of repurposing it; a material change to a rule's security meaning requires a new ID and rule-pack version.

## Finding fingerprints

Each finding includes a deterministic `fingerprint`: a SHA-256-derived identity over its rule ID, normalized relative path, location, and normalized evidence. It is stable for equivalent input and helps correlate the same occurrence across reports. It is not a cryptographic claim about the scanned artifact.

## Schema and examples

The normative schema is [`schemas/trojaino-report-v1.schema.json`](../schemas/trojaino-report-v1.schema.json).

JSON example:

```json
{
  "schema_version": "1.0.0",
  "scanner_version": "0.1.5",
  "rule_pack": {"id": "trojaino-core", "version": "1.0.0"},
  "scan_profile": {"id": "default"},
  "findings": [{"id": "PKG_REMOTE_LIFECYCLE_EXEC", "fingerprint": "e7d2c69c46fd1f1e204a16c4"}]
}
```

Text and HTML reports show the same stable rule ID alongside each finding. JSON remains the complete machine-readable record.

## Verification

The test suite validates emitted finding IDs against the registry, validates generated JSON using the published schema, and checks deterministic fingerprints and normalized report fields across equivalent fixture copies.
