using System;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Diagnostics;
using System.Threading;
using Trojaino.Setup;

internal static class ControllerNativeTests
{
    static void Assert(bool ok, string why) { if (!ok) throw new Exception(why); }
    static void Refuse(Action action)
    {
        try { action(); }
        catch (InvalidDataException) { return; }
        throw new Exception("Unsafe controller operation accepted");
    }
    static void RuntimeBytes(string root)
    {
        using (var resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("Trojaino.Setup.Payload"))
        using (var outer = new ZipArchive(resource, ZipArchiveMode.Read))
        using (var nested = outer.GetEntry("runtime.zip").Open())
        using (var memory = new MemoryStream())
        {
            nested.CopyTo(memory); memory.Position = 0;
            using (var zip = new ZipArchive(memory, ZipArchiveMode.Read))
            {
                Assert(Directory.GetFiles(root, "*", SearchOption.AllDirectories).Length == zip.Entries.Count, "runtime whole inventory");
                foreach (var entry in zip.Entries)
                    using (var input = entry.Open()) using (var expected = new MemoryStream())
                    { input.CopyTo(expected); Assert(File.ReadAllBytes(Path.Combine(root, entry.FullName)).SequenceEqual(expected.ToArray()), "runtime byte equality"); }
            }
        }
    }
    static int Main(string[] args)
    {
        try
        {
            Assert(typeof(SetupController).GetMethod("TestInstall", BindingFlags.NonPublic | BindingFlags.Static) == null, "test controller injection leaked");
            Assert(typeof(SetupController).GetMethod("Core", BindingFlags.NonPublic | BindingFlags.Static).GetParameters().Length == 3, "production callback parameter leaked");
            Assert(typeof(TrustedPreparation).GetMethod("TestPublish", BindingFlags.NonPublic | BindingFlags.Static) == null, "test raw publication leaked");
            Assert(typeof(ReceiptCodec).GetMethod("TestDecode", BindingFlags.NonPublic | BindingFlags.Static) == null, "raw state codec leaked");
#if !NETFRAMEWORK
            bool refused = false;
            try { SetupController.Install(null, null, CancellationToken.None); }
            catch (PlatformNotSupportedException) { refused = true; }
            Assert(refused, "exact production platform-first refusal");
            Console.WriteLine("PASS production controller test seams absent; exact non-Framework refusal; native execution NOT qualified");
            return 0;
#else
            if (args.Length == 5 && args[0] == "--reload-remove")
            {
                PairState.Remove(PairState.Load(args[1], args[2], args[3], args[4]));
                Assert(args.Skip(1).All(r => !Directory.Exists(r)), "fresh process cleanup");
                return 0;
            }
            Assert(args.Length == 0, "unexpected arguments");
            string parent = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "tj-controller-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(parent);
            try
            {
                string name = "trojaino-local-controller-native";
                string[] roots = new[] {"runtime", "source", "scratch", name, "runtime-state", "plugin-state"}.Select(n => Path.Combine(parent, n)).ToArray();
                for (int i = 0; i < 6; i++)
                {
                    File.WriteAllText(roots[i], "prior");
                    Refuse(() => SetupController.Install(roots, name, CancellationToken.None));
                    Assert(File.ReadAllText(roots[i]) == "prior" && Directory.GetFileSystemEntries(parent).Length == 1, "whole gate preserves prior and creates nothing");
                    File.Delete(roots[i]);
                }
                var alias = (string[])roots.Clone(); alias[5] = alias[0];
                Refuse(() => SetupController.Install(alias, name, CancellationToken.None));
                Assert(Directory.GetFileSystemEntries(parent).Length == 0, "overlap zero writes");
                var pair = SetupController.Install(roots, name, CancellationToken.None);
                PairState.Verify(pair);
                Assert(!Directory.Exists(roots[1]) && !Directory.Exists(roots[2]), "transient source and scratch retired");
                RuntimeBytes(roots[0]);
                var json = new System.Web.Script.Serialization.JavaScriptSerializer { MaxJsonLength = 16 * 1024 * 1024 };
                var manifest = json.Deserialize<System.Collections.Generic.Dictionary<string,string>>(File.ReadAllText(Path.Combine(roots[3], "MANIFEST.sha256.json")));
                Assert(Directory.GetFiles(roots[3], "*", SearchOption.AllDirectories).Length == manifest.Count + 1, "plugin entire inventory");
                foreach (var pin in manifest) Assert(Bootstrap.Hash(File.ReadAllBytes(Path.Combine(roots[3], pin.Key))) == pin.Value, "every plugin digest");
                var meta = json.Deserialize<System.Collections.Generic.Dictionary<string,object>>(File.ReadAllText(Path.Combine(roots[3], ".claude-plugin", "plugin.json")));
                Assert((string)meta["name"] == name && (bool)meta["defaultEnabled"] == false, "default-disabled identity, not explicit setting override proof");
                string python = Path.Combine(roots[0], "python.exe"), entry = Path.Combine(roots[3], "scripts", "preflight.py");
                string hook = File.ReadAllText(Path.Combine(roots[3], "hooks", "hooks.json"));
                Assert(hook.Contains(json.Serialize(python)) && hook.Contains(json.Serialize(entry)), "literal final hooks");
                Assert(entry.IndexOf('\'') < 0 && python.IndexOf('\'') < 0, "quote-free fixture");
                string binding = "_EXPECTED_BINDING = ('" + entry.Replace("\\", "\\\\") + "', '" + python.Replace("\\", "\\\\") + "')";
                Assert(File.ReadAllLines(entry).Single(l => l.StartsWith("_EXPECTED_BINDING = ", StringComparison.Ordinal)) == binding, "sealed lifetime binding");
                Refuse(() => SetupController.Install(roots, name, CancellationToken.None));
                PairState.Verify(pair); RuntimeBytes(roots[0]);
                string self = Process.GetCurrentProcess().MainModule.FileName;
                string[] paths = new[] {roots[0], roots[3], roots[4], roots[5]};
                Assert(paths.All(p => !p.Contains("\"") && !p.EndsWith("\\")), "safe fixture arguments");
                using (var child = Process.Start(new ProcessStartInfo { FileName = self, UseShellExecute = false, CreateNoWindow = true,
                    Arguments = "--reload-remove " + string.Join(" ", paths.Select(p => "\"" + p + "\"")) }))
                {
                    if (!child.WaitForExit(30000)) { child.Kill(); child.WaitForExit(5000); throw new TimeoutException("fixture child timed out"); }
                    Assert(child.ExitCode == 0, "fresh process remove failed");
                }
                Assert(roots.All(r => !Directory.Exists(r)), "all controller roots removed");
                Console.WriteLine("PASS native Framework whole transaction: approved CPython executed; complete runtime bytes/plugin hashes/literal binding/default-disabled identity; DPAPI fresh-process Load/Remove; no GUI, Claude activation or Windows11 qualification");
            }
            finally { Directory.Delete(parent, true); } // Disposable developer fixture only.
            return 0;
#endif
        }
        catch (Exception e) { Console.WriteLine("FAIL " + e); return 1; }
    }
}
