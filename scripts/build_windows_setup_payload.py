"""Build-time offline Windows setup payload. Never execute archive contents.

This is not an installer or a bootstrap trust anchor. Runtime pinning happens
before ZIP parsing; the eventual native launcher must independently authenticate
its entire payload before launching Python. No network, PATH lookup or installs.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import zipfile


MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_FILES = 4096

RESERVED = {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$',
            *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}


def verified_archive(data, expected_sha256):
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ValueError('compressed archive budget exceeded')
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError('archive digest mismatch')
    try:
        return _archive_files(data)
    except (zipfile.BadZipFile, EOFError) as error:
        raise ValueError('malformed archive') from error


def _archive_files(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if (not entries or len(entries) > MAX_FILES
                or sum(entry.file_size for entry in entries) > MAX_TOTAL_BYTES
                or any(entry.file_size > MAX_FILE_BYTES for entry in entries)):
            raise ValueError('expanded archive budget exceeded')
        names = {}
        files = set()
        directories = set()
        for entry in archive.infolist():
            if entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise ValueError('unsupported archive compression')
            name = entry.filename
            parts = name.split('/')
            if entry.orig_filename != name or any(
                not re.fullmatch(r'[A-Za-z0-9_.-]{1,240}', part)
                or part in ('.', '..') or part.endswith('.')
                or part.split('.')[0].upper() in RESERVED for part in parts
            ):
                raise ValueError('unsafe archive path')
            mode = stat.S_IFMT(entry.external_attr >> 16)
            if entry.is_dir() or mode not in (0, stat.S_IFREG) or entry.external_attr & 0x18:
                raise ValueError('only regular archive files allowed')
            for index in range(1, len(parts) + 1):
                prefix = '/'.join(parts[:index])
                key = prefix.lower()
                if key in names and names[key] != prefix:
                    raise ValueError('case-alias archive path')
                names[key] = prefix
                if index < len(parts):
                    if key in files:
                        raise ValueError('archive file/directory collision')
                    directories.add(key)
                elif key in files or key in directories:
                    raise ValueError('duplicate or colliding archive file')
                else:
                    files.add(key)
        return {entry.filename: archive.read(entry) for entry in archive.infolist()}


RUNTIME_VERSION = '3.14.7'
RUNTIME_URL = 'https://www.python.org/ftp/python/3.14.7/python-3.14.7-embed-amd64.zip'
RUNTIME_SHA256 = 'd297e5ff019966817ad8502465176139f2d3d840fa4ed84b13bed399a6ab1f15'


def read_archive(path):
    with Path(path).open('rb') as source:
        data = source.read(MAX_ARCHIVE_BYTES + 1)
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ValueError('compressed archive budget exceeded')
    return data


def publish_new(output, data):
    """Publish complete bytes without replacing a name; no partial final ZIP.

    This developer build operation requires a trusted output parent supporting
    hard links. No rename/overwrite fallback. It is not the install transaction.
    """
    output = Path(output)
    fd, temporary = tempfile.mkstemp(prefix='.trojaino-payload-', dir=output.parent)
    try:
        with os.fdopen(fd, 'wb') as target:
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
        os.link(temporary, output)
    finally:
        Path(temporary).unlink()


def build(runtime_path, source_path, source_sha256, source_commit, output):
    """Package explicitly pinned developer inputs. Commit is a caller declaration.

    The digest is verified, but a commit string alone cannot prove that a ZIP
    was built from Git. Release engineering must compare source bytes against
    the reviewed commit separately; metadata deliberately calls it declared.
    """
    if not re.fullmatch(r'[0-9a-f]{40}', source_commit):
        raise ValueError('literal lowercase 40-character source commit required')
    runtime = read_archive(runtime_path)
    source = read_archive(source_path)
    runtime_files = verified_archive(runtime, RUNTIME_SHA256)
    source_files = verified_archive(source, source_sha256)
    metadata = {
        'schema': 1,
        'trial': 'setup-experiment-20260912-01',
        'classification': 'engineering-only-not-an-installer',
        'platform': 'windows-x64',
        'declared_source_commit': source_commit,
        'runtime_version': RUNTIME_VERSION,
        'runtime_url': RUNTIME_URL,
        'archives': {},
    }
    for name, data, files in [('runtime.zip', runtime, runtime_files),
                              ('source.zip', source, source_files)]:
        metadata['archives'][name] = {
            'sha256': hashlib.sha256(data).hexdigest(),
            'files': {key: hashlib.sha256(value).hexdigest() for key, value in sorted(files.items())},
        }
    payload = {'runtime.zip': runtime, 'source.zip': source,
               'payload.json': (json.dumps(metadata, indent=2, sort_keys=True) + '\n').encode()}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, data in sorted(payload.items()):
            info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, data)
    data = buffer.getvalue()
    publish_new(output, data)
    return {'artifact': str(output), 'sha256': hashlib.sha256(data).hexdigest(),
            'classification': metadata['classification']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.runtime, args.source, args.source_sha256,
                           args.source_commit, args.output)))
