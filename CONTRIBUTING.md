# Contributing

Thanks for helping improve AI Shield.

## Before opening a change

- Search existing issues and pull requests.
- Keep changes local, offline, deterministic, and evidence-first.
- Preserve the exact verdict vocabulary: `DO NOT RUN`, `CAUTION`, and `NO CRITICAL RISKS FOUND`.
- Never describe a scan result as safe, secure, certified, or a substitute for human review.
- Do not submit real credentials, private source, or unredacted third-party findings. Fixtures must use inert synthetic values.

## Development

AI Shield supports Python 3.11 and newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
python3 -m unittest discover -s tests -v
python3 -m aishield scan . --profile release --json
```

Risky fixtures intentionally produce nonzero CLI exit codes. A release-profile self-scan should produce `NO CRITICAL RISKS FOUND` and exit `0`.

## Pull requests

Use a focused branch and explain the behavior change, regression fixtures, commands run, expected scanner exit codes, and security or compatibility risks. Add a synthetic fixture and test for every new detection class. Keep refactors separate from behavior changes where practical.

By submitting a contribution, you agree that it is licensed under the GNU Affero General Public License version 3 only (`AGPL-3.0-only`), the same license as the project. You confirm that you have the right to submit the contribution under those terms.