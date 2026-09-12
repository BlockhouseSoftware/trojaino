using System;
using System.IO;
using System.IO.Compression;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using Trojaino.Setup;
class Program
{
    static void Check(bool ok, string why) { if (!ok) throw new Exception(why); }
    static void Refuse(Action action)
    {
        try { action(); }
        catch (Exception e) { if (e is IOException || e is InvalidDataException || e is PlatformNotSupportedException || e is System.Security.Cryptography.CryptographicException || e is System.ComponentModel.Win32Exception) return; throw; }
        throw new Exception("Unsafe pair operation accepted");
    }
    static void PlatformRefuse(Action action)
    {
        try { action(); }
        catch (PlatformNotSupportedException) { return; }
        throw new Exception("Expected specific native-platform refusal");
    }
    static Bootstrap.Receipt Component(string root)
    {
        byte[] bytes = new byte[] { 1, 2, 3, 4 }, archive;
        using (var memory = new MemoryStream())
        {
            using (var zip = new ZipArchive(memory, ZipArchiveMode.Create, true))
            using (var output = zip.CreateEntry("nested/owned.bin").Open()) output.Write(bytes, 0, bytes.Length);
            archive = memory.ToArray();
        }
        return Bootstrap.Install(archive, Bootstrap.Hash(archive), new Dictionary<string, string> { { "nested/owned.bin", Bootstrap.Hash(bytes) } }, root);
    }
    static void Main(string[] args)
    {
        Check(typeof(StateStore).GetField("Fault", BindingFlags.NonPublic | BindingFlags.Static) == null, "Test fault leaked");
        Check(typeof(ReceiptCodec).GetMethod("TestEncode", BindingFlags.NonPublic | BindingFlags.Static) == null, "Raw encoder leaked");
        Check(typeof(ReceiptCodec).GetMethod("TestDecode", BindingFlags.NonPublic | BindingFlags.Static) == null, "Raw decoder leaked");
        if (args.Length == 5 && args[0] == "--reload-remove")
        {
            PairState.Remove(PairState.Load(args[1], args[2], args[3], args[4]));
            foreach (string path in args.Skip(1)) Check(!Directory.Exists(path), "Fresh-process removal incomplete");
            return;
        }
        Check(args.Length == 0, "Unexpected harness arguments");
        string temp = Path.Combine(Environment.OSVersion.Platform == PlatformID.Win32NT ? Path.GetTempPath() : "/private/tmp", "trojaino-pair-native-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(temp);
        try
        {
            string runtime = Path.Combine(temp, "runtime"), plugin = Path.Combine(temp, "plugin"), rs = Path.Combine(temp, "runtime-state"), ps = Path.Combine(temp, "plugin-state");
            var r = Component(runtime); var p = Component(plugin);
            if (Environment.OSVersion.Platform != PlatformID.Win32NT)
            {
                PlatformRefuse(() => PairState.Save(r, p, rs, ps));
                PlatformRefuse(() => PairState.Load(runtime, plugin, rs, ps));
                Bootstrap.Verify(r); Bootstrap.Verify(p);
                Check(!Directory.Exists(rs) && !Directory.Exists(ps), "Unsupported production wrote state");
                Console.WriteLine("PASS production Pair Save/Load refuse off native Windows Framework; SKIP real DPAPI"); return;
            }
            Refuse(() => PairState.Save(r, p, rs, rs.ToUpperInvariant()));
            Check(!Directory.Exists(rs), "Case-alias roots wrote state");
            Directory.CreateDirectory(ps); File.WriteAllText(Path.Combine(ps, "prior"), "retain");
            Refuse(() => PairState.Save(r, p, rs, ps));
            Check(!Directory.Exists(rs) && File.ReadAllText(Path.Combine(ps, "prior")) == "retain", "Native partial pair save rollback failed");
            Bootstrap.Verify(r); Bootstrap.Verify(p); Directory.Delete(ps, true);
            var saved = PairState.Save(r, p, rs, ps);
            byte[] rb = File.ReadAllBytes(Path.Combine(rs, "receipt.bin")), pb = File.ReadAllBytes(Path.Combine(ps, "receipt.bin"));
            Refuse(() => PairState.Load(runtime, runtime, rs, rs));
            foreach (string tree in new[] { runtime, plugin, rs, ps })
            {
                string unknown = Path.Combine(tree, "unknown"); File.WriteAllText(unknown, "retain");
                Refuse(() => PairState.Load(runtime, plugin, rs, ps)); Refuse(() => PairState.Remove(saved));
                Check(File.ReadAllText(unknown) == "retain" && File.ReadAllBytes(Path.Combine(rs, "receipt.bin")).SequenceEqual(rb)
                    && File.ReadAllBytes(Path.Combine(ps, "receipt.bin")).SequenceEqual(pb), "Native predelete refusal changed state");
                File.Delete(unknown); Bootstrap.Verify(r); Bootstrap.Verify(p);
            }
            string self = Process.GetCurrentProcess().MainModule.FileName;
            string[] paths = new[] { runtime, plugin, rs, ps };
            Check(paths.All(x => !x.Contains("\"")), "Unsafe fixture argument");
            var start = new ProcessStartInfo { FileName = self, Arguments = "--reload-remove " + string.Join(" ", paths.Select(x => "\"" + x + "\"")), UseShellExecute = false, CreateNoWindow = true };
            using (var child = Process.Start(start))
            {
                if (!child.WaitForExit(30000)) { child.Kill(); child.WaitForExit(); throw new TimeoutException("Native pair child timed out"); }
                Check(child.ExitCode == 0, "Native pair child failed");
            }
            foreach (string path in paths) Check(!Directory.Exists(path), "Native pair removal incomplete");
            Console.WriteLine("PASS actual Framework DPAPI pair Save and fresh-process Load/Remove, alias/predelete all-four-tree refusal and second-state failure rollback; not GUI/crash recovery/Windows11");
        }
        finally { Directory.Delete(temp, true); } // Disposable owned harness fixture only.
    }
}
