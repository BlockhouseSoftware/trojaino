"""Fetch exactly what an install would fetch, verify it, and unpack it safely."""
import unittest
from unittest import mock

from tests.gate_fixtures import FakeRegistry, tgz, wheel
from trojaino import registry
from trojaino.registry import Refused, Unscannable


class VersionRangeTests(unittest.TestCase):
    def test_npm_ranges(self):
        cases = [("1.2.3", "^1.0.0", True), ("2.0.0", "^1.0.0", False), ("0.2.5", "^0.2.1", True),
                 ("0.3.0", "^0.2.1", False), ("1.2.9", "~1.2.3", True), ("1.3.0", "~1.2.3", False),
                 ("1.5.0", "1.x", True), ("2.0.0", "1.x", False), ("3.1.0", ">=2 <4", True),
                 ("4.0.0", ">=2 <4", False), ("1.0.0", "1.0.0 - 1.2.0", True), ("5.0.0", "^1 || ^5", True),
                 ("2.0.0-beta.1", "^2.0.0-0", False), ("1.0.0", "*", True)]
        for version, spec, expected in cases:
            with self.subTest(version=version, spec=spec):
                self.assertEqual(registry.npm_satisfies(version, spec), expected)

    def test_pypi_specifiers(self):
        cases = [("2.31.0", ">=2", True), ("1.9", ">=2", False), ("2.4.1", "~=2.4", True),
                 ("3.0", "~=2.4", False), ("1.2.3", "==1.2.*", True), ("1.3.0", "!=1.3.0", False),
                 ("2.0.0rc1", ">=1", False), ("1.5", ">=1,<2", True)]
        for version, spec, expected in cases:
            with self.subTest(version=version, spec=spec):
                self.assertEqual(registry.pypi_satisfies(version, spec), expected)


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeRegistry()
        patcher = mock.patch.object(registry, "fetch_bytes", self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_npm_latest_exact_tag_and_range(self):
        archive = tgz({"package.json": "{}"})
        self.fake.npm("cowsay", {"1.5.0": archive, "1.6.0": archive, "2.0.0-beta": archive},
                      latest="1.6.0", tags={"next": "2.0.0-beta"})
        self.assertEqual(registry.resolve_npm("cowsay", None).version, "1.6.0")
        self.assertEqual(registry.resolve_npm("cowsay", "1.5.0").version, "1.5.0")
        self.assertEqual(registry.resolve_npm("cowsay", "next").version, "2.0.0-beta")
        self.assertEqual(registry.resolve_npm("cowsay", "^1.0.0").version, "1.6.0")
        with self.assertRaises(Unscannable):
            registry.resolve_npm("cowsay", "^3")
        with self.assertRaises(Unscannable):
            registry.resolve_npm("not-published", None)

    def test_npm_scoped_names_are_encoded(self):
        self.fake.npm("@scope/tool", {"1.0.0": tgz({"index.js": "1"})})
        artifact = registry.resolve_npm("@scope/tool", None)
        self.assertEqual(artifact.label, "@scope/tool@1.0.0")

    def test_pypi_prefers_the_pure_wheel_then_the_sdist(self):
        pure = wheel({"pkg/__init__.py": "x = 1\n"})
        sdist = tgz({"pkg/__init__.py": "x = 1\n"}, root="pkg-1.0")
        self.fake.pypi("pkg", "1.0", [("pkg-1.0-py3-none-any.whl", pure, "bdist_wheel"),
                                      ("pkg-1.0.tar.gz", sdist, "sdist")])
        self.assertEqual(registry.resolve_pypi("pkg", None).kind, "zip")
        self.fake.pypi("src", "2.0", [("src-2.0.tar.gz", sdist, "sdist"),
                                      ("src-2.0-cp312-cp312-win_amd64.whl", pure, "bdist_wheel")])
        self.assertEqual(registry.resolve_pypi("src", None).kind, "tgz")

    def test_pypi_compiled_only_and_specifiers(self):
        compiled = wheel({"x.pyd": b"MZ"})
        self.fake.pypi("fast", "3.0", [("fast-3.0-cp312-cp312-win_amd64.whl", compiled, "bdist_wheel")])
        with self.assertRaises(Unscannable):
            registry.resolve_pypi("fast", None)
        pure = wheel({"m.py": "1"})
        self.fake.pypi("lib", "2.5", [("lib-2.5-py3-none-any.whl", pure, "bdist_wheel")],
                       older={"1.9": [("lib-1.9-py3-none-any.whl", pure, "bdist_wheel")]})
        self.assertEqual(registry.resolve_pypi("lib", "<2").version, "1.9")
        self.assertEqual(registry.resolve_pypi("lib", "==2.5").version, "2.5")

    def test_github_refs(self):
        head, tag, branch = "a" * 40, "b" * 40, "c" * 40
        self.fake.github("o/r", {"HEAD": head, "refs/heads/main": head, "refs/heads/dev": branch,
                                 "refs/tags/v1": "d" * 40, "refs/tags/v1^{}": tag}, {})
        self.assertEqual(registry.resolve_github("o/r", None).version, head)
        self.assertEqual(registry.resolve_github("o/r", "dev").version, branch)
        self.assertEqual(registry.resolve_github("o/r", "v1").version, tag)
        self.assertEqual(registry.resolve_github("o/r", "e" * 40).version, "e" * 40)
        with self.assertRaises(Unscannable):
            registry.resolve_github("o/r", "abc1234")
        with self.assertRaises(Unscannable):
            registry.resolve_github("o/r", "missing")

    def test_download_is_checked_against_the_registry_checksum(self):
        good = tgz({"index.js": "1"})
        self.fake.npm("pkg", {"1.0.0": good})
        artifact = registry.resolve_npm("pkg", None)
        self.assertEqual(registry.download(artifact), good)
        self.fake.responses[artifact.url] = tgz({"index.js": "tampered"})
        with self.assertRaises(Refused):
            registry.download(artifact)


class RealFetchPolicyTests(unittest.TestCase):
    def test_non_https_and_foreign_hosts_are_refused_without_a_request(self):
        for url in ("http://registry.npmjs.org/x", "https://evil.example/x.tgz",
                    "https://registry.npmjs.org.evil.example/x"):
            with self.subTest(url=url), mock.patch("urllib.request.OpenerDirector.open") as opener:
                with self.assertRaises(Unscannable):
                    registry.fetch_bytes(url, 100)
                opener.assert_not_called()


class UnpackTests(unittest.TestCase):
    def artifact(self, kind="tgz", subdir=""):
        return registry.Artifact("npm", "p", "1.0.0", "p@1.0.0", "u", "", kind, subdir)

    def test_code_is_staged_and_everything_else_is_counted_not_stored(self):
        staged = registry.unpack(self.artifact(), tgz({
            "package.json": "{}", "dist/index.js": "module.exports = 1",
            "logo.png": b"\x89PNG....", "bin/tool": b"\x7fELF...."}))
        self.assertEqual(sorted(staged.files), ["dist/index.js", "package.json"])
        self.assertEqual(staged.compiled, ["bin/tool"])
        self.assertEqual(staged.skipped, 1)

    def test_compiled_extensions_are_flagged(self):
        staged = registry.unpack(self.artifact(), tgz({"build/Release/addon.node": b"\x00", "a.js": "1"}))
        self.assertEqual(staged.compiled, ["build/Release/addon.node"])

    def test_unsafe_archives_are_refused(self):
        for files, links in (({"../escape.js": "x"}, None), ({"a.js": "1", "A.js": "2"}, None),
                             ({"a.js": "1"}, {"link.js": "/etc/passwd"})):
            with self.subTest(files=files, links=links), self.assertRaises(Refused):
                registry.unpack(self.artifact(), tgz(files, links=links))

    def test_two_top_level_folders_are_refused(self):
        raw = tgz({"package/a.js": "1", "other/b.js": "2"}, root="")
        with self.assertRaises(Refused):
            registry.unpack(self.artifact(), raw)

    def test_oversized_code_cannot_be_scanned(self):
        with mock.patch.object(registry, "MAX_CODE_FILE_BYTES", 10):
            with self.assertRaises(Unscannable):
                registry.unpack(self.artifact(), tgz({"big.js": "x" * 50}))

    def test_subdirectory_of_a_repository(self):
        staged = registry.unpack(self.artifact(subdir="plugins/tool"),
                                 tgz({"plugins/tool/x.js": "1", "other/y.js": "2"}, root="repo-sha"))
        self.assertEqual(list(staged.files), ["x.js"])
        with self.assertRaises(Unscannable):
            registry.unpack(self.artifact(subdir="missing"), tgz({"a.js": "1"}, root="repo-sha"))

    def test_wheels_have_no_single_root(self):
        staged = registry.unpack(self.artifact("zip"), wheel({"pkg/__init__.py": "x=1",
                                                              "pkg-1.0.dist-info/METADATA": "Name: pkg"}))
        self.assertIn("pkg/__init__.py", staged.files)


if __name__ == "__main__":
    unittest.main()
