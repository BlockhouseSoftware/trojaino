"""Marketplace contract tests for MKT-001."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / ".claude-plugin" / "marketplace.json"
PLUGIN_PATH = ROOT / "plugins" / "trojaino"
MANIFEST_PATH = PLUGIN_PATH / ".claude-plugin" / "plugin.json"
RESERVED_MARKETPLACE_NAMES = {
    "claude-code-marketplace", "claude-code-plugins",
    "claude-plugins-official", "claude-plugins-community",
    "claude-community", "anthropic-marketplace", "anthropic-plugins",
    "agent-skills", "anthropic-agent-skills", "knowledge-work-plugins",
    "life-sciences", "claude-for-legal", "claude-for-financial-services",
    "financial-services-plugins", "first-party-plugins", "claude-tag-plugins",
    "healthcare",
}
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")


class MarketplaceContractTests(unittest.TestCase):
    def load_catalog(self):
        self.assertTrue(CATALOG_PATH.is_file(), "MKT-001 requires a root marketplace catalog")
        return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

    def test_catalog_identifies_non_reserved_blockhouse_marketplace(self):
        catalog = self.load_catalog()
        self.assertRegex(catalog["name"], r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
        self.assertNotIn(catalog["name"], RESERVED_MARKETPLACE_NAMES)
        self.assertEqual(catalog["owner"]["name"], "Blockhouse Software")

    def test_catalog_uses_only_contained_trojaino_source(self):
        catalog = self.load_catalog()
        entries = [entry for entry in catalog["plugins"] if entry.get("name") == "trojaino"]
        self.assertEqual(len(entries), 1)
        source = entries[0]["source"]
        self.assertEqual(source, "./plugins/trojaino")
        self.assertFalse(Path(source).is_absolute())
        self.assertNotIn("..", Path(source).parts)
        self.assertEqual((ROOT / source).resolve(), PLUGIN_PATH.resolve())
        self.assertTrue(PLUGIN_PATH.resolve().is_relative_to(ROOT.resolve()))

    def test_catalog_entry_is_disabled_and_matches_manifest_metadata(self):
        catalog = self.load_catalog()
        entry = next(item for item in catalog["plugins"] if item["name"] == "trojaino")
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertFalse(entry.get("defaultEnabled", True))
        self.assertRegex(entry["version"], SEMVER)
        self.assertEqual(entry["version"], manifest["version"])
        for field in ("displayName", "description", "homepage", "repository", "license", "tags"):
            self.assertTrue(entry.get(field), f"catalog entry missing {field}")
        for field in ("displayName", "description", "homepage", "repository", "license"):
            self.assertTrue(manifest.get(field), f"plugin manifest missing {field}")
            self.assertEqual(entry[field], manifest[field], f"catalog and manifest disagree on {field}")
        self.assertEqual(manifest["author"]["name"], "Blockhouse Software")
        self.assertTrue(manifest.get("keywords") or manifest.get("tags"))

    def test_unprepared_plugin_has_no_executable_hooks(self):
        hooks = json.loads((PLUGIN_PATH / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(hooks, {"hooks": {}})

    def test_plugin_has_no_auto_dependency_install_surface(self):
        self.assertFalse((PLUGIN_PATH / "bin").exists())
        for filename in ("package.json", "bun.lock", "bun.lockb", "npm-shrinkwrap.json", "package-lock.json"):
            self.assertFalse((PLUGIN_PATH / filename).exists(), filename)


if __name__ == "__main__":
    unittest.main()
