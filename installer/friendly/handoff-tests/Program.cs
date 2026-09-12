// Actual authenticated payload bytes, never execute the staged runtime or source.
using System;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using Trojaino.Setup;

internal static class HandoffTests
{
    static void Assert(bool ok, string why) { if (!ok) throw new Exception(why); }
    static object Call(string method, StagedPayload staged)
    {
        var entry = typeof(StagedPayload).GetMethod(method, BindingFlags.Static | BindingFlags.NonPublic);
        Assert(entry != null, "Missing runtime lifetime bridge: " + method);
        try { return entry.Invoke(null, new object[] { staged }); }
        catch (TargetInvocationException e) { throw e.InnerException; }
    }
    static void Denied(Action action)
    {
        bool refused = false;
        try { action(); } catch (InvalidDataException) { refused = true; }
        Assert(refused, "Expected integrity refusal");
    }
    static void CompareRuntime(string root)
    {
        using (var resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("Trojaino.Setup.Payload"))
        using (var outer = new ZipArchive(resource, ZipArchiveMode.Read))
        using (var input = outer.GetEntry("runtime.zip").Open())
        using (var copy = new MemoryStream())
        {
            input.CopyTo(copy); copy.Position = 0;
            using (var inner = new ZipArchive(copy, ZipArchiveMode.Read))
            {
                Assert(Directory.GetFiles(root, "*", SearchOption.AllDirectories).Length == inner.Entries.Count, "Runtime inventory changed");
                foreach (var entry in inner.Entries)
                    using (var bytes = entry.Open())
                    using (var expected = new MemoryStream())
                    {
                        bytes.CopyTo(expected);
                        Assert(File.ReadAllBytes(Path.Combine(root, entry.FullName)).SequenceEqual(expected.ToArray()), "Runtime bytes changed: " + entry.FullName);
                    }
            }
        }
    }
    static int Main()
    {
        string parent = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "trojaino-handoff-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(parent);
        try
        {
            string runtime = Path.Combine(parent, "runtime"), source = Path.Combine(parent, "source");
            var staged = StagedPayload.Install(runtime, source);
            var owned = (Bootstrap.Receipt)Call("CaptureRuntime", staged);
            Assert(owned.Root == runtime, "Runtime binding relocated");
            // Both unknown-tree directions refuse before deleting source.
            foreach (string root in new[] { runtime, source })
            {
                string unknown = Path.Combine(root, "unknown.txt"); File.WriteAllText(unknown, "retain unknown");
                Denied(() => Call("CaptureRuntime", staged));
                Denied(() => Call("RemoveSource", staged));
                Assert(File.ReadAllText(unknown) == "retain unknown" && Directory.Exists(source) && Directory.Exists(runtime), "Unverified tree deleted");
                File.Delete(unknown);
                StagedPayload.Verify(staged); // Every original identity, inventory and byte preserved.
            }
            Call("RemoveSource", staged);
            Assert(!Directory.Exists(source), "Reviewed source not retired");
            Bootstrap.Verify(owned); CompareRuntime(runtime);
            // No disk-tree reconstruction: pair cannot be captured after source removal.
            bool refused = false;
            try { Call("CaptureRuntime", staged); } catch (IOException) { refused = true; }
            Assert(refused, "Retired pair unexpectedly adopted");
            Bootstrap.Remove(owned);
            Assert(!Directory.Exists(runtime), "Captured original runtime receipt cannot remove");
            Console.WriteLine("PASS captured original runtime ownership, both unknown-tree predelete refusals, source-only retirement, EVERY runtime byte preserved, original runtime Verify/Remove; no execution");
            return 0;
        }
        catch (Exception e) { Console.WriteLine("FAIL " + e); return 1; }
        finally { Directory.Delete(parent, true); } // Disposable test-created parent only.
    }
}
