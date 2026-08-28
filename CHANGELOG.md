# Changelog

All notable changes to Trojaino are documented here.

## 0.1.5 - Unreleased

### Machine contract

- Introduced Machine Contract v1 for JSON scan reports (`schema_version: "1.0.0"`).
- Added immutable `trojaino-core` rule-pack identity and deterministic finding fingerprints.
- Published the checked-in JSON Schema at `schemas/trojaino-report-v1.schema.json`.
- Existing JSON fields and meanings remain compatible; compatible changes are additive within schema v1.

### Rule lifecycle

- Rule IDs are public, unique, and never reused. Retired rules remain documented as retired.
- A material security-meaning change receives a new rule ID and rule-pack version.

### Verdicts

- No verdict threshold changes in this release.

## 0.1.4.1

- Windows installer and scanner improvements.
