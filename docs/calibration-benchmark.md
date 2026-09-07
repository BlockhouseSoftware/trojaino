# Calibration benchmark methodology

Trojaino's public calibration corpus contains 20 committed **synthetic** fixture targets. It is a reproducible regression/calibration instrument, not a vulnerability ranking of third-party software and not a claim that any project is safe.

## Run it

```bash
python scripts/run_calibration_benchmark.py
```

The runner scans fixture paths only; it does not execute target code, install dependencies, fetch the network, or follow the manifest outside `tests/fixtures/`. It writes deterministic JSON summaries plus a clean and finding-heavy HTML/JSON example to `benchmark/artifacts/`.

## Labels and interpretation

- **unsafe**: the fixture intentionally includes at least one scanner stop-and-review signal.
- **review**: the fixture represents an actionable but non-blocking caution signal.
- **benign**: the fixture represents normal code, documentation, test, or controlled-command context. It may retain review/example-context findings without changing the verdict.

The aggregate output separates per-label finding burden from expected unsafe detection. It deliberately does **not** publish precision, recall, or a safety claim: the corpus is synthetic and every result requires human interpretation.

## Adjudication rule

Before a public benchmark update is accepted, a reviewer must inspect every generated finding and record whether it is expected actionable evidence, expected review evidence, or expected test/documentation context. Any unexpected rule ID, changed disposition, incomplete scan, or changed expected verdict blocks publication until the manifest, fixture, rule, and report are reviewed together.

## Known limits

- The corpus is not an external-repository census and does not measure general recall.
- It does not exercise dependency vulnerability databases, obfuscated runtime payloads, dynamic execution, or full dataflow analysis.
- The two committed example reports are generated from synthetic fixtures only; no private source, real credentials, or raw third-party findings are published.
- `NO CRITICAL RISKS FOUND` means only that the current deterministic rules did not produce a critical stop signal for that scan. It is not a safety certification.
