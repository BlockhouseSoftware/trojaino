#!/bin/sh
# This file is read by sh, so neither executable bits nor Python are required.
# Hook input stays on stdin; probes must never consume it or evaluate its text.
script_dir=${0%/*}
if [ "${OS-}" = Windows_NT ]; then
    exec powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$script_dir/launch.ps1" "$@"
fi
mode=${1-}
case "$mode" in
    session-start|pre-tool-use) operation=hook ;;
    doctor) operation=doctor ;;
    *) printf '%s\n' 'Usage: launch.sh session-start|pre-tool-use|doctor' >&2; exit 1 ;;
esac
problem='Python was not found on PATH.'
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        "$candidate" -I -S -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 3)' </dev/null >/dev/null 2>&1
        result=$?
        if [ "$result" -eq 0 ]; then
            exec "$candidate" -I -S -X utf8 "$script_dir/preflight.py" "$operation"
        elif [ "$result" -eq 3 ]; then
            problem='The available Python is older than 3.11.'
        elif [ "$problem" = 'Python was not found on PATH.' ]; then
            problem='Python was found but could not run in isolated mode.'
        fi
    fi
done
message="Trojaino cannot start: $problem Python 3.11 or newer is required. Trojaino is not checking installations. Install Python using https://github.com/BlockhouseSoftware/trojaino/blob/main/docs/plugin-installation.md, restart Claude Code, then run /trojaino:doctor."
# All message fragments are constants, not event data or command output.
case "$mode" in
    doctor)
        printf '{"status":"Needs attention","actions":["%s"]}\n' "$message"
        exit 1 ;;
    session-start) event=SessionStart ;;
    pre-tool-use) event=PreToolUse ;;
esac
# Valid hook JSON makes the warning visible without claiming a scan or changing
# Claude's normal permissions. A hook process error alone can be easy to miss.
printf '{"systemMessage":"%s","hookSpecificOutput":{"hookEventName":"%s","additionalContext":"%s"}}\n' "$message" "$event" "$message"
