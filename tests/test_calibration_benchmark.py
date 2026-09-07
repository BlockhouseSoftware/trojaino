from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "run_calibration_benchmark.py"
SPEC = importlib.util.spec_from_file_location("run_calibration_benchmark", SCRIPT)
assert SPEC and SPEC.loader
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


class CalibrationBenchmarkTests(unittest.TestCase):
    def test_manifest_runs_all_synthetic_cases_and_writes_examples(self):
        output = Path(tempfile.mkdtemp(prefix="trojaino-calibration-"))
        aggregate = benchmark.run(benchmark.DEFAULT_MANIFEST, output)

        self.assertEqual(aggregate["case_count"], 20)
        self.assertEqual(aggregate["cases_by_label"], {"benign": 6, "review": 2, "unsafe": 12})
        self.assertTrue((output / "summary.json").is_file())
        self.assertTrue((output / "clean-example.json").is_file())
        self.assertTrue((output / "clean-example.html").is_file())
        self.assertTrue((output / "finding-heavy-example.json").is_file())
        self.assertTrue((output / "finding-heavy-example.html").is_file())

        summary = json.loads((output / "summary.json").read_text())
        self.assertEqual(summary["case_count"], 20)
        self.assertIn("NO CRITICAL RISKS FOUND", summary["cases_by_verdict"])
        self.assertIn("DO NOT RUN", summary["cases_by_verdict"])


if __name__ == "__main__":
    unittest.main()
