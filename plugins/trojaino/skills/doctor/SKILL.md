---
name: doctor
description: Check whether Trojaino is installed, enabled and able to execute its protection hooks. Use after installing, updating or migrating Trojaino, or when a hook fails.
disable-model-invocation: true
---

Run this exact offline readiness check:

```sh
python3 -I -S "${CLAUDE_PLUGIN_ROOT}/scripts/preflight.py" doctor
```

Report its `status`, then any `actions`. A registered hook or an enabled plugin alone is not proof of readiness. Do not say Ready unless the command returned Ready. The check scans a harmless synthetic fixture as data, never executes its script, never installs software, and makes no registry request.

If Python cannot start, say **Needs attention: Python is unavailable**. Link to https://github.com/BlockhouseSoftware/trojaino/blob/main/docs/plugin-installation.md for the OS-specific Python setup, then ask the user to restart Claude Code and repeat this check. Do not install a runtime or change settings automatically.

If legacy hooks or another Trojaino plugin are reported, explain the named migration action. Never delete unrelated hooks or settings. After migration, restart Claude and run this check again.
