// Authenticated approved preparation; no candidate execution or publication.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Trojaino.Setup
{
    internal static class TrustedPreparation
    {
        static void Require(bool ok, string why) { if (!ok) throw new InvalidDataException(why); }
        static bool Overlaps(string a, string b)
        {
            return string.Equals(a, b, StringComparison.OrdinalIgnoreCase)
                || a.StartsWith(b + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)
                || b.StartsWith(a + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase);
        }
        static void Absent(string path)
        {
            try { File.GetAttributes(path); }
            catch (FileNotFoundException) { return; }
            catch (DirectoryNotFoundException) { return; }
            throw new InvalidDataException("Final plugin destination already exists");
        }
        static string Quote(string value)
        {
            Require(!string.IsNullOrEmpty(value) && value.IndexOfAny(new[] {'\"', '\r', '\n', '\0'}) < 0 && !value.EndsWith("\\"), "Unsafe process argument");
            return "\"" + value + "\"";
        }
        internal static byte[] Render(StagedPayload receipt, string final, string name, Bootstrap.Receipt scratchReceipt, CancellationToken cancellation)
        {
            if (Environment.OSVersion.Platform != PlatformID.Win32NT) throw new PlatformNotSupportedException("Preparation requires native Windows");
            cancellation.ThrowIfCancellationRequested();
            if (receipt == null) throw new ArgumentNullException("receipt");
            Require(scratchReceipt != null && scratchReceipt.Hashes.Count == 0 && scratchReceipt.Identities.Count == 1, "Private empty scratch receipt required");
            string scratch = scratchReceipt.Root;
            Bootstrap.Verify(scratchReceipt);
            WindowsPreflight.Check(final, new[] { "scripts/preflight.py" });
            Require(name != null && System.Text.RegularExpressions.Regex.IsMatch(name, @"\Atrojaino-local-[a-z0-9]+(?:-[a-z0-9]+)*\z")
                && name.Length <= 120 && Path.GetFileName(final) == name, "Distinct matching personal plugin identity required");
            Require(!string.IsNullOrEmpty(scratch) && Path.IsPathRooted(scratch) && Path.GetFullPath(scratch) == scratch
                && Path.GetDirectoryName(scratch) == Path.GetDirectoryName(receipt.RuntimeRoot)
                && !Overlaps(scratch, receipt.RuntimeRoot) && !Overlaps(scratch, receipt.SourceRoot), "Distinct literal sibling scratch required");
            Require(!Overlaps(final, scratch) && !Overlaps(final, receipt.RuntimeRoot) && !Overlaps(final, receipt.SourceRoot), "Final plugin overlaps staging");
            WindowsPreflight.Check(Path.Combine(scratch, "scratch-check"), new string[0]);
            Bootstrap.PlainAncestors(scratch);
            Absent(final);
            string python = Path.Combine(receipt.RuntimeRoot, "python.exe");
            string helper = Path.Combine(receipt.SourceRoot, "trojaino-source", "scripts", "prepare_preflight_plugin.py");
            var start = new ProcessStartInfo {
                FileName = python,
                Arguments = "-I -S -B " + Quote(helper) + " " + Quote(final) + " --personal-plugin-name " + Quote(name) + " --plan",
                UseShellExecute = false, CreateNoWindow = true,
                RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true,
                WorkingDirectory = scratch
            };
            start.EnvironmentVariables.Clear();
            start.EnvironmentVariables["SystemRoot"] = Environment.GetFolderPath(Environment.SpecialFolder.Windows);
            start.EnvironmentVariables["TEMP"] = scratch;
            start.EnvironmentVariables["TMP"] = scratch;
            Bootstrap.Verify(scratchReceipt);
            StagedPayload.Verify(receipt); // Compiled source/runtime authority immediately before execution.
            byte[] plan = RunProcess(start, 60000, 16 * 1024 * 1024, 64 * 1024, cancellation
#if PREPARATION_TESTS
                , null
#endif
            );
            cancellation.ThrowIfCancellationRequested();
            StagedPayload.Verify(receipt);
            Bootstrap.Verify(scratchReceipt); // Successful helper must leave its private temporary root empty.
            Absent(final);
            Require(plan.Length > 0, "Empty preparation output");
            return plan; // No parsing, publication, activation or removal in this component.
        }

        internal static Bootstrap.Receipt Install(StagedPayload staged, string final, string name, Bootstrap.Receipt scratch, CancellationToken cancellation)
        {
            // No caller-supplied archive, hash, executable or manifest is accepted.
            byte[] plan = Render(staged, final, name, scratch, cancellation);
            cancellation.ThrowIfCancellationRequested();
            StagedPayload.Verify(staged);
            Bootstrap.Verify(scratch);
            return Publish(plan, final);
        }

        // Only authenticated transformation output reaches this private writer.
        static Bootstrap.Receipt Publish(byte[] plan, string final)
        {
            Require(plan != null && plan.Length > 0 && plan.Length <= 16 * 1024 * 1024, "Preparation archive budget exceeded");
            var pins = new Dictionary<string, string>(StringComparer.Ordinal);
            byte[] manifest = null;
            var expected = new HashSet<string>(new[] {
                ".claude-plugin/plugin.json", "LICENSE", "MANIFEST.sha256.json", "README.md",
                "hooks/hooks.json", "scripts/hook.sh", "scripts/preflight.py", "skills/scan/SKILL.md"
            }, StringComparer.Ordinal);
            using (var memory = new MemoryStream(plan, false))
            using (var zip = new ZipArchive(memory, ZipArchiveMode.Read))
            {
                Require(zip.Entries.Count == expected.Count, "Preparation inventory mismatch");
                long total = 0;
                foreach (var entry in zip.Entries)
                {
                    Require(expected.Remove(entry.FullName), "Unknown or duplicate preparation member");
                    Require(entry.Length >= 0 && entry.Length <= 8 * 1024 * 1024 && (total += entry.Length) <= 16 * 1024 * 1024, "Preparation expanded budget exceeded");
                    using (var input = entry.Open())
                    {
                        byte[] bytes = ReadOutput(input, (int)entry.Length);
                        Require(bytes.Length == entry.Length, "Preparation member length mismatch");
                        pins.Add(entry.FullName, Bootstrap.Hash(bytes));
                        if (entry.FullName == "MANIFEST.sha256.json") manifest = bytes;
                    }
                }
            }
            // Local helper's exact deterministic format; never deserialize as authority.
            string canonical = "{\n" + string.Join(",\n", pins.Where(p => p.Key != "MANIFEST.sha256.json")
                .OrderBy(p => p.Key, StringComparer.Ordinal).Select(p => "  \"" + p.Key + "\": \"" + p.Value + "\"")) + "\n}\n";
            Require(manifest != null && manifest.SequenceEqual(Encoding.UTF8.GetBytes(canonical)), "Preparation manifest mismatch");
            return Bootstrap.Install(plan, Bootstrap.Hash(plan), pins, final);
        }
#if PREPARATION_TESTS
        internal static Bootstrap.Receipt TestPublish(byte[] plan, string final)
        { return Publish(plan, final); }
#endif

        static byte[] ReadOutput(Stream input, int limit)
        {
            using (var output = new MemoryStream())
            {
                var buffer = new byte[8192]; int count;
                while ((count = input.Read(buffer, 0, buffer.Length)) > 0)
                {
                    if (output.Length + count > limit) throw new InvalidDataException("Helper output budget exceeded");
                    output.Write(buffer, 0, count);
                }
                return output.ToArray();
            }
        }
        static byte[] RunProcess(ProcessStartInfo start, int timeout, int outputLimit, int errorLimit, CancellationToken cancellation
#if PREPARATION_TESTS
            , Action<int> started
#endif
        )
        {
            cancellation.ThrowIfCancellationRequested();
            using (var process = new Process { StartInfo = start })
            {
                if (!process.Start()) throw new IOException("Approved helper did not start");
                Task<byte[]> output = null, error = null;
                try
                {
                    var clock = Stopwatch.StartNew();
                    output = Task.Run(() => ReadOutput(process.StandardOutput.BaseStream, outputLimit));
                    error = Task.Run(() => ReadOutput(process.StandardError.BaseStream, errorLimit));
                    process.StandardInput.Close();
#if PREPARATION_TESTS
                    if (started != null) started(process.Id);
#endif
                    while (true)
                    {
                        cancellation.ThrowIfCancellationRequested();
                        if (output.IsFaulted) throw output.Exception;
                        if (error.IsFaulted) throw error.Exception;
                        if (clock.ElapsedMilliseconds >= timeout) throw new TimeoutException("Approved helper timed out");
                        if (process.WaitForExit(25) && output.IsCompleted && error.IsCompleted) break;
                    }
                    cancellation.ThrowIfCancellationRequested();
                    // Accessing Result also observes faults that raced with IsCompleted.
                    byte[] bytes = output.Result, diagnostic = error.Result;
                    if (process.ExitCode != 0) throw new IOException("Approved helper failed with exit code " + process.ExitCode);
                    if (diagnostic.Length != 0) throw new IOException("Unexpected helper stderr");
                    return bytes;
                }
                catch (Exception failure)
                {
                    var failures = new List<Exception> { failure };
                    bool stopped = false;
                    try
                    {
                        if (!process.HasExited) process.Kill();
                        stopped = process.WaitForExit(5000);
                    }
                    catch (Exception cleanup) { failures.Add(cleanup); }
                    if (!stopped)
                        throw new AggregateException("Helper stop unconfirmed; retain all staged trees, never publish", failures);
                    // The trusted helper has no children. Await EOF readers after confirmed exit.
                    var streams = new List<Task>();
                    if (output != null) streams.Add(output);
                    if (error != null) streams.Add(error);
                    try
                    {
                        if (!Task.WaitAll(streams.ToArray(), 5000))
                            failures.Add(new IOException("Helper stream shutdown unconfirmed; retain staged trees"));
                    }
                    catch (AggregateException) { /* Read failures are observed; original error retained. */ }
                    if (failures.Count > 1) throw new AggregateException("Preparation failed with cleanup errors; never publish", failures);
                    throw;
                }
            }
        }
#if PREPARATION_TESTS
        internal static byte[] TestRun(ProcessStartInfo start, int timeout, int outputLimit, int errorLimit, CancellationToken cancellation, Action<int> started)
        { return RunProcess(start, timeout, outputLimit, errorLimit, cancellation, started); }
#endif
    }
}
