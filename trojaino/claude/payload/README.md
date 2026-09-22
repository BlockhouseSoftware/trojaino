# Trojaino for Claude Code — install gate 0.3.1

Trojaino checks software **before Claude installs it**. When Claude runs an install command, Trojaino fetches that exact package, scans it without running any of it, and then:

| Result | What happens |
| --- | --- |
| **NO CRITICAL RISKS FOUND** | Supported npm installs continue pinned to the scanned version; supported Python requirement forms use the scanned file URL and SHA-256. Commands that cannot be bound require approval. Your normal Claude Code permission settings still apply. |
| **CAUTION** | Claude asks you, and shows the findings. You decide. |
| **DO NOT RUN** | The install is blocked. |
| Could not be scanned | Claude asks you, and says why Trojaino could not check it. |

Everything else Claude does (building, testing, editing, running your code) is untouched. Trojaino is an install gate, not a general command filter.

## Install

You need **Python 3.11 or newer**, available as `python3`, and Claude Code **2.1.274 or newer**. Then, inside Claude Code:

```
/plugin marketplace add BlockhouseSoftware/claude-marketplace
/plugin install trojaino@blockhouse-software
```

Restart Claude Code and run **`/trojaino:doctor`**. Continue when it says **Ready**; otherwise follow its recovery action. `/hooks` only proves registration, not successful execution. See [installation and migration](https://github.com/BlockhouseSoftware/trojaino/blob/main/docs/plugin-installation.md) for macOS/Linux prerequisites and older prepared plugins.

On Windows, install Python with the **Python Install Manager** (from the Microsoft Store, or `winget install 9NQ7512CXL7T`), which provides the `python3` command. Step-by-step instructions for someone who has never used a terminal are in the [Windows quick start](https://github.com/BlockhouseSoftware/trojaino/blob/main/docs/windows-quick-start.md).

To update: `/plugin marketplace update blockhouse-software`, then `/plugin update trojaino@blockhouse-software`. Restart Claude and run `/trojaino:doctor`. To remove: `/plugin uninstall trojaino@blockhouse-software`.

## What it checks

| Install command | What Trojaino scans |
| --- | --- |
| `npx`, `npm install`, `pnpm add`, `pnpm dlx`, `yarn add`, `yarn dlx`, `bun add`, `bunx` | The npm package, from registry.npmjs.org, checked against its sha512 |
| `pip install`, `python -m pip install`, `uv add`, `uv pip install`, `uvx`, `uv tool install`, `pipx` | The PyPI package, from pypi.org, checked against its sha256 |
| `git clone`, `gh repo clone`, npm or pip installs from GitHub | The repository at one exact commit |
| `claude mcp add ... -- npx ...` or `-- uvx ...` | The package that runs the MCP server |
| `claude plugin install`, `claude plugin marketplace add` | The plugin or marketplace source |

A scan is followed by approval when the command cannot be bound to what was scanned: Git clones, mutable plugin/local sources, nested shell commands, `uvx PACKAGE` and `pipx run PACKAGE`. Use a supported explicit requirement form such as `uvx --from PACKAGE COMMAND` for Python artifact binding. Source-selection flags, environment overrides and detected source-changing package-manager configuration also require approval.

Asked about, never auto-allowed: `winget`, `choco`, `scoop`, `brew`, `apt`, `cargo install`, `go install`, `gem install`, `docker pull`, installers (`.exe`, `.msi`), `curl … | sh`, `irm … | iex`, private registries and custom indexes, remote (HTTP) MCP servers, packages containing compiled code, packages too large to scan, and edits to `.mcp.json` or Claude's plugin and MCP settings.

Passed through untouched: installing what your project already declares (`npm install` with no package named, `pip install -r requirements.txt`, `pip install -e .`).

## Scan without installing

Ask Claude to use `/trojaino:scan`, for example:

```
/trojaino:scan npm:@modelcontextprotocol/server-filesystem
/trojaino:scan pypi:mcp-server-fetch
/trojaino:scan https://github.com/OWNER/REPO
```

## Limits — read these

- **Only the named package is scanned, not its dependencies.** A clean result says nothing about what that package pulls in.
- **A clean result is not a safety guarantee.** Trojaino is a deterministic, rule-based static scanner. It is not antivirus and not a sandbox.
- **It gates what Claude does.** Installs you type yourself in a terminal, or with `/plugin install` in Claude's own interface, are not tool calls and are not checked.
- **It recognises the usual ways of installing.** A disguised install (an encoded command, a script that installs something) is not recognised. Trojaino is a gate on the front door, not a firewall.
- **If Python is missing, the gate is not running.** Claude will show a hook error. Nothing is blocked, and nothing is checked.
- **Network.** Trojaino contacts registry.npmjs.org, pypi.org, files.pythonhosted.org, github.com and codeload.github.com, and only while an install is being checked. It sends nothing about you or your project. `tjscan check-updates` is the only other network use, and only when you run it.
- **Reports** are kept in `~/.local/state/trojaino/reports` (Windows: `%LOCALAPPDATA%\trojaino\reports`). Clean and CAUTION verdicts are remembered per exact package version, so the same version is not fetched twice.

License: AGPL-3.0-only, as in the repository root LICENSE.
