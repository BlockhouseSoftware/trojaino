using System;
using System.IO;
using System.Linq;
using System.Reflection;

internal static class LocationsTests
{
    static void Assert(bool ok, string why) { if (!ok) throw new Exception("ASSERT: " + why); }
    static Type Target()
    {
        var type = Assembly.GetExecutingAssembly().GetType("Trojaino.Setup.SetupLocations");
        Assert(type != null, "six-role controller prewrite validation missing");
        return type;
    }
    static void Layout(string[] roots, string name)
    {
        try { Target().GetMethod("ValidateLayout", BindingFlags.Static | BindingFlags.NonPublic).Invoke(null, new object[] {roots, name}); }
        catch (TargetInvocationException e) { throw e.InnerException; }
    }
    static void Refuse(string[] roots, string name)
    {
        bool refused = false;
        try { Layout(roots, name); } catch (InvalidDataException) { refused = true; }
        Assert(refused, "invalid six-role layout accepted");
    }
    static string[] Good(string parent)
    { return new[] {parent + @"\runtime", parent + @"\source", parent + @"\scratch", parent + @"\trojaino-local-trial", parent + @"\runtime-state", parent + @"\plugin-state"}; }
    static void Check(string[] roots, string name)
    {
        var method = Target().GetMethod("Check", BindingFlags.Static | BindingFlags.NonPublic);
        Assert(method != null, "native six-role all-destination preflight missing");
        try { method.Invoke(null, new object[] {roots, name}); }
        catch (TargetInvocationException e) { throw e.InnerException; }
    }
    static void Native()
    {
#if !NETFRAMEWORK
        bool refused = false;
        try { Check(null, null); } catch (PlatformNotSupportedException) { refused = true; }
        Assert(refused, "production Check must refuse unsupported framework BEFORE input/file probes");
        Console.WriteLine("PASS exact production non-Framework platform refusal; native checks not qualified");
#else
        if (Environment.OSVersion.Platform != PlatformID.Win32NT) throw new PlatformNotSupportedException();
        string parent = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "trojaino-locations-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(parent);
        try
        {
            var roots = Good(parent);
            Check(roots, "trojaino-local-trial");
            Assert(Directory.GetFileSystemEntries(parent).Length == 0, "successful native check wrote destinations");
            for (int role = 0; role < roots.Length; role++)
            {
                foreach (bool directory in new[] {false, true})
                {
                    if (directory) Directory.CreateDirectory(roots[role]); else File.WriteAllText(roots[role], "prior bytes");
                    bool rejected = false;
                    try { Check(roots, "trojaino-local-trial"); } catch (InvalidDataException) { rejected = true; }
                    Assert(rejected, "existing role accepted " + role);
                    Assert(Directory.GetFileSystemEntries(parent).Length == 1, "refusal wrote another role");
                    if (directory) { Assert(Directory.GetFileSystemEntries(roots[role]).Length == 0, "existing directory changed"); Directory.Delete(roots[role]); }
                    else { Assert(File.ReadAllText(roots[role]) == "prior bytes", "prior bytes changed"); File.Delete(roots[role]); }
                }
                var missing = (string[])roots.Clone();
                if (role <= 2) for (int sibling = 0; sibling <= 2; sibling++) missing[sibling] = Path.Combine(parent, "absent", Path.GetFileName(roots[sibling]));
                else missing[role] = Path.Combine(parent, "absent", Path.GetFileName(roots[role]));
                bool failed = false;
                try { Check(missing, "trojaino-local-trial"); }
                catch (IOException) { failed = true; }
                catch (InvalidDataException) { failed = true; }
                Assert(failed && Directory.GetFileSystemEntries(parent).Length == 0, "missing parent accepted/created");
            }
            Console.WriteLine("PASS native Framework all-six-role existing file/directory byte preservation, missing-parent no-write refusal and successful zero-write preflight; not GUI/Windows11");
        }
        finally { Directory.Delete(parent, true); }
#endif
    }
    static void Inventories()
    {
        using (var input = Assembly.GetExecutingAssembly().GetManifestResourceStream("Trojaino.Setup.Payload"))
        using (var outer = new System.IO.Compression.ZipArchive(input, System.IO.Compression.ZipArchiveMode.Read))
            foreach (string kind in new[] {"Runtime", "Source"})
            {
                var method = typeof(Trojaino.Setup.ApprovedPayload).GetMethod(kind + "Members", BindingFlags.Static | BindingFlags.NonPublic);
                var first = (string[])method.Invoke(null, null);
                using (var stream = outer.GetEntry(kind.ToLowerInvariant() + ".zip").Open())
                using (var memory = new MemoryStream())
                {
                    stream.CopyTo(memory); memory.Position = 0;
                    using (var nested = new System.IO.Compression.ZipArchive(memory, System.IO.Compression.ZipArchiveMode.Read))
                        Assert(first.SequenceEqual(nested.Entries.Select(e => e.FullName).OrderBy(x => x, StringComparer.Ordinal)), "compiled " + kind + " metadata differs from actual resource inventory");
                }
                first[0] = "mutated-by-test";
                Assert(((string[])method.Invoke(null, null))[0] != first[0], "mutable shared metadata");
            }
        Console.WriteLine("PASS actual embedded runtime/source ZIP inventories match fresh compiled path metadata; no payload execution");
    }
    static void Budgets(string[] roots)
    {
        foreach (int role in new[] {3, 4, 5})
        {
            string member = role == 3 ? ".claude-plugin/plugin.json" : "receipt.bin";
            string leaf = role == 3 ? "trojaino-local-trial" : "state";
            int padding = 247 - 1 - member.Length - 3 - 110 - 1 - 1 - leaf.Length;
            var boundary = (string[])roots.Clone();
            string parent = @"D:\" + new string('a', 110) + @"\" + new string('b', padding);
            boundary[role] = parent + @"\" + leaf;
            Layout(boundary, "trojaino-local-trial");
            boundary[role] = parent + @"b\" + leaf; Refuse(boundary, "trojaino-local-trial");
        }
        int runtime = Trojaino.Setup.ApprovedPayload.RuntimeMembers().Max(x => x.Length) + "runtime".Length;
        int source = Trojaino.Setup.ApprovedPayload.SourceMembers().Max(x => x.Length) + "source".Length;
        int parentLength = 247 - 2 - Math.Max(runtime, source);
        string staging = @"D:\" + new string('a', 70) + @"\" + new string('b', parentLength - 74);
        var staged = (string[])roots.Clone();
        staged[0] = staging + @"\runtime"; staged[1] = staging + @"\source"; staged[2] = staging + @"\scratch";
        Layout(staged, "trojaino-local-trial");
        staged[0] = staging + @"b\runtime"; staged[1] = staging + @"b\source"; staged[2] = staging + @"b\scratch";
        Refuse(staged, "trojaino-local-trial");
        Console.WriteLine("PASS exact compiled staging, plugin and both receipt-file path budget boundaries");
    }
    static int Main()
    {
        var roots = Good(@"C:\Users\Sig Å\AppData\Local\Trojaino");
        Layout(roots, "trojaino-local-trial");
        for (int i = 0; i < roots.Length; i++)
            for (int j = 0; j < roots.Length; j++)
            {
                if (i == j) continue;
                var changed = (string[])roots.Clone(); changed[j] = roots[i]; Refuse(changed, "trojaino-local-trial");
                changed[j] = roots[i] + @"\child"; Refuse(changed, "trojaino-local-trial");
                changed[j] = roots[i].ToUpperInvariant(); Refuse(changed, "trojaino-local-trial");
            }
        Refuse(null, "trojaino-local-trial");
        Refuse(roots.Take(5).ToArray(), "trojaino-local-trial");
        foreach (int role in new[] {1, 2})
        {
            var changed = (string[])roots.Clone(); changed[role] = @"C:\Other\separate"; Refuse(changed, "trojaino-local-trial");
        }
        foreach (string name in new[] {null, "", "trojaino", "trojaino-local-Trial", "trojaino-local-other", "trojaino-local-trial\n"}) Refuse(roots, name);
        foreach (string path in new[] {null, "", @"relative", @"C:\x\..\runtime", @"C:\x\runtime\", @"C:\x\NUL", @"C:\x\with. ", "C:\\x\\new\nline"})
        {
            var changed = (string[])roots.Clone(); changed[4] = path; Refuse(changed, "trojaino-local-trial");
        }
        var budget = (string[])roots.Clone();
        int wanted = 247 - 1 - "receipt.bin".Length;
        budget[4] = @"D:\" + new string('a', 110) + @"\" + new string('b', wanted - 114);
        Layout(budget, "trojaino-local-trial");
        budget[4] += "b"; Refuse(budget, "trojaino-local-trial");
        Console.WriteLine("PASS exact accepted/refused state member path budget");
        Console.WriteLine("PASS pure six-role Windows layout, all directed cross-role equality/ancestor/case aliases, sibling/name/path refusal; no writes or native qualification");
        Inventories(); Budgets(roots); Native();
        return 0;
    }
}
