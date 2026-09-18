// Native primitive evidence only. This is NOT a settings transaction or installer entry.
using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using Trojaino.Setup;

internal static class SettingsLockTests
{
    static void Assert(bool ok, string why) { if (!ok) throw new Exception("ASSERT: " + why); }
    static bool Sharing(IOException e) { return (e.HResult & 0xffff) == 32; }
    static int Child(string action, string path)
    {
        try
        {
            if (action == "write")
                using (var stream = new FileStream(path, FileMode.Open, FileAccess.ReadWrite, FileShare.ReadWrite | FileShare.Delete)) { stream.WriteByte(90); stream.Flush(true); }
            else if (action == "rename") File.Move(path, path + ".moved");
            else throw new InvalidOperationException("Unknown test child action");
            return 3; // A denied operation unexpectedly succeeded.
        }
        catch (IOException e) { if (!Sharing(e)) throw; Console.WriteLine("PASS child sharing denial: " + action); return 0; }
    }
    static void DeniedChild(string action, string path)
    {
        Assert(!path.Contains("\"") && !path.Contains("\r") && !path.Contains("\n"), "unsafe fixture transport");
        var info = new ProcessStartInfo(Assembly.GetExecutingAssembly().Location, "--child " + action + " \"" + path + "\"") {
            UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true
        };
        using (var process = Process.Start(info))
        {
            Assert(process != null, "test child did not start");
            if (!process.WaitForExit(15000))
            {
                process.Kill(); Assert(process.WaitForExit(5000), "test child stop unconfirmed; retain fixture");
                throw new Exception("Test child timed out; retain fixture");
            }
            string output = process.StandardOutput.ReadToEnd(), error = process.StandardError.ReadToEnd();
            Assert(process.ExitCode == 0 && output.Contains("PASS child sharing denial: " + action) && error == "", "child did not prove precise sharing refusal: " + output + error);
        }
    }
    static int Main(string[] args)
    {
        if (Environment.OSVersion.Platform != PlatformID.Win32NT)
        { Console.WriteLine("PASS settings lock harness unsupported-platform refusal; no native evidence"); return 0; }
        if (args.Length == 3 && args[0] == "--child") return Child(args[1], args[2]);
        Assert(args.Length == 0, "no external fixture arguments accepted by parent");
        string root = Path.Combine(Path.GetTempPath(), "trj-settings-lock-" + Guid.NewGuid().ToString("N"));
        var owner = Bootstrap.CreateEmpty(root);
        string path = Path.Combine(root, "settings.json"), replacement = Path.Combine(root, "replacement.json");
        bool passed = false;
        try
        {
            byte[] original = System.Text.Encoding.UTF8.GetBytes("{\"other\":1,\"enabledPlugins\":{}}");
            byte[] next = System.Text.Encoding.UTF8.GetBytes("{\"other\":2}");
            using (var output = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None)) output.Write(original, 0, original.Length);
            using (var output = new FileStream(replacement, FileMode.CreateNew, FileAccess.Write, FileShare.None)) output.Write(next, 0, next.Length);
            string identity = Bootstrap.Identity(path), replacementIdentity = Bootstrap.Identity(replacement);
            using (var held = new FileStream(path, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
            {
                DeniedChild("write", path); DeniedChild("rename", path);
                bool denied = false;
                try { File.Replace(replacement, path, null); } catch (IOException e) { if (!Sharing(e)) throw; denied = true; }
                Assert(denied, "own path replacement bypassed denied-delete handle");
                byte[] read = new byte[original.Length]; int count = held.Read(read, 0, read.Length);
                Assert(count == original.Length && held.Length == original.Length && read.SequenceEqual(original), "denied operations changed held bytes");
                Assert(Bootstrap.Identity(path) == identity && Bootstrap.Identity(replacement) == replacementIdentity, "denied operations changed native identities");
            }
            Assert(File.ReadAllBytes(path).SequenceEqual(original) && File.ReadAllBytes(replacement).SequenceEqual(next) && Directory.GetFileSystemEntries(root).Length == 2, "refusal changed whole primitive fixture");
            // Once the exclusive handle is closed an ordinary writer can open it.
            using (var available = new FileStream(path, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
                Assert(available.Length == original.Length, "released lock did not restore normal access");
            // Test-created files only; verify original identities/bytes before cleanup.
            Assert(Bootstrap.Identity(path) == identity && Bootstrap.Identity(replacement) == replacementIdentity, "fixture changed before cleanup");
            File.Delete(replacement); File.Delete(path); Bootstrap.Remove(owner); passed = true;
            Console.WriteLine("PASS native exclusive existing-settings handle blocks real child write/rename AND own path replacement, preserving both IDs/bytes; normal access after release; NOT publication/recovery evidence");
            return 0;
        }
        finally { if (!passed) Console.Error.WriteLine("RETAINED unsuccessful settings lock fixture: " + root); }
    }
}
