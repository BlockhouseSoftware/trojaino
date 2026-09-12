"""MKT-001A containment checks; these inspect package files only."""
import ast
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "plugins" / "trojaino"
RUNTIME_ROOT = PLUGIN_ROOT / "runtime"
WRAPPER = PLUGIN_ROOT / "scripts" / "preflight.py"


class MarketplacePackageContainmentTests(unittest.TestCase):
    def test_preflight_runtime_is_embedded_in_entry(self):
        self.assertTrue("'trojaino.preflight':" in WRAPPER.read_text())
        self.assertFalse(RUNTIME_ROOT.exists())

    def test_no_package_path_is_a_symlink_outside_plugin_root(self):
        plugin = PLUGIN_ROOT.resolve()
        for path in PLUGIN_ROOT.rglob("*"):
            if path.is_symlink():
                self.assertTrue(path.resolve().is_relative_to(plugin), str(path))

    def test_symlinked_entry_wrapper_is_denied_before_runtime_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            copied = Path(tmp) / "trojaino"
            shutil.copytree(PLUGIN_ROOT, copied, symlinks=True)
            wrapper = copied / "scripts/preflight.py"
            wrapper.unlink()
            wrapper.symlink_to(WRAPPER)
            result = subprocess.run(
                [sys.executable, "-I", "-S", str(wrapper), "--help"],
                capture_output=True, text=True, check=False,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("plugin_entry_invalid", result.stdout)

    def test_wrapper_uses_sealed_image_without_runtime_path_loader(self):
        source = WRAPPER.read_text(encoding="utf-8")
        self.assertTrue("sys.flags.isolated" in source)
        self.assertTrue("sys.flags.no_site" in source)
        self.assertFalse("RUNTIME_PACKAGE.rglob" in source)
        self.assertTrue("_CAPSULE" in source)

    def test_wrapper_has_no_repository_parent_escape(self):
        tree = ast.parse(WRAPPER.read_text(encoding="utf-8"), filename=str(WRAPPER))
        forbidden = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "parents":
                forbidden.append(node.lineno)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in {"insert", "append"} and isinstance(node.func.value, ast.Attribute):
                    if node.func.value.attr == "path" and isinstance(node.func.value.value, ast.Name) and node.func.value.value.id == "sys":
                        forbidden.append(node.lineno)
        self.assertEqual(forbidden, [], f"unsafe wrapper path manipulation at lines {forbidden}")


if __name__ == "__main__":
    unittest.main()
