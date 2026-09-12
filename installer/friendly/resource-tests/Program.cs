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
    static object Transaction(string method, params object[] args)
    {
        var type = Assembly.GetExecutingAssembly().GetType("Trojaino.Setup.StagedPayload");
        Assert(type != null, "missing authenticated pair staging transaction");
        var member = type.GetMethod(method, BindingFlags.Static | BindingFlags.NonPublic);
        Assert(member != null, "missing transaction method: " + method);
        try { return member.Invoke(null, args); }
        catch (TargetInvocationException e) { throw e.InnerException; }
    }
    static void SourceRefusalRollsBackRuntime(string parent)
    {
        string runtime = Path.Combine(parent, "pair-runtime"), source = Path.Combine(parent, "pair-source");
        Directory.CreateDirectory(source);
        File.WriteAllText(Path.Combine(source, "keep.txt"), "prior user bytes");
        bool denied = false;
        try { Transaction("Install", runtime, source); }
        catch (System.ComponentModel.Win32Exception) { denied = true; }
        Assert(denied, "second-stage existing source refusal reported");
        Assert(!Directory.Exists(runtime), "first-stage owned runtime rolled back");
        Assert(Directory.GetFileSystemEntries(source).Length == 1 && File.ReadAllText(Path.Combine(source, "keep.txt")) == "prior user bytes", "existing source entirely preserved");
        File.Delete(Path.Combine(source, "keep.txt")); Directory.Delete(source);
        Console.WriteLine("PASS pair transaction: existing source refused, runtime rollback, prior bytes preserved");
    }
    static void PairLifecycle(string parent)
    {
        string runtime = Path.Combine(parent, "pair-runtime"), source = Path.Combine(parent, "pair-source");
        var pair = Transaction("Install", runtime, source);
        Compare("runtime.zip", runtime); Compare("source.zip", source);
        Transaction("Verify", pair);
        string intruder = Path.Combine(runtime, "unknown.txt");
        File.WriteAllText(intruder, "retain everything");
        bool denied = false;
        try { Transaction("Remove", pair); } catch (InvalidDataException) { denied = true; }
        Assert(denied, "changed runtime refused");
        Compare("source.zip", source); // Must not remove the otherwise valid source first.
        Assert(File.ReadAllText(intruder) == "retain everything", "unknown content preserved");
        File.Delete(intruder);
        Transaction("Verify", pair); Transaction("Remove", pair);
        Assert(!Directory.Exists(runtime) && !Directory.Exists(source), "both unchanged owned trees removed");
        Console.WriteLine("PASS pair lifecycle: full predelete validation across both trees, Verify/Remove");
    }
    static void PairDestinationsMustBeDistinctSiblings(string parent)
    {
        string runtime = Path.Combine(parent, "pair-runtime");
        foreach (string source in new[] { Path.Combine(runtime, "source"), runtime, runtime.ToUpperInvariant(), Path.Combine(parent, "absent-parent", "source") })
        {
            bool denied = false;
            try { Transaction("Install", runtime, source); } catch (InvalidDataException) { denied = true; }
            Assert(denied && !Directory.Exists(runtime), "overlapping/non-sibling destinations refused before writing: " + source);
        }
        Console.WriteLine("PASS pair destinations: nested, identical, case alias and non-sibling refused before writes");
    }
    static void NestedMemberReceipt(string parent)
    {
        // Small native regression: ZIP separators are not filesystem separators.
        string destination = Path.Combine(parent, "nested-receipt");
        byte[] archive;
        using (var memory = new MemoryStream())
        {
            using (var zip = new ZipArchive(memory, ZipArchiveMode.Create, true))
            {
                var entry = zip.CreateEntry("first/second/file.txt");
                entry.ExternalAttributes = 0x1800000;
                using (var output = entry.Open()) output.WriteByte(42);
            }
            archive = memory.ToArray();
        }
        var pins = new System.Collections.Generic.Dictionary<string, string> {
            { "first/second/file.txt", Bootstrap.Hash(new byte[] {42}) }
        };
        var receipt = Bootstrap.Install(archive, Bootstrap.Hash(archive), pins, destination);
        string expected = Path.Combine(destination, "first", "second", "file.txt");
        Assert(receipt.Hashes.ContainsKey(expected), "receipt must use native component spelling");
        Assert(File.ReadAllBytes(expected).SequenceEqual(new byte[] {42}), "nested fixture bytes preserved");
        Bootstrap.Verify(receipt); Bootstrap.Remove(receipt);
        Assert(!Directory.Exists(destination), "nested receipt can Verify and Remove");
        Console.WriteLine("PASS nested ZIP member: native receipt spelling, exact bytes, Verify/Remove");
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
            NestedMemberReceipt(parent);
            SourceRefusalRollsBackRuntime(parent);
            PairLifecycle(parent);
            PairDestinationsMustBeDistinctSiblings(parent);
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
