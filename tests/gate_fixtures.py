"""Build real package archives in memory and serve them from a fake registry.

No test here touches the network: registry.fetch_bytes is replaced with a
lookup in a dictionary of URL -> bytes built from these helpers.
"""
import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"


def tgz(files: dict, root: str = "package", links: dict | None = None) -> bytes:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w:gz") as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(f"{root}/{name}" if root else name)
            data = data if isinstance(data, bytes) else data.encode()
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        for name, target in (links or {}).items():
            info = tarfile.TarInfo(f"{root}/{name}")
            info.type = tarfile.SYMTYPE
            info.linkname = target
            archive.addfile(info)
    return raw.getvalue()


def wheel(files: dict) -> bytes:
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return raw.getvalue()


def fixture_files(name: str) -> dict:
    base = FIXTURES / name
    return {p.relative_to(base).as_posix(): p.read_bytes() for p in base.rglob("*") if p.is_file()}


def sha512(data: bytes) -> str:
    return "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()


class FakeRegistry:
    """Enough of registry.npmjs.org, pypi.org and github.com to resolve and download."""

    def __init__(self):
        self.responses: dict[str, bytes] = {}
        self.requests: list[str] = []

    def __call__(self, url, limit, accept="*/*"):
        from trojaino.registry import Unscannable
        self.requests.append(url)
        if url not in self.responses:
            raise Unscannable("it could not be found (it may be misspelled or removed)")
        return self.responses[url]

    def npm(self, name: str, versions: dict, latest: str | None = None, tags: dict | None = None):
        meta = {"name": name, "dist-tags": dict(tags or {}, latest=latest or list(versions)[-1]),
                "versions": {}}
        for version, archive in versions.items():
            url = f"https://registry.npmjs.org/{name}/-/{name.split('/')[-1]}-{version}.tgz"
            self.responses[url] = archive
            meta["versions"][version] = {"dist": {"tarball": url, "integrity": sha512(archive)}}
        self.responses[f"https://registry.npmjs.org/{name.replace('/', '%2f')}"] = json.dumps(meta).encode()

    def pypi(self, name: str, version: str, files: list, older: dict | None = None):
        def entry(filename, data, kind):
            url = f"https://files.pythonhosted.org/packages/xx/{filename}"
            self.responses[url] = data
            return {"filename": filename, "url": url, "packagetype": kind, "yanked": False,
                    "digests": {"sha256": hashlib.sha256(data).hexdigest()}}
        urls = [entry(*f) for f in files]
        releases = {version: urls}
        for other, other_files in (older or {}).items():
            releases[other] = [entry(*f) for f in other_files]
        self.responses[f"https://pypi.org/pypi/{name}/json"] = json.dumps(
            {"info": {"version": version}, "urls": urls, "releases": releases}).encode()
        self.responses[f"https://pypi.org/pypi/{name}/{version}/json"] = json.dumps(
            {"info": {"version": version}, "urls": urls}).encode()

    def github(self, repo: str, refs: dict, archives: dict):
        lines = []
        head = refs.get("HEAD")
        for i, (ref, sha) in enumerate(refs.items()):
            text = f"{sha} {ref}" + ("\0symref=HEAD:refs/heads/main agent=git" if i == 0 else "") + "\n"
            lines.append(f"{len(text) + 4:04x}{text}")
        body = "001e# service=git-upload-pack\n0000" + "".join(lines) + "0000"
        self.responses[f"https://github.com/{repo}.git/info/refs?service=git-upload-pack"] = body.encode()
        for sha, archive in archives.items():
            self.responses[f"https://codeload.github.com/{repo}/tar.gz/{sha}"] = archive
        return head
