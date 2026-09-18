using System;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Collections.Generic;
using System.Diagnostics;
using System.Security.Cryptography;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
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
    [StructLayout(LayoutKind.Sequential)] struct FileInformation
    {
        internal uint Attributes, CreatedLow, CreatedHigh, AccessLow, AccessHigh, WriteLow, WriteHigh, Volume, SizeHigh, SizeLow, Links, IndexHigh, IndexLow;
    }
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern SafeFileHandle CreateFileW(string path, uint access, uint share, IntPtr security, uint creation, uint flags, IntPtr template);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool GetFileInformationByHandle(SafeFileHandle handle, out FileInformation info);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern bool CreateHardLinkW(string alias, string existing, IntPtr security);
    // Diagnostic only: unlike the production ownership gate, observe hardlink IDs
    // and link counts so the refusal itself, not the before-snapshot, is exercised.
    static string ObservedIdentity(string path)
    {
        using (var handle = CreateFileW(path, 0, 7, IntPtr.Zero, 3, 0x02200000, IntPtr.Zero))
        {
            if (handle.IsInvalid) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
            FileInformation info;
            if (!GetFileInformationByHandle(handle, out info)) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
            Check((info.Attributes & 0x400) == 0, "Reparse snapshot requires a separate no-follow fixture");
            return info.Volume + ":" + info.IndexHigh + ":" + info.IndexLow + ":" + info.CreatedHigh + ":" + info.CreatedLow + ":links=" + info.Links;
        }
    }
    static string[] Snapshot(string root)
    {
        return new[] { root }.Concat(Directory.GetFileSystemEntries(root, "*", SearchOption.AllDirectories)).OrderBy(p => p, StringComparer.Ordinal).Select(p =>
            p + "|" + ObservedIdentity(p) + "|" + (Directory.Exists(p) ? "directory" : Bootstrap.Hash(File.ReadAllBytes(p)))).ToArray();
    }
    static void Main(string[] args)
    {
        Check(typeof(StateStore).GetField("Fault", BindingFlags.NonPublic | BindingFlags.Static) == null, "Test fault leaked");
        Check(typeof(ReceiptCodec).GetMethod("TestEncode", BindingFlags.NonPublic | BindingFlags.Static) == null, "Raw receipt encoder leaked");
        Check(typeof(ReceiptCodec).GetMethod("TestDecode", BindingFlags.NonPublic | BindingFlags.Static) == null, "Raw receipt decoder leaked");
        Check(typeof(ReceiptCodec).GetMethod("TestDecodeRemaining", BindingFlags.NonPublic | BindingFlags.Static) == null, "Raw removal decoder leaked");
        if (Environment.OSVersion.Platform != PlatformID.Win32NT)
        {
            Refuse(() => StateStore.LoadRemaining("/unsupported-component", "/unsupported"), "native Windows Framework");
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
                {
                    using (var output = zip.CreateEntry("nested/owned.bin").Open()) output.Write(content, 0, content.Length);
                    using (var output = zip.CreateEntry("keeper.bin").Open()) output.Write(content, 0, content.Length);
                }
                archive = memory.ToArray();
            }
            var component = Bootstrap.Install(archive, Bootstrap.Hash(archive), new Dictionary<string, string> { { "nested/owned.bin", Bootstrap.Hash(content) }, { "keeper.bin", Bootstrap.Hash(content) } }, root);
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
            component = Bootstrap.Install(archive, Bootstrap.Hash(archive), new Dictionary<string, string> { { "nested/owned.bin", Bootstrap.Hash(content) }, { "keeper.bin", Bootstrap.Hash(content) } }, root);
            StateStore.Store(component, state); cipher = File.ReadAllBytes(file);
            File.Delete(installed);
            Refuse(() => StateStore.Load(root, state), "Missing installed content");
            var remainder = StateStore.LoadRemaining(root, state);
            string survivor = Path.Combine(root, "keeper.bin");
            File.WriteAllBytes(survivor, new byte[] { 9 });
            string[] beforeRefusal = Snapshot(temp);
            Refuse(() => StateStore.LoadRemaining(root, state), "Installed length changed");
            Check(Snapshot(temp).SequenceEqual(beforeRefusal), "Changed-length refusal altered inventory/identities/bytes");
            File.WriteAllBytes(survivor, content);
            string heldStateDirectory = Path.Combine(temp, "held-state-directory");
            Directory.Move(state, heldStateDirectory); Directory.CreateDirectory(state);
            File.Move(Path.Combine(heldStateDirectory, "receipt.bin"), file);
            beforeRefusal = Snapshot(temp);
            Refuse(() => StateStore.LoadRemaining(root, state), "Installed object replaced");
            Check(Snapshot(temp).SequenceEqual(beforeRefusal), "Replaced state directory refusal altered inventory/identities/bytes");
            File.Move(file, Path.Combine(heldStateDirectory, "receipt.bin")); Directory.Delete(state); Directory.Move(heldStateDirectory, state);
            string heldComponent = Path.Combine(temp, "held-component"); Directory.Move(root, heldComponent);
            beforeRefusal = Snapshot(temp);
            Refuse(() => StateStore.LoadRemaining(root, state));
            Check(Snapshot(temp).SequenceEqual(beforeRefusal), "Missing root refusal altered inventory/identities/bytes");
            Directory.Move(heldComponent, root);
            beforeRefusal = Snapshot(temp);
            using (var locked = new FileStream(survivor, FileMode.Open, FileAccess.Read, FileShare.None))
                Refuse(() => StateStore.LoadRemaining(root, state));
            Check(Snapshot(temp).SequenceEqual(beforeRefusal), "Read-sharing access refusal altered inventory/identities/bytes");
            foreach (string linked in new[] { survivor, file })
            {
                string alias = Path.Combine(temp, "outside-hardlink.bin");
                Check(CreateHardLinkW(alias, linked, IntPtr.Zero), "Native hardlink fixture creation failed: " + Marshal.GetLastWin32Error());
                try
                {
                    Check(ObservedIdentity(alias) == ObservedIdentity(linked) && ObservedIdentity(linked).EndsWith(":links=2", StringComparison.Ordinal), "Fixture is not the same original two-link object");
                    beforeRefusal = Snapshot(temp);
                    Refuse(() => StateStore.LoadRemaining(root, state), "hard-linked object refused");
                    Refuse(() => remainder.Remove(), "hard-linked object refused");
                    Check(Snapshot(temp).SequenceEqual(beforeRefusal), "Hardlink refusal changed either tree, original identity, aliases or bytes");
                }
                finally { File.Delete(alias); } // Only the alias explicitly created by this test.
                StateStore.LoadRemaining(root, state); // Original ownership remains valid when test alias is retired.
            }
            Console.WriteLine("PASS actual native runtime/state original hardlink refusals in LoadRemaining and stale Remove; whole inventory/native IDs/link counts/bytes unchanged, original ownership reverified after test alias retirement");
            foreach (string unknownRoot in new[] { root, state })
            {
                string unknown = Path.Combine(unknownRoot, "unknown"); File.WriteAllBytes(unknown, content);
                beforeRefusal = Snapshot(temp);
                Refuse(() => StateStore.LoadRemaining(root, state));
                Refuse(() => remainder.Remove());
                Check(Snapshot(temp).SequenceEqual(beforeRefusal), "Unknown-content recovery refusal altered complete inventory/identities/bytes");
                Check(Directory.Exists(Path.Combine(root, "nested")) && File.ReadAllBytes(unknown).SequenceEqual(content) && File.ReadAllBytes(file).SequenceEqual(cipher), "Recovery predelete refusal altered survivor/state");
                File.Delete(unknown);
            }
            bad = (byte[])cipher.Clone(); bad[bad.Length / 2] ^= 1; File.WriteAllBytes(file, bad);
            Refuse(() => StateStore.LoadRemaining(root, state));
            File.WriteAllText(file, "plaintext must not authorize recovery"); Refuse(() => StateStore.LoadRemaining(root, state));
            File.WriteAllBytes(file, cipher);
            File.Move(file, held); File.WriteAllBytes(file, cipher);
            Refuse(() => StateStore.LoadRemaining(root, state), "Installed object replaced");
            File.Delete(file); File.Move(held, file);
            Refuse(() => StateStore.LoadRemaining(root + "-other", state), "Receipt location binding mismatch");
            Directory.Move(state, moved);
            Refuse(() => StateStore.LoadRemaining(root, moved), "State location binding mismatch"); Directory.Move(moved, state);
            StateStore.LoadRemaining(root, state).Remove();
            Check(!Directory.Exists(root) && !Directory.Exists(state), "Authenticated missing-file recovery did not remove survivors");
            Console.WriteLine("PASS real DPAPI removal-only missing-file recovery; strict Load still refuses; unknown both-tree/stale-wrapper/corrupt/plaintext/replaced-state/root/location refusals preserve survivors");
            Console.WriteLine("PASS real Framework DPAPI state persistence/tamper/plaintext/cap/identity/location/root/changed component and unknown-state predelete refusal; not GUI/crash recovery/Windows11");
        }
        finally { Directory.Delete(temp, true); } // Only owned disposable test fixture.
    }
}
