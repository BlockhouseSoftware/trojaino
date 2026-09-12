using System;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Collections.Generic;
using System.Diagnostics;
using System.Security.Cryptography;
using Trojaino.Setup;
class Program
{
    static void Check(bool value, string why) { if (!value) throw new Exception(why); }
    static void Refuse(Action action, string reason = null)
    {
        try { action(); }
        catch (Exception e)
        {
            if (!(e is IOException || e is InvalidDataException || e is CryptographicException || e is PlatformNotSupportedException || e is System.ComponentModel.Win32Exception)) throw;
            if (reason != null) Check(e.Message.Contains(reason), "Wrong refusal: " + e.Message);
            return;
        }
        throw new Exception("Unsafe production state operation accepted");
    }
    static void Main(string[] args)
    {
        Check(typeof(StateStore).GetField("Fault", BindingFlags.NonPublic | BindingFlags.Static) == null, "Test fault leaked");
        Check(typeof(ReceiptCodec).GetMethod("TestEncode", BindingFlags.NonPublic | BindingFlags.Static) == null, "Raw receipt encoder leaked");
        Check(typeof(ReceiptCodec).GetMethod("TestDecode", BindingFlags.NonPublic | BindingFlags.Static) == null, "Raw receipt decoder leaked");
        if (Environment.OSVersion.Platform != PlatformID.Win32NT)
        {
            Refuse(() => StateStore.Store(null, "/unsupported"), "native Windows Framework");
            Refuse(() => StateStore.Load("/unsupported-component", "/unsupported"), "native Windows Framework");
            Refuse(() => StateStore.Remove(null), "native Windows Framework");
            Console.WriteLine("PASS production Store/Load/Remove refuse off Windows Framework; SKIP actual DPAPI persistence"); return;
        }
        if (args.Length == 3 && args[0] == "--reload-remove")
        {
            var loaded = StateStore.Load(args[1], args[2]);
            StateStore.Remove(loaded);
            Check(!Directory.Exists(args[1]) && !Directory.Exists(args[2]), "Child removal incomplete");
            Console.WriteLine("PASS fresh-process DPAPI Load and complete owned component+state Remove"); return;
        }
        Check(args.Length == 0, "Unexpected harness arguments");
        string temp = Path.Combine(Path.GetTempPath(), "trojaino-state-native-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(temp);
        try
        {
            string root = Path.Combine(temp, "component"), state = Path.Combine(temp, "state"), file = Path.Combine(state, "receipt.bin");
            byte[] content = new byte[] { 1, 2, 3, 4 }, archive;
            using (var memory = new MemoryStream())
            {
                using (var zip = new ZipArchive(memory, ZipArchiveMode.Create, true))
                using (var output = zip.CreateEntry("nested/owned.bin").Open()) output.Write(content, 0, content.Length);
                archive = memory.ToArray();
            }
            var component = Bootstrap.Install(archive, Bootstrap.Hash(archive), new Dictionary<string, string> { { "nested/owned.bin", Bootstrap.Hash(content) } }, root);
            string tooLongState = Path.Combine(temp, "boundary").PadRight(248 - 1 - "receipt.bin".Length, 'a');
            Refuse(() => StateStore.Store(component, tooLongState), "Installed member exceeds");
            Check(!Directory.Exists(tooLongState), "State member budget refused after creation");
            var saved = StateStore.Store(component, state);
            byte[] cipher = File.ReadAllBytes(file);
            Check(cipher.Length > 0, "No persisted ciphertext");
            Refuse(() => StateStore.Store(component, state));
            Check(File.ReadAllBytes(file).SequenceEqual(cipher), "Existing state overwritten");
            byte[] bad = (byte[])cipher.Clone(); bad[bad.Length / 2] ^= 1;
            File.WriteAllBytes(file, bad);
            Refuse(() => StateStore.Load(root, state));
            File.WriteAllText(file, "plaintext must never authorize removal");
            Refuse(() => StateStore.Load(root, state));
            File.WriteAllBytes(file, cipher);
            string held = Path.Combine(temp, "held.bin");
            File.Move(file, held); File.WriteAllBytes(file, cipher);
            Refuse(() => StateStore.Load(root, state), "Installed object replaced");
            File.Delete(file); File.Move(held, file);
            File.WriteAllText(Path.Combine(state, "unknown"), "retain");
            Refuse(() => StateStore.Load(root, state), "Unknown installed content");
            Refuse(() => StateStore.Remove(saved), "Unknown installed content");
            Bootstrap.Verify(component);
            Check(File.ReadAllBytes(file).SequenceEqual(cipher), "Predelete refusal changed state");
            File.Delete(Path.Combine(state, "unknown"));
            Refuse(() => StateStore.Load(root + "-other", state), "Receipt location binding mismatch");
            string moved = Path.Combine(temp, "moved"); Directory.Move(state, moved);
            Refuse(() => StateStore.Load(root, moved), "State location binding mismatch"); Directory.Move(moved, state);
            using (var output = new FileStream(file, FileMode.Open, FileAccess.Write)) output.SetLength(3 * 1024 * 1024 + 1);
            Refuse(() => StateStore.Load(root, state), "State ciphertext budget exceeded"); File.WriteAllBytes(file, cipher);
            string installed = Path.Combine(root, "nested", "owned.bin");
            File.WriteAllBytes(installed, new byte[] { 4, 3, 2, 1 });
            Refuse(() => StateStore.Load(root, state), "Installed bytes changed"); File.WriteAllBytes(installed, content);
            // Trusted test's own compiled executable, not a candidate or PATH lookup.
            string self = Process.GetCurrentProcess().MainModule.FileName;
            Check(!root.Contains("\"") && !state.Contains("\""), "Unsafe fixture path");
            var start = new ProcessStartInfo { FileName = self, Arguments = "--reload-remove \"" + root + "\" \"" + state + "\"", UseShellExecute = false, CreateNoWindow = true };
            using (var child = Process.Start(start))
            {
                if (!child.WaitForExit(30000)) { child.Kill(); child.WaitForExit(); throw new TimeoutException("Native state child timed out"); }
                Check(child.ExitCode == 0, "Native state child failed");
            }
            Check(!Directory.Exists(root) && !Directory.Exists(state), "Fresh-process persistent removal failed");
            Console.WriteLine("PASS real Framework DPAPI state persistence/tamper/plaintext/cap/identity/location/root/changed component and unknown-state predelete refusal; not GUI/crash recovery/Windows11");
        }
        finally { Directory.Delete(temp, true); } // Only owned disposable test fixture.
    }
}
