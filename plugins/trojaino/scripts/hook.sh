#!/bin/sh
# Explicit trusted interpreter only. Never evaluate candidate shell strings.
deny() {
  printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Trojaino hook unavailable: configure an absolute trusted TROJAINO_PYTHON (3.11+) and keep the plugin in its trusted checkout."}}'
}
case "${TROJAINO_PYTHON:-}" in
  /*) ;;
  *) deny; exit 0 ;;
esac
if [ ! -x "$TROJAINO_PYTHON" ]; then
  deny
  exit 0
fi
if output=$("$TROJAINO_PYTHON" -I -S "${CLAUDE_PLUGIN_ROOT}/scripts/preflight.py" hook); then
  printf '%s\n' "$output"
else
  deny
fi
