"""Generate compiled pins for one explicitly approved offline setup payload.

Developer build step only. Hash arguments are build approvals, never end-user
options. A source commit remains a declaration; compare source bytes to Git
before approving it. No download, extraction, runtime execution or config edits.
"""
import argparse
import hashlib
import io
import zipfile
from pathlib import Path
import re
import runpy

_HELPER = runpy.run_path(str(Path(__file__).with_name('build_windows_setup_payload.py')))
RUNTIME_SHA256 = _HELPER['RUNTIME_SHA256']


def render(payload, payload_sha256, source_sha256, source_commit):
    for digest in (payload_sha256, source_sha256):
        if not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise ValueError('literal lowercase SHA256 required')
    if not re.fullmatch(r'[0-9a-f]{40}', source_commit):
        raise ValueError('literal lowercase source commit required')
    outer = _HELPER['verified_archive'](payload, payload_sha256)
    if set(outer) != {'runtime.zip', 'source.zip', 'payload.json'}:
        raise ValueError('unexpected setup payload inventory')
    # The embedded manifest supplies NO trust. Recompute from separately pinned inputs.
    inputs = [('Runtime', 'runtime.zip', RUNTIME_SHA256), ('Source', 'source.zip', source_sha256)]
    methods = []
    for label, name, digest in inputs:
        files = _HELPER['verified_archive'](outer[name], digest)
        # Match the native stager's stricter spelling/depth/metadata budgets.
        with zipfile.ZipFile(io.BytesIO(outer[name])) as checked:
            if any(entry.external_attr & 0x400 for entry in checked.infolist()):
                raise ValueError('native stager refuses reparse metadata')
        if any(len(key) > 200 or len(key.split('/')) > 12
               or any(len(part) > 120 for part in key.split('/')) for key in files):
            raise ValueError('native stager path budget exceeded')
        rows = ',\n'.join('                {"' + key + '", "' + hashlib.sha256(data).hexdigest() + '"}'
                         for key, data in sorted(files.items()))
        members = ', '.join('"' + key + '"' for key in sorted(files))
        methods.append('''        // Fresh path-budget metadata, never caller-supplied extraction authority.
        internal static string[] %sMembers()
        { return new[] {%s}; }
''' % (label, members))
        methods.append('''        internal static Bootstrap.Receipt Stage%s(string destination)
        {
            return Bootstrap.Install(ReadArchive("%s"), "%s",
                new Dictionary<string, string>(StringComparer.Ordinal) {
%s
                }, destination);
        }
''' % (label, name, digest, rows))
    return '''// GENERATED developer trust adapter. Review pins and compile with the exact resource.
// Not an installer UI, activation mechanism or native Windows qualification.
using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Reflection;

namespace Trojaino.Setup
{
    internal static class ApprovedPayload
    {
        internal const string DeclaredSourceCommit = "%s";
        internal const string PayloadSha256 = "%s";
        static byte[] ReadBounded(Stream input)
        {
            if (input == null) throw new InvalidDataException("Missing approved embedded payload");
            using (var output = new MemoryStream())
            {
                var buffer = new byte[8192];
                int count;
                while ((count = input.Read(buffer, 0, buffer.Length)) > 0)
                {
                    if (output.Length + count > 64 * 1024 * 1024) throw new InvalidDataException("Embedded payload budget exceeded");
                    output.Write(buffer, 0, count);
                }
                return output.ToArray();
            }
        }
        static byte[] ReadArchive(string name)
        {
            byte[] data;
            using (var input = Assembly.GetExecutingAssembly().GetManifestResourceStream("Trojaino.Setup.Payload"))
                data = ReadBounded(input);
            if (Bootstrap.Hash(data) != PayloadSha256) throw new InvalidDataException("Embedded payload digest mismatch");
            using (var memory = new MemoryStream(data, false))
            using (var zip = new ZipArchive(memory, ZipArchiveMode.Read))
            {
                var entry = zip.GetEntry(name);
                if (entry == null) throw new InvalidDataException("Missing approved nested archive");
                using (var input = entry.Open()) return ReadBounded(input);
            }
        }
%s    }
}
''' % (source_commit, payload_sha256, '\n'.join(methods))


def build(payload_path, payload_sha256, source_sha256, source_commit, output):
    data = _HELPER['read_archive'](payload_path)
    generated = render(data, payload_sha256, source_sha256, source_commit).encode('utf-8')
    _HELPER['publish_new'](output, generated)
    return {'output': str(output), 'sha256': hashlib.sha256(generated).hexdigest(),
            'classification': 'engineering-only-compiled-trust-adapter'}


if __name__ == '__main__':
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--payload-sha256', required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.payload, args.payload_sha256, args.source_sha256,
                           args.source_commit, args.output)))
