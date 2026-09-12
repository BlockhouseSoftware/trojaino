"""Test-only observation must retain the original CLI denial, never replay."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from trojaino import preflight


@unittest.skipUnless(os.name == "posix", "observer targets POSIX launch CI")
class NodeProbeObserverTests(unittest.TestCase):
    def test_original_nonzero_probe_is_observed_without_launch_or_replay(self):
        self.check_original_probe("exit 9", "CalledProcessError", 9)

    def test_original_timeout_is_observed_without_extending_deadline(self):
        self.check_original_probe("exec /bin/sleep 10", "TimeoutExpired", None)

    def test_observation_write_failure_does_not_change_cli_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "source"
            source.mkdir()
            (source / "server.js").write_text('console.log("fixture");')
            from preflight_test_support import sealed_gate
            receipt = sealed_gate(source, root / "state")
            self.assertEqual(receipt["decision"], "permit", receipt)
            node = root / "node"
            node.write_text("#!/bin/sh\nexit 0\n")
            node.chmod(0o700)
            result = subprocess.run(
                [sys.executable, "-I", "-S", str(Path(__file__).with_name("node_probe_observer.py")),
                 str(root), "launch", receipt["report_path"], "--entry", "server.js"],
                env=dict(os.environ, TROJAINO_NODE=str(node)),
                capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stderr)["decision"], "permit")
            self.assertEqual(result.stdout, "")

    def check_original_probe(self, command, exception, returncode):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "source"
            source.mkdir()
            (source / "server.js").write_text('console.log("TARGET_EXECUTED");')
            from preflight_test_support import sealed_gate
            receipt = sealed_gate(source, root / "state")
            self.assertEqual(receipt["decision"], "permit", receipt)
            count = root / "calls"
            node = root / "node"
            node.write_text(f"#!/bin/sh\nprintf x >> '{count}'\n{command}\n")
            node.chmod(0o700)
            observation = root / "probe.json"
            helper = Path(__file__).with_name("node_probe_observer.py")
            result = subprocess.run(
                [sys.executable, "-I", "-S", str(helper), str(observation),
                 "launch", receipt["report_path"], "--entry", "server.js"],
                env=dict(os.environ, TROJAINO_NODE=str(node), NODE_OPTIONS="--invalid"),
                capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertTrue(observation.is_file(), "original probe observation missing")
            self.assertEqual(json.loads(result.stderr), {
                "decision": "deny", "reason": "node_permission_runtime_required"})
            record = json.loads(observation.read_text())
            self.assertEqual(record["exception"], exception)
            self.assertEqual(record["returncode"], returncode)
            self.assertIsNone(record["errno"])
            self.assertEqual(record["timeout"], 3)
            self.assertEqual(record["cwd"], "/")
            self.assertEqual(record["env_keys"], ["LANG", "PATH"])
            self.assertTrue(record["check"])
            self.assertEqual(record["stdio"], [subprocess.DEVNULL] * 3)
            self.assertIn("--eval", record["argv"])
            self.assertNotIn("server.js", str(record["argv"]))
            self.assertGreaterEqual(record["elapsed_seconds"], 0)
            self.assertEqual(count.read_text(), "x", "probe must run exactly once")


if __name__ == "__main__":
    unittest.main()
