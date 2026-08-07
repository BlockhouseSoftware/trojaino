# AI Shield v0.1.0

AI Shield is a local deterministic trust scanner for AI-built and downloaded software. The first version focuses on Node/TypeScript projects, MCP/tooling repos, Docker configs, and agent instruction files.

It is intentionally not a generic "ask an LLM to review this repo" wrapper. v0.1 runs repeatable rule packs and produces evidence-first findings with a conservative verdict:

- `DO NOT RUN`
- `CAUTION`
- `NO CRITICAL RISKS FOUND`

It never says software is "safe" or "certified secure."

## Repository scope

This repository contains only the product source, public documentation, tests, and synthetic fixtures needed to verify detections. Company strategy, private requirements, decks, raw scan reports, screenshots, and generated evidence live outside this repository.

Generated reports should be written to a local-only workspace. A report belongs in this repository only when it is deliberately selected as a public example, sanitized, and manually reviewed.

## Install

Clone the repo, then run the CLI directly from the checkout:

```bash
git clone https://github.com/BlockhouseSoftware/ai-shield.git
cd ai-shield
python3 -m aishield scan ./tests/fixtures/clean-project
```

For local development, install it in editable mode inside a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
aishield scan ./tests/fixtures/clean-project
```

### Distribution

AI Shield v0.1.0 is distributed as source through this repository and its GitHub Releases page. No AI Shield package has been published to PyPI yet. Until an official release links to a verified PyPI project, do not install similarly named packages from PyPI or with `pipx`.

For a reproducible source checkout after the first release is published:

```bash
git checkout v0.1.0
```

## Run locally

```bash
python3 -m aishield scan ./some-project          # terminal summary, top 5 findings
python3 -m aishield scan ./some-project --all    # terminal summary, all findings
python3 -m aishield scan ./some-project --json   # full machine-readable report
python3 -m aishield scan ./some-project --html report.html
python3 -m aishield scan . --profile release     # shipped-source view; excludes tests/examples/reference artifacts
```

Exit codes are stable for scripts and demos:

- `0` — `NO CRITICAL RISKS FOUND`
- `1` — `CAUTION`
- `2` — `DO NOT RUN`

Bad demo fixtures are expected to exit `2`; do not continue with install/run/deploy commands until findings are reviewed.

### Release-profile self-scan

Use `--profile release` when scanning a development checkout as the artifact you intend to ship. It deliberately excludes development-only `tests/`, `reference/`, `docs/`, and example directories, while retaining package metadata, shipped source, agent instructions, and CI/deployment files. This avoids treating intentionally unsafe fixtures and rendered scan reports as runtime application code.

It is not a blanket suppression mechanism: a committed `.env`, dangerous package lifecycle hook, or other supported risk in the shipped source still produces a finding. Before cutting a release, run both the unit suite and release-profile scan:

```bash
python3 -m unittest discover -s tests -v
python3 -m aishield scan . --profile release --json
```

## Demo fixtures

Use the included fixtures to see the alpha behavior without scanning an unrelated project:

```bash
python3 -m aishield scan tests/fixtures/bad-node-app
python3 -m aishield scan tests/fixtures/poisoned-agent-file
python3 -m aishield scan tests/fixtures/risky-mcp-server
python3 -m aishield scan tests/fixtures/unsafe-docker-config
python3 -m aishield scan tests/fixtures/clean-project
```

The intentionally bad fixtures should produce `Verdict: DO NOT RUN` and exit `2`. That is expected: they demonstrate catches such as remote package install scripts, committed env files, client-exposed key names, poisoned agent instructions, risky MCP access, and unsafe Docker settings.

The `clean-project` fixture is only "clean-ish": it should produce `NO CRITICAL RISKS FOUND` for the deterministic v0.1 rules, not a guarantee that the project is safe.

## Current deterministic checks

- Dangerous package lifecycle scripts (`postinstall`, `preinstall`, `curl | bash`, remote script execution)
- Suspicious package script access to home/credential paths
- Committed `.env` files and client-exposed key patterns (`VITE_*KEY`, `NEXT_PUBLIC_*SECRET`, etc.)
- Docker host escape/overexposure risks (`privileged: true`, Docker socket mounts, home-directory mounts, exposed admin/database ports)
- Agent instruction risks in `AGENTS.md`, `CLAUDE.md`, Cursor/Windsurf rules, and prompt-like markdown files
- MCP/tool risk patterns: filesystem/shell/environment access, credential paths, undeclared outbound endpoints
- Node route heuristics for unauthenticated destructive endpoints and dangerous shell/eval/file operations

## Limitations

AI Shield v0.1 is an alpha deterministic scanner:

- It does not prove a project is safe, complete a full security audit, or replace human review.
- Rules are intentionally incomplete and may miss logic bugs, auth design flaws, dependency vulnerabilities, obfuscated payloads, generated code, or runtime-only behavior.
- It is strongest today on Node/TypeScript apps, package scripts, MCP/tooling code, Docker/self-hosted config, and agent instruction files.
- Findings are evidence-first heuristics. Treat `DO NOT RUN` as a stop-and-review signal, not as an automated fix plan.

## Test

```bash
python3 -m unittest discover -s tests -v
```

## License

Copyright © 2026 Blockhouse Software.

AI Shield is licensed under the [GNU Affero General Public License version 3](LICENSE) only (`AGPL-3.0-only`).
