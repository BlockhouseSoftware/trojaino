// Real compiled-resource staging exercise; never run Python or candidate files.
using System;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using Trojaino.Setup;

internal static class ResourceTests
{
    static void Assert(bool ok, string message) { if (!ok) throw new Exception(message); }
    static void Compare(string archiveName, string destination)
    {
        using (var resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("Trojaino.Setup.Payload"))
        using (var outer = new ZipArchive(resource, ZipArchiveMode.Read))
        using (var nested = outer.GetEntry(archiveName).Open())
        using (var memory = new MemoryStream())
        {
            nested.CopyTo(memory); memory.Position = 0;
            using (var zip = new ZipArchive(memory, ZipArchiveMode.Read))
            {
                Assert(Directory.GetFiles(destination, "*", SearchOption.AllDirectories).Length == zip.Entries.Count, "exact inventory");
                foreach (var entry in zip.Entries)
                    using (var input = entry.Open())
                    using (var expected = new MemoryStream())
                    {
                        input.CopyTo(expected);
                        Assert(File.ReadAllBytes(Path.Combine(destination, entry.FullName)).SequenceEqual(expected.ToArray()), "bytes differ: " + entry.FullName);
                    }
                Console.WriteLine("PASS " + archiveName + ": " + zip.Entries.Count + " files independently compared byte-for-byte, NOT EXECUTED");
            }
        }
    }
    static int Main(string[] args)
    {
        string parent = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "trojaino-resource-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(parent);
        try
        {
            string runtime = Path.Combine(parent, "runtime"), source = Path.Combine(parent, "source");
            if (args.Length == 1 && args[0] == "--expect-tamper")
            {
                bool denied = false;
                try { ApprovedPayload.StageRuntime(runtime); }
                catch (InvalidDataException e) { denied = e.Message == "Embedded payload digest mismatch"; }
                Assert(denied && !Directory.Exists(runtime), "tampered compiled resource must fail before writes");
                Console.WriteLine("PASS tampered compiled resource denied by compiled digest before writes");
                return 0;
            }
            Assert(args.Length == 0, "unexpected developer arguments");
            var r = ApprovedPayload.StageRuntime(runtime);
            var s = ApprovedPayload.StageSource(source);
            Compare("runtime.zip", runtime); Compare("source.zip", source);
            Bootstrap.Verify(r); Bootstrap.Verify(s);
            Bootstrap.Remove(s); Bootstrap.Remove(r);
            Assert(!Directory.Exists(runtime) && !Directory.Exists(source), "owned removal");
            Console.WriteLine("PASS compiled approved payload " + ApprovedPayload.PayloadSha256 + ": staging, Verify, Remove; no test callbacks compiled");
            return 0;
        }
        catch (Exception e) { Console.WriteLine("FAIL " + e); return 1; }
        finally { Directory.Delete(parent, true); } // Test-created disposable root only.
    }
}
