"""Fetch exactly what an install would fetch, without running any of it.

Each source is resolved to one immutable artifact first (an npm version with
its sha512 integrity, a PyPI file with its sha256, a GitHub commit), then
downloaded with hard size and time limits and checked against that digest.
Nothing here executes package code: no lifecycle scripts, no builds, no
setup.py. Archives are unpacked by our own code with the same safety rules as
the rest of Trojaino (no links, no traversal, no case-colliding names).

Only these hosts are ever contacted, and only while an install is happening:
registry.npmjs.org, pypi.org, files.pythonhosted.org, github.com and
codeload.github.com.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import gzip
import hashlib
import io
import json
import re
import tarfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile

NPM_REGISTRY = "https://registry.npmjs.org"
PYPI = "https://pypi.org"
GITHUB = "https://github.com"
CODELOAD = "https://codeload.github.com"
ALLOWED_HOSTS = {"registry.npmjs.org", "pypi.org", "files.pythonhosted.org",
                 "github.com", "codeload.github.com"}

MAX_METADATA_BYTES = 40_000_000
MAX_ARCHIVE_BYTES = 15_000_000
MAX_UNPACKED_BYTES = 60_000_000
MAX_FILES = 5000
MAX_ENTRIES = 20000
MAX_DEPTH = 50
MAX_CODE_FILE_BYTES = 1_000_000
MAX_CODE_BYTES = 25_000_000
DOWNLOAD_SECONDS = 30

# Code that cannot be read as text. A package carrying any of it is never
# auto-allowed, because Trojaino has no way to tell what it does.
COMPILED_SUFFIXES = (".node", ".so", ".dll", ".dylib", ".exe", ".pyd", ".a", ".lib", ".o",
                     ".wasm", ".bin", ".jar", ".class", ".msi", ".com", ".scr", ".sys")
_MAGIC = (b"\x7fELF", b"MZ", b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe",
          b"\x00asm")


class Unscannable(Exception):
    """The artifact exists but Trojaino cannot vet it; say why in plain words."""


class Refused(Exception):
    """The artifact itself is unsafe to unpack (traversal, links, and so on)."""


@dataclass(frozen=True)
class Artifact:
    ecosystem: str
    name: str
    version: str        # exact version, or a 40-character commit
    label: str          # what the user sees, e.g. "cowsay@1.6.0"
    url: str
    digest: str         # "sha512-<base64>", "sha256:<hex>" or "" for a commit archive
    kind: str           # "tgz" | "zip"
    subdir: str = ""    # only this folder of a repository is scanned
    # PyPI only: the release also has wheels other than this file, so an
    # installer given just the version might choose code Trojaino did not scan.
    alternatives: bool = False


@dataclass
class Staged:
    files: dict          # relative path -> bytes, code and text files only
    compiled: list       # relative paths of compiled code that was not read
    skipped: int         # other non-code files (images, fonts, data) not staged


# ---------------------------------------------------------------- HTTP


class _Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).hostname not in ALLOWED_HOSTS or not newurl.startswith("https://"):
            raise Unscannable("the download redirected to a host Trojaino does not trust")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_bytes(url: str, limit: int, accept: str = "*/*") -> bytes:
    """One bounded HTTPS GET to an allowed host. Raises Unscannable on any failure."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS:
        raise Unscannable("the package is hosted somewhere Trojaino does not fetch from")
    opener = urllib.request.build_opener(_Redirects())
    request = urllib.request.Request(url, headers={
        "User-Agent": "trojaino-install-gate", "Accept": accept, "Accept-Encoding": "identity"})
    deadline = time.monotonic() + DOWNLOAD_SECONDS
    try:
        with opener.open(request, timeout=15) as response:
            chunks = bytearray()
            while True:
                if time.monotonic() > deadline:
                    raise Unscannable("the download took too long")
                chunk = response.read(65536)
                if not chunk:
                    return bytes(chunks)
                chunks.extend(chunk)
                if len(chunks) > limit:
                    raise Unscannable("the package is too large for Trojaino to scan")
    except urllib.error.HTTPError as exc:
        if exc.code in {404, 410}:
            raise Unscannable("it could not be found (it may be misspelled or removed)") from exc
        if exc.code in {401, 403, 407}:
            raise Unscannable("the registry refused the request (the package may be private, "
                              "or a network proxy is blocking it)") from exc
        raise Unscannable(f"the registry answered with an error ({exc.code})") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise Unscannable("the registry could not be reached") from exc


def _json(url: str, accept: str = "application/json") -> dict:
    try:
        data = json.loads(fetch_bytes(url, MAX_METADATA_BYTES, accept))
    except ValueError as exc:
        raise Unscannable("the registry returned something unreadable") from exc
    if not isinstance(data, dict):
        raise Unscannable("the registry returned something unreadable")
    return data


# ---------------------------------------------------------------- versions

_SEMVER = re.compile(r"v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?")


def _semver(version: str):
    m = _SEMVER.fullmatch(version)
    if not m:
        return None
    pre = tuple((0, int(p)) if p.isdigit() else (1, p) for p in m[4].split(".")) if m[4] else None
    return (int(m[1]), int(m[2]), int(m[3])), pre


def _semver_key(version: str):
    parsed = _semver(version)
    if parsed is None:
        return ((-1, -1, -1), 0, ())
    core, pre = parsed
    return (core, 0 if pre else 1, pre or ())


def _partial(text: str):
    parts = text.lstrip("v=").split(".")
    nums = []
    for part in parts[:3]:
        if part in {"x", "X", "*", ""}:
            break
        if not part.isdigit():
            return None
        nums.append(int(part))
    return nums


def _comparator(op: str, text: str):
    nums = _partial(text)
    if nums is None:
        raise ValueError(text)
    full = nums + [0] * (3 - len(nums))
    low = tuple(full)
    if op in {"", "="} and len(nums) < 3:          # x-range: 1.2 or 1.x
        if not nums:
            return [lambda v: True]
        high = list(nums)
        high[-1] += 1
        high = tuple(high + [0] * (3 - len(high)))
        return [lambda v, l=low: v >= l, lambda v, h=high: v < h]
    if op == "^":
        if full[0] > 0 or len(nums) == 1:
            high = (full[0] + 1, 0, 0)
        elif full[1] > 0 or len(nums) == 2:
            high = (0, full[1] + 1, 0)
        else:
            high = (0, 0, full[2] + 1)
        return [lambda v, l=low: v >= l, lambda v, h=high: v < h]
    if op == "~":
        high = (full[0] + 1, 0, 0) if len(nums) == 1 else (full[0], full[1] + 1, 0)
        return [lambda v, l=low: v >= l, lambda v, h=high: v < h]
    table = {">=": lambda v, l=low: v >= l, "<=": lambda v, l=low: v <= l,
             ">": lambda v, l=low: v > l, "<": lambda v, l=low: v < l,
             "=": lambda v, l=low: v == l, "": lambda v, l=low: v == l}
    return [table[op]]


def npm_satisfies(version: str, spec: str) -> bool:
    """A small npm range matcher: x-ranges, ^, ~, comparators, hyphen and ||."""
    parsed = _semver(version)
    if parsed is None or parsed[1] is not None:   # prereleases only by exact version
        return False
    core = parsed[0]
    for alternative in spec.split("||"):
        alternative = alternative.strip()
        m = re.fullmatch(r"(\S+)\s+-\s+(\S+)", alternative)
        tests = []
        try:
            if m:
                tests = _comparator(">=", m[1]) + _comparator("<=", m[2])
            else:
                for part in re.findall(r"(\^|~|>=|<=|>|<|=)?\s*([0-9vxX*][0-9A-Za-z.*]*)", alternative):
                    tests += _comparator(part[0], part[1])
        except (ValueError, KeyError):
            return False
        if tests and all(test(core) for test in tests):
            return True
    return False


_PEP440 = re.compile(r"(\d+(?:\.\d+)*)((?:a|b|rc)\d+)?(\.post\d+)?(\.dev\d+)?", re.I)


def _pep440(version: str):
    m = _PEP440.fullmatch(version.strip().lower().lstrip("v"))
    if not m:
        return None
    release = tuple(int(x) for x in m[1].split("."))
    return release, bool(m[2] or m[4])


def pypi_satisfies(version: str, spec: str) -> bool:
    parsed = _pep440(version)
    if parsed is None:
        return False
    release, prerelease = parsed
    for clause in spec.split(","):
        m = re.fullmatch(r"\s*(===|==|~=|!=|<=|>=|<|>)\s*(\S+)\s*", clause)
        if not m:
            return False
        op, target = m[1], m[2]
        if op in {"==", "==="} and target == version:
            continue
        if op in {"==", "!="} and target.endswith(".*"):
            prefix = tuple(int(x) for x in target[:-2].split(".") if x.isdigit())
            hit = release[:len(prefix)] == prefix
            if hit != (op == "=="):
                return False
            continue
        other = _pep440(target)
        if other is None:
            return False
        length = max(len(release), len(other[0]))
        a = release + (0,) * (length - len(release))
        b = other[0] + (0,) * (length - len(other[0]))
        if op == "~=":
            upper = list(other[0][:-1])
            upper[-1] += 1
            u = tuple(upper) + (0,) * (length - len(upper))
            ok = a >= b and a < u
        else:
            ok = {"==": a == b, "===": a == b, "!=": a != b, "<=": a <= b, ">=": a >= b,
                  "<": a < b, ">": a > b}[op]
        if not ok:
            return False
    return not prerelease or any(c.strip().startswith(("==", "===")) for c in spec.split(","))


# ---------------------------------------------------------------- resolve


def resolve_npm(name: str, spec: str | None) -> Artifact:
    encoded = name.replace("/", "%2f")
    meta = _json(f"{NPM_REGISTRY}/{encoded}", "application/vnd.npm.install-v1+json")
    versions = meta.get("versions") or {}
    tags = meta.get("dist-tags") or {}
    wanted = (spec or "latest").strip()
    if wanted in tags:
        version = tags[wanted]
    elif wanted in versions:
        version = wanted
    else:
        matching = [v for v in versions if npm_satisfies(v, wanted)]
        if not matching:
            raise Unscannable(f"no published version of {name} matches {wanted!r}")
        version = max(matching, key=_semver_key)
    dist = (versions.get(version) or {}).get("dist") or {}
    url, integrity = dist.get("tarball", ""), dist.get("integrity", "")
    if not url.startswith(NPM_REGISTRY + "/") or not integrity.startswith("sha512-"):
        raise Unscannable(f"{name}@{version} has no verifiable download")
    return Artifact("npm", name, version, f"{name}@{version}", url, integrity, "tgz")


def resolve_pypi(name: str, spec: str | None) -> Artifact:
    exact = spec[2:] if spec and spec.startswith("==") and "," not in spec and "*" not in spec else None
    meta = _json(f"{PYPI}/pypi/{name}/{exact}/json" if exact else f"{PYPI}/pypi/{name}/json")
    if exact:
        version, files = meta.get("info", {}).get("version", exact), meta.get("urls") or []
    elif not spec:
        version = meta.get("info", {}).get("version")
        files = meta.get("urls") or []
    else:
        releases = meta.get("releases") or {}
        candidates = [v for v, fs in releases.items()
                      if fs and not all(f.get("yanked") for f in fs) and pypi_satisfies(v, spec)]
        if not candidates:
            raise Unscannable(f"no published version of {name} matches {spec!r}")
        version = max(candidates, key=lambda v: _pep440(v)[0])
        files = releases[version]
    files = [f for f in files if not f.get("yanked")]
    def py3_pure(filename: str) -> bool:
        # name-version[-build]-PYTAG-none-any.whl; a py2-only wheel is never chosen by Python 3.
        parts = filename[:-4].split("-")
        return (filename.endswith("-none-any.whl") and len(parts) >= 5
                and any(tag.startswith("py3") for tag in parts[-3].split(".")))
    pure = [f for f in files if f.get("packagetype") == "bdist_wheel"
            and py3_pure(f.get("filename", ""))]
    sdists = [f for f in files if f.get("packagetype") == "sdist"
              and f.get("filename", "").endswith((".tar.gz", ".zip"))]
    wheels = [f for f in files if f.get("packagetype") == "bdist_wheel"]
    if pure:
        chosen = pure[0]
    elif sdists:
        chosen = sdists[0]
    elif wheels:
        raise Unscannable(f"{name} {version} is only published as compiled code")
    else:
        raise Unscannable(f"{name} {version} has no downloadable files")
    digest = (chosen.get("digests") or {}).get("sha256", "")
    url = chosen.get("url", "")
    if not re.fullmatch(r"[0-9a-f]{64}", digest) or not url.startswith("https://files.pythonhosted.org/"):
        raise Unscannable(f"{name} {version} has no verifiable download")
    kind = "tgz" if chosen["filename"].endswith(".tar.gz") else "zip"
    alternatives = any(f is not chosen for f in wheels)
    return Artifact("pypi", name, version, f"{name}=={version}", url, "sha256:" + digest, kind,
                    alternatives=alternatives)


def _pkt_lines(data: bytes):
    i = 0
    while i + 4 <= len(data):
        length = int(data[i:i + 4], 16)
        if length == 0:
            i += 4
            continue
        yield data[i + 4:i + length]
        i += length


def resolve_github(repo: str, ref: str | None, subdir: str = "") -> Artifact:
    owner, _, name = repo.partition("/")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]+", name) \
            or name in {".", ".."}:
        raise Unscannable("the repository name is not recognised")
    name = name[:-4] if name.endswith(".git") else name
    if ref and re.fullmatch(r"[0-9a-f]{40}", ref):
        sha = ref
    else:
        advertised = fetch_bytes(f"{GITHUB}/{owner}/{name}.git/info/refs?service=git-upload-pack",
                                 5_000_000, "application/x-git-upload-pack-advertisement")
        refs: dict[str, str] = {}
        head_target = None
        for line in _pkt_lines(advertised):
            text = line.decode("utf-8", "replace").rstrip("\n")
            if text.startswith("#"):
                continue
            sha_part, _, rest = text.partition(" ")
            ref_name, _, capabilities = rest.partition("\0")
            m = re.search(r"symref=HEAD:(\S+)", capabilities)
            if m:
                head_target = m[1]
            if re.fullmatch(r"[0-9a-f]{40}", sha_part):
                refs[ref_name] = sha_part
        if ref is None:
            sha = refs.get("HEAD") or (refs.get(head_target) if head_target else None)
        else:
            sha = (refs.get(f"refs/tags/{ref}^{{}}") or refs.get(f"refs/tags/{ref}")
                   or refs.get(f"refs/heads/{ref}") or refs.get(ref))
            if sha is None and re.fullmatch(r"[0-9a-f]{7,39}", ref):
                raise Unscannable("a shortened commit id cannot be checked; use the full 40 characters")
        if not sha:
            raise Unscannable(f"{repo} has no branch or tag named {ref!r}" if ref else f"{repo} is empty")
    label = f"{owner}/{name}@{sha[:12]}" + (f" ({subdir})" if subdir else "")
    return Artifact("github", f"{owner}/{name}", sha, label,
                    f"{CODELOAD}/{owner}/{name}/tar.gz/{sha}", "", "tgz", subdir.strip("/"))


# ---------------------------------------------------------------- download + unpack


def download(artifact: Artifact) -> bytes:
    data = fetch_bytes(artifact.url, MAX_ARCHIVE_BYTES)
    if artifact.digest.startswith("sha512-"):
        expected = base64.b64decode(artifact.digest[7:])
        if hashlib.sha512(data).digest() != expected:
            raise Refused("the download does not match the registry's checksum")
    elif artifact.digest.startswith("sha256:"):
        if hashlib.sha256(data).hexdigest() != artifact.digest[7:]:
            raise Refused("the download does not match the registry's checksum")
    return data


def _valid_component(part: str) -> bool:
    from trojaino.preflight_paths import valid_component
    return valid_component(part)


def _is_code(path: str) -> bool:
    from pathlib import PurePosixPath
    from trojaino.file_utils import should_scan
    return should_scan(PurePosixPath(path), "package")


class _Collector:
    def __init__(self, strip_root: bool, subdir: str):
        self.strip_root, self.subdir = strip_root, subdir.strip("/")
        self.staged = Staged({}, [], 0)
        self.root = None
        self.seen: dict[str, str] = {}
        self.entries = self.unpacked = self.code_bytes = 0

    def name(self, raw: str, is_dir: bool) -> str | None:
        self.entries += 1
        if self.entries > MAX_ENTRIES:
            raise Unscannable("the package has too many files for Trojaino to scan")
        if "\\" in raw or any(ord(c) < 32 for c in raw) or raw.startswith("/"):
            raise Refused("the archive contains an unsafe file name")
        parts = raw.rstrip("/").split("/")
        if len(parts) > MAX_DEPTH + 1 or any(not _valid_component(p) for p in parts):
            raise Refused("the archive contains an unsafe file name")
        for depth in range(1, len(parts) + 1):
            spelling = "/".join(parts[:depth])
            key = unicodedata.normalize("NFC", spelling).casefold()
            if self.seen.setdefault(key, spelling) != spelling:
                raise Refused("the archive contains names that collide on Windows or macOS")
        if self.strip_root:
            if self.root is None:
                self.root = parts[0]
            elif parts[0] != self.root:
                raise Refused("the archive does not have a single top folder")
            parts = parts[1:]
        if is_dir or not parts:
            return None
        path = "/".join(parts)
        if self.subdir:
            if not path.startswith(self.subdir + "/"):
                return None
            path = path[len(self.subdir) + 1:]
        return path

    def add(self, path: str, size: int, read) -> None:
        self.unpacked += max(size, 0)
        if self.unpacked > MAX_UNPACKED_BYTES:
            raise Unscannable("the package is too large for Trojaino to scan")
        lowered = path.lower()
        if lowered.endswith(COMPILED_SUFFIXES):
            self.staged.compiled.append(path)
            return
        if _is_code(path):
            if size > MAX_CODE_FILE_BYTES:
                raise Unscannable(f"{path} is too large for Trojaino to read")
            if len(self.staged.files) >= MAX_FILES:
                raise Unscannable("the package has too many files for Trojaino to scan")
            data = read(MAX_CODE_FILE_BYTES + 1)
            if len(data) > MAX_CODE_FILE_BYTES:
                raise Unscannable(f"{path} is too large for Trojaino to read")
            if data.startswith(_MAGIC):
                # A compiled program with a text-looking name, such as bin/tool.
                self.staged.compiled.append(path)
                return
            self.code_bytes += len(data)
            if self.code_bytes > MAX_CODE_BYTES:
                raise Unscannable("the package is too large for Trojaino to scan")
            self.staged.files[path] = data
            return
        if read(4).startswith(_MAGIC):
            self.staged.compiled.append(path)
        else:
            self.staged.skipped += 1


def unpack(artifact: Artifact, data: bytes) -> Staged:
    """Read the archive in memory. Nothing from it is executed or linked."""
    collector = _Collector(strip_root=artifact.kind == "tgz", subdir=artifact.subdir)
    try:
        if artifact.kind == "tgz":
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as compressed:
                raw = compressed.read(MAX_UNPACKED_BYTES + 1)
            if len(raw) > MAX_UNPACKED_BYTES:
                raise Unscannable("the package is too large for Trojaino to scan")
            with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
                for member in archive:
                    if member.type in (tarfile.XHDTYPE, tarfile.XGLTYPE):
                        continue
                    if member.issym() or member.islnk():
                        # Links are how archives escape their folder; refuse outright.
                        raise Refused("the archive contains links")
                    if not (member.isdir() or member.isfile()) or member.issparse():
                        if member.name.endswith("pax_global_header"):
                            continue
                        raise Refused("the archive contains special files")
                    path = collector.name(member.name, member.isdir())
                    if path is None:
                        continue
                    stream = archive.extractfile(member)
                    if stream is None:
                        raise Refused("the archive contains unreadable entries")
                    collector.add(path, member.size, stream.read)
        else:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for info in archive.infolist():
                    if info.flag_bits & 0x1:
                        raise Refused("the archive is encrypted")
                    mode = (info.external_attr >> 16) & 0o170000
                    if mode and mode not in (0o100000, 0o040000):
                        raise Refused("the archive contains links or special files")
                    path = collector.name(info.filename, info.is_dir())
                    if path is None:
                        continue
                    with archive.open(info) as stream:
                        collector.add(path, info.file_size, stream.read)
    except (tarfile.TarError, zipfile.BadZipFile, EOFError, OSError, ValueError) as exc:
        raise Refused("the archive is damaged or malformed") from exc
    if artifact.subdir and not collector.staged.files and not collector.staged.compiled:
        raise Unscannable(f"{artifact.subdir} was not found in {artifact.name}")
    return collector.staged
