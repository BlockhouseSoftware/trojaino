# Trojaino v0.1.3

Trojaino is a local deterministic install gate for AI tools and downloaded software. The first version focuses on Node/TypeScript and Python projects, MCP/tooling repos, Docker configs, and agent instruction files.

## Requirements

The CLI requires Python 3.11 or newer and has no runtime third-party Python
dependencies. The optional desktop GUI uses the same scanner and additionally
requires Tkinter plus a graphical desktop session. If you only use the CLI,
Tkinter is not required.

It is intentionally not a generic "ask an LLM to review this repo" wrapper. v0.1 runs repeatable rule packs and produces evidence-first findings with a conservative verdict:

- `DO NOT RUN`
- `CAUTION`
- `NO CRITICAL RISKS FOUND`

It never says software is "safe" or "certified secure."

## Repository scope

This repository contains only the product source, public documentation, tests, and synthetic fixtures needed to verify detections. Company strategy, private requirements, decks, raw scan reports, screenshots, and generated evidence live outside this repository.

Generated reports should be written to a local-only workspace. A report belongs in this repository only when it is deliberately selected as a public example, sanitized, and manually reviewed.

## Install and run

Trojaino is currently distributed as source, not through PyPI. For normal use,
clone the verified repository and run it directly — no installation is required:

```bash
python3 --version
git clone https://github.com/BlockhouseSoftware/trojaino.git
cd trojaino
python3 -m trojaino gui
```

To run a scan from the terminal without installing anything:

```bash
python3 -m trojaino scan ./tests/fixtures/clean-project
```

If you prefer the shorter `trojaino` command, install it in an isolated virtual
environment. This is optional; it is not required to use the desktop window.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip setuptools
python3 -m pip install -e .
trojaino gui
```

### Distribution

Trojaino v0.1.3 is distributed as source through this repository and its GitHub Releases page. No Trojaino package has been published to PyPI yet. Until an official release links to a verified PyPI project, do not install similarly named packages from PyPI or with `pipx`.

For a reproducible source checkout after the first release is published:

```bash
git checkout v0.1.3
```

## Run locally

### Desktop scan window

For a file-picker-based local scan from a source checkout, run:

```bash
python3 -m trojaino gui
```

If you completed the optional virtual-environment installation above, the
equivalent shorter command is `trojaino gui`.

The optional desktop window uses the same local scanner, bounded resource presets, and report renderers as the CLI. Choose a project or file, select Standard, Large, or Exhaustive, then choose HTML, JSON, or both report formats. It proposes a visible `TrojainoReports/` folder beside the selected artifact, but outside a containing Git repository; you can choose any other report folder before scanning. It does not upload or execute the selected code.

The GUI requires a graphical desktop session and a Python installation with Tkinter. On a server, SSH session, or minimal Python installation without Tk support, use the CLI commands below instead.

Trojaino scans local files and folders. To scan a Git repository, clone it first, then select or pass the local checkout. Remote-URL cloning is not implemented in this alpha.

### Optional anonymous scan statistics

Trojaino never uploads code, reports, paths, filenames, line numbers, evidence, credentials, or the selected target. After a desktop scan, **Share anonymous statistics…** shows the exact aggregate JSON before anything can leave the device. Sharing is optional and off by default.

The CLI has the same explicit preview-first flow. It reads a local Trojaino JSON report only to create a new allowlisted summary; it never uploads that report file.

```bash
# Prints the complete anonymous payload and sends nothing.
trojaino share ./TrojainoReports/project-20260812-221530.json

# Sends only after the user has reviewed the preview and explicitly opts in.
trojaino share ./TrojainoReports/project-20260812-221530.json --send

# Deletes a prior submission. Both values are displayed only after sending.
trojaino unshare <receipt> <deletion-token>
```

The contribution service is hosted separately from this local scanner repository. It accepts only this allowlisted aggregate schema and labels each row anonymous and unverified. It does not accept report files or arbitrary user content. Trojaino shows a one-time receipt and deletion token after a submission; save both together to delete the contribution using `trojaino unshare`. The hosted service uses `https://trojaino.llamaheads.com/v1/scan-statistics` only; Trojaino will not send data to a user-supplied destination.

### Anonymous statistics privacy notice

Sharing is optional and disabled unless you explicitly choose **Send anonymous statistics** in the desktop window or add `--send` to `trojaino share`. Before either action, Trojaino displays the complete JSON payload.

The service receives only scanner version, profile, verdict, completion status, a coarse scan-size band, and counts grouped by supported detection rule/category and coverage-issue IDs. It does not receive source code, HTML or JSON reports, paths, filenames, line numbers, evidence, credentials, the selected target, hashes, contact details, archives, or arbitrary metadata.

Contributions are anonymous and unverified: they may be incorrect or fabricated and are not treated as authoritative research. The service retains them for at most 90 days, then deletes them automatically. You can delete a contribution earlier using the receipt and one-time deletion token returned after you submit it. Keep those values private; without both, the service cannot identify or remove an anonymous row.

```bash
trojaino scan ./some-project          # terminal summary, top 5 findings
trojaino scan ./some-project --all    # terminal summary, all findings
trojaino scan ./some-project --json   # full machine-readable report
trojaino scan ./some-project --html report.html
trojaino scan . --profile release     # shipped-source view; excludes tests/examples/reference artifacts
```

Every CLI scan first performs a bounded, metadata-only preflight estimate. In an interactive terminal, Trojaino offers to keep the selected hard limits, raise them once to fit the estimate, choose a larger preset, or cancel before reading project files. JSON, CI, and other non-interactive runs never prompt; incomplete scans fail closed, and budget-limited results include a suggested higher-budget command when another supported ceiling is available.

```bash
trojaino scan ./large-project --budget large
trojaino scan ./large-project --budget exhaustive
trojaino scan ./large-project --max-total-mb 150 --max-seconds 180
```

`standard`, `large`, and `exhaustive` are finite presets, not unlimited modes. File, entry, byte, finding, canonical JSON report-data, depth, and elapsed-time ceilings remain enforced during the actual scan even when preflight predicts the project will fit. Use `--no-prompt` to retain preflight metadata while suppressing interactive questions.

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
trojaino scan . --profile release --json
```

## Demo fixtures

Use the included fixtures to see the alpha behavior without scanning an unrelated project:

```bash
trojaino scan tests/fixtures/bad-node-app
trojaino scan tests/fixtures/poisoned-agent-file
trojaino scan tests/fixtures/risky-mcp-server
trojaino scan tests/fixtures/unsafe-docker-config
trojaino scan tests/fixtures/clean-project
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
- Python app heuristics for dangerous execution, unsafe deserialization, debug/CORS exposure, destructive routes, and user-input-to-sensitive-sink review signals

## Limitations

Trojaino v0.1 is an alpha deterministic scanner:

- It does not prove a project is safe, complete a full security audit, or replace human review.
- Rules are intentionally incomplete and may miss logic bugs, auth design flaws, dependency vulnerabilities, obfuscated payloads, generated code, or runtime-only behavior.
- It is strongest today on Node/TypeScript and Python apps, package scripts, MCP/tooling code, Docker/self-hosted config, and agent instruction files.
- Python support is heuristic and stdlib-only. It catches common AI-generated Flask/FastAPI/script risks, but it is not comprehensive Python SAST.
- Findings are evidence-first heuristics. Treat `DO NOT RUN` as a stop-and-review signal, not as an automated fix plan.

## Test

```bash
python3 -m unittest discover -s tests -v
```

## License

Copyright © 2026 Blockhouse Software.

Trojaino is licensed under the [GNU Affero General Public License version 3](LICENSE) only (`AGPL-3.0-only`).
