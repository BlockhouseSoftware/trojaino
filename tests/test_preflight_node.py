"""PREFLIGHT-001: ambient modules must never execute outside the scan."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from trojaino import preflight


@unittest.skipUnless(os.name == 'posix', 'preflight pilot requires POSIX')
class NodeLaunchTests(unittest.TestCase):
    def setUp(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node runtime unavailable")
        self.node = str(Path(node).resolve())
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.source = self.root / "candidate"
        self.source.mkdir()
        self.env = patch.dict(os.environ, TROJAINO_NODE=self.node)
        self.env.start()
        self.addCleanup(self.env.stop)

    def plan(self, entry, code):
        (self.source / entry).write_text(code)
        receipt = preflight.gate(str(self.source), self.root / "state")
        self.assertEqual(receipt["decision"], "permit", receipt)
        result, argv = preflight.launch_plan(receipt["report_path"], entry)
        self.assertEqual(result["decision"], "permit", result)
        return result, argv

    def run_plan(self, result, argv):
        return subprocess.run(argv, cwd=result["staged_path"],
                              env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
                              capture_output=True, text=True, timeout=10)

    def test_scanned_siblings_and_builtins_work_with_symlinked_state_parent(self):
        # macOS /var -> /private/var and user-selected state aliases must work.
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        (self.source / "helper.cjs").write_text("module.exports = 42;")
        (self.source / "server.js").write_text("console.log(require('node:path').basename(__filename), require('./helper.cjs'));")
        receipt = preflight.gate(str(self.source), alias / "state")
        self.assertEqual(receipt["decision"], "permit", receipt)
        result, argv = preflight.launch_plan(receipt["report_path"], "server.js")
        self.assertEqual(result["decision"], "permit", result)
        process = self.run_plan(result, argv)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stdout, "server.js 42\n")

    def test_runtime_without_permission_capability_is_denied_before_launch(self):
        # Harmless stand-in for an older trusted Node rejecting unknown flags.
        runtime = self.root / "node"
        runtime.write_text("#!/bin/sh\nexit 9\n")
        runtime.chmod(0o700)
        (self.source / "server.js").write_text('console.log("TARGET_EXECUTED");')
        receipt = preflight.gate(str(self.source), self.root / "state")
        self.assertEqual(receipt["decision"], "permit", receipt)
        with patch.dict(os.environ, TROJAINO_NODE=str(runtime)):
            result, argv = preflight.launch_plan(receipt["report_path"], "server.js")
        self.assertEqual(result["decision"], "deny")
        self.assertEqual(result["reason"], "node_permission_runtime_required")
        self.assertEqual(argv, [])

    def test_permission_grant_cannot_interpret_state_path_as_wildcard(self):
        (self.source / "server.js").write_text("console.log(42);")
        receipt = preflight.gate(str(self.source), self.root / "state*wildcard")
        self.assertEqual(receipt["decision"], "permit", receipt)
        result, argv = preflight.launch_plan(receipt["report_path"], "server.js")
        self.assertEqual(result["decision"], "deny")
        self.assertEqual(result["reason"], "unsupported_node_stage_path")
        self.assertEqual(argv, [])

    def test_scanned_commonjs_and_esm_siblings_and_builtins(self):
        (self.source / "helper.cjs").write_text("module.exports = 42;")
        (self.source / "helper.mjs").write_text("export default 42;")
        cases = {
            "server.js": "console.log(require('node:path').basename(__filename), require('./helper.cjs'));",
            "server.cjs": "console.log(require('node:path').basename(__filename), require('./helper.cjs'));",
            "server.mjs": "import path from 'node:path'; import answer from './helper.mjs'; console.log(path.basename(import.meta.filename), answer);",
        }
        for entry, code in cases.items():
            with self.subTest(entry=entry):
                result, argv = self.plan(entry, code)
                process = self.run_plan(result, argv)
                self.assertEqual(process.returncode, 0, process.stderr)
                self.assertEqual(process.stdout, entry + " 42\n")
                (self.source / entry).unlink()

    def test_ancestor_package_metadata_never_redirects_to_external_code(self):
        (self.root / "package.json").write_text(
            '{"type":"module","imports":{"#ambient":"./outside.mjs"}}')
        (self.root / "outside.mjs").write_text('console.log("EXTERNAL_METADATA_EXECUTED");')
        result, argv = self.plan("server.mjs", "import '#ambient';")
        process = self.run_plan(result, argv)
        self.assertNotEqual(process.returncode, 0)
        self.assertNotIn("EXTERNAL_METADATA_EXECUTED", process.stdout)
        self.assertIn("ERR_ACCESS_DENIED", process.stderr)

    def test_probe_failures_are_closed_and_never_receive_candidate_code(self):
        (self.source / "server.js").write_text('console.log("TARGET_EXECUTED");')
        receipt = preflight.gate(str(self.source), self.root / "state")
        real_run = subprocess.run
        for fault in (OSError("probe unavailable"), subprocess.TimeoutExpired("node", 3)):
            with self.subTest(fault=type(fault).__name__):
                def fail_probe(argv, **kwargs):
                    if argv[0] == self.node:
                        self.assertNotIn(receipt["staged_path"], str(argv))
                        self.assertNotIn("TARGET_EXECUTED", str(argv))
                        self.assertEqual(kwargs["cwd"], "/")
                        self.assertNotIn("NODE_OPTIONS", kwargs["env"])
                        raise fault
                    return real_run(argv, **kwargs)
                with patch.object(preflight.subprocess, "run", side_effect=fail_probe):
                    result, argv = preflight.launch_plan(receipt["report_path"], "server.js")
                self.assertEqual(result["reason"], "node_permission_runtime_required")
                self.assertEqual(result["decision"], "deny")
                self.assertEqual(argv, [])

    def test_scan_and_hook_never_execute_node_candidate_or_environment_preloads(self):
        import shlex
        import sys
        cli = Path(preflight.__file__).resolve().parents[1] / "plugins/trojaino/scripts/preflight.py"
        marker = self.root / "PRELOAD_EXECUTED"
        preload = self.root / "preload.cjs"
        preload.write_text(f"require('node:fs').writeFileSync({str(marker)!r}, 'bad');")
        (self.source / "server.js").write_text('console.log("TARGET_EXECUTED");')
        calls = []
        real_run = subprocess.run
        def observe(argv, **kwargs):
            if argv[0] == self.node:
                calls.append((argv, kwargs))
            return real_run(argv, **kwargs)
        with patch.dict(os.environ, NODE_OPTIONS="--require " + str(preload)), \
                patch.object(preflight.subprocess, "run", side_effect=observe):
            receipt = preflight.gate(str(self.source), self.root / "state")
            self.assertEqual(receipt["decision"], "permit", receipt)
            self.assertEqual(calls, [])
            event = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {
                "command": shlex.join([sys.executable, "-I", "-S", str(cli), "launch",
                                       receipt["report_path"], "--entry", "server.js"])}}
            result = preflight.hook(event)
        self.assertNotIn("permissionDecision", result["hookSpecificOutput"])
        self.assertEqual(len(calls), 1)
        argv, kwargs = calls[0]
        self.assertIn("--eval", argv)
        self.assertNotIn("TARGET_EXECUTED", str(argv))
        self.assertNotIn("server.js", str(argv))
        self.assertNotIn("NODE_OPTIONS", kwargs["env"])
        self.assertFalse(marker.exists())

    def test_ancestor_commonjs_package_cannot_execute(self):
        package = self.root / "node_modules/review-ambient-helper"
        package.mkdir(parents=True)
        marker = "UNSCANNED_AMBIENT_MODULE_EXECUTED"
        (package / "index.js").write_text(f'console.log("{marker}"); module.exports = 42;')
        cases = {
            "server.js": "console.log(require('review-ambient-helper'));",
            "server.cjs": "console.log(require('review-ambient-helper'));",
            "server.mjs": "import 'review-ambient-helper';",
            "dynamic.cjs": "import('review-ambient-helper');",
        }
        for entry, code in cases.items():
            with self.subTest(entry=entry):
                result, argv = self.plan(entry, code)
                self.assertNotIn("node_modules", str(preflight.snapshot(Path(result["staged_path"]))))
                process = self.run_plan(result, argv)
                self.assertNotIn(marker, process.stdout)
                self.assertNotEqual(process.returncode, 0)
                self.assertIn("ERR_ACCESS_DENIED", process.stderr)
                (self.source / entry).unlink()


if __name__ == "__main__":
    unittest.main()
