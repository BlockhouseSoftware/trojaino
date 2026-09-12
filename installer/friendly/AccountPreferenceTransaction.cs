// Existing-file account edit. Retains original recovery evidence; not atomic,
// power-loss qualification, effective Claude protection, or recovery resolution.
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace Trojaino.Setup
{
    internal static class AccountPreferenceTransaction
    {
        const int MaxDocument = 1024 * 1024, MaxCipher = 3 * 1024 * 1024;
        const string Purpose = "Trojaino.Setup.AccountPreference.Prepared.v1";
        static readonly UTF8Encoding Utf8 = new UTF8Encoding(false, true);
#if ACCOUNT_TRANSACTION_TESTS
        internal static Action<string> Fault = null;
        internal static int TargetWrites = 0;
#endif
        [System.Diagnostics.Conditional("ACCOUNT_TRANSACTION_TESTS")]
        static void Observe(string phase)
        {
#if ACCOUNT_TRANSACTION_TESTS
            if (Fault != null) Fault(phase);
#endif
        }
        internal static bool Apply(string selectedIdentity, bool enabled)
        {
            Platform();
            return ApplyCore(DefaultSetupPlan.Resolve(), selectedIdentity, enabled);
        }
        static void Platform()
        {
#if NETFRAMEWORK
            if (Environment.OSVersion.Platform == PlatformID.Win32NT) return;
#endif
            throw new PlatformNotSupportedException("Account changes require native Windows Framework");
        }
        static void Require(bool ok, string why) { if (!ok) throw new InvalidDataException(why); }
        sealed class Held : IDisposable
        {
            internal readonly List<SafeFileHandle> Handles = new List<SafeFileHandle>();
            internal readonly Dictionary<string, string> Identities = new Dictionary<string, string>(StringComparer.Ordinal);
            internal void Ancestors(string directory)
            {
                var paths = new Stack<string>();
                for (var d = new DirectoryInfo(directory); d != null; d = d.Parent) paths.Push(d.FullName);
                foreach (string path in paths)
                {
                    if (Identities.ContainsKey(path)) continue;
                    var h = Open(path, 0, 3, 3, true); Handles.Add(h);
                    Identities.Add(path, Identity(h, path, true));
                }
            }
            internal void Pair(PairState.Record pair)
            {
                foreach (var receipt in new[] { pair.Runtime.Component, pair.Runtime.State, pair.Plugin.Component, pair.Plugin.State })
                {
                    Ancestors(Path.GetDirectoryName(receipt.Root));
                    foreach (var item in receipt.Identities.OrderBy(p => p.Key.Length))
                    {
                        bool directory = !receipt.Hashes.ContainsKey(item.Key);
                        var h = Open(item.Key, directory ? 0u : 0x80000000u, directory ? 3u : 1u, 3, directory);
                        Handles.Add(h);
                        Require(Identity(h, item.Key, directory) == item.Value, "Installation changed while acquiring account-change guards");
                    }
                }
                PairState.Verify(pair);
            }
            public void Dispose()
            {
                var errors = new List<Exception>();
                for (int i = Handles.Count - 1; i >= 0; i--) try { Handles[i].Dispose(); } catch (Exception e) { errors.Add(e); }
                if (errors.Count != 0) throw new AggregateException("Account guard close failed", errors);
            }
        }
        static SafeFileHandle Open(string path, uint access, uint share, uint creation, bool directory)
        {
            var h = CreateFileW(path, access, share, IntPtr.Zero, creation, 0x00200000u | (directory ? 0x02000000u : 0u), IntPtr.Zero);
            if (h.IsInvalid) { int error = Marshal.GetLastWin32Error(); h.Dispose(); throw new Win32Exception(error); }
            return h;
        }
        static string Identity(SafeFileHandle handle, string path, bool directory)
        {
            FileInformation info;
            if (!GetFileInformationByHandle(handle, out info)) throw new Win32Exception(Marshal.GetLastWin32Error());
            Require((info.Attributes & 0x400) == 0 && ((info.Attributes & 0x10) != 0) == directory
                && (directory || info.Links == 1), "Account object is reparse, hard-linked or the wrong type");
            Require(GetFileType(handle) == 1, "Account object must be a disk file");
            var final = new StringBuilder(512);
            uint size = GetFinalPathNameByHandleW(handle, final, (uint)final.Capacity, 0);
            if (size == 0) throw new Win32Exception(Marshal.GetLastWin32Error());
            Require(size < final.Capacity && string.Equals(@"\\?\" + path, final.ToString(), StringComparison.OrdinalIgnoreCase), "Account object redirected");
            return info.Volume + ":" + info.IndexHigh + ":" + info.IndexLow + ":" + info.CreatedHigh + ":" + info.CreatedLow;
        }
        static FileStream Stream(string path, uint creation)
        {
            var handle = Open(path, 0xc0000000, 0, creation, false);
            try { Identity(handle, path, false); return new FileStream(handle, FileAccess.ReadWrite, 1, false); }
            catch { handle.Dispose(); throw; }
        }
        static byte[] Read(FileStream file, int limit)
        {
            Require(file.Length >= 0 && file.Length <= limit, "Account data size budget exceeded");
            file.Position = 0; byte[] bytes = new byte[(int)file.Length];
            int offset = 0;
            while (offset < bytes.Length)
            {
                int count = file.Read(bytes, offset, bytes.Length - offset);
                Require(count > 0, "Account data truncated"); offset += count;
            }
            Require(file.ReadByte() == -1, "Account data grew during read"); return bytes;
        }
        sealed class Journal
        {
            internal string Target, TargetId, ParentId, Root, RootId, FileId, Identity, PairBinding;
            internal bool Enabled;
            internal byte[] Original, Intended;
        }
        static string RecoveryRoot(DefaultSetupPlan plan) { return Path.Combine(plan.LocalData, "Trojaino-settings-recovery-v1"); }
        static string Target(DefaultSetupPlan plan) { return Path.Combine(plan.Profile, ".claude", "settings.json"); }
        static string JournalPath(string root) { return Path.Combine(root, "prepared.bin"); }
        static void Text(BinaryWriter w, string value)
        {
            byte[] b = Utf8.GetBytes(value); Require(b.Length > 0 && b.Length <= 4096, "Account journal text budget exceeded"); w.Write(b.Length); w.Write(b);
        }
        static string Text(BinaryReader r)
        {
            int n = r.ReadInt32(); Require(n > 0 && n <= 4096, "Account journal text budget exceeded");
            byte[] b = r.ReadBytes(n); Require(b.Length == n, "Account journal truncated"); return Utf8.GetString(b);
        }
        static byte[] Bytes(BinaryReader r)
        {
            int n = r.ReadInt32(); Require(n >= 0 && n <= MaxDocument, "Account journal document budget exceeded");
            byte[] b = r.ReadBytes(n); Require(b.Length == n, "Account journal truncated"); return b;
        }
        static byte[] Protect(byte[] bytes, bool seal)
        {
#if NETFRAMEWORK
            return seal ? ProtectedData.Protect(bytes, Utf8.GetBytes(Purpose), DataProtectionScope.CurrentUser)
                : ProtectedData.Unprotect(bytes, Utf8.GetBytes(Purpose), DataProtectionScope.CurrentUser);
#else
            throw new PlatformNotSupportedException();
#endif
        }
        static byte[] Encode(Journal j)
        {
            byte[] plain;
            using (var m = new MemoryStream()) using (var w = new BinaryWriter(m, Utf8))
            {
                w.Write(1);
                foreach (string s in new[] { j.Target, j.TargetId, j.ParentId, j.Root, j.RootId, j.FileId, j.Identity, j.PairBinding }) Text(w, s);
                w.Write(j.Enabled ? 1 : 0);
                w.Write(j.Original.Length); w.Write(j.Original); w.Write(j.Intended.Length); w.Write(j.Intended); w.Flush(); plain = m.ToArray();
            }
            try { byte[] cipher = Protect(plain, true); Require(cipher.Length > 0 && cipher.Length <= MaxCipher, "Account journal ciphertext budget exceeded"); return cipher; }
            finally { Array.Clear(plain, 0, plain.Length); }
        }
        static Journal Decode(byte[] cipher, string target, string root, string rootId, string fileId, string parentId)
        {
            Require(cipher.Length > 0 && cipher.Length <= MaxCipher, "Account journal ciphertext budget exceeded");
            byte[] plain = Protect(cipher, false); // Authenticate BEFORE any metadata parsing.
            Journal j = null;
            try
            {
                Require(plain.Length <= 2 * MaxDocument + 65536, "Account journal plaintext budget exceeded");
                using (var m = new MemoryStream(plain, false)) using (var r = new BinaryReader(m, Utf8))
                {
                    Require(r.ReadInt32() == 1, "Unsupported account journal version");
                    j = new Journal { Target = Text(r), TargetId = Text(r), ParentId = Text(r), Root = Text(r), RootId = Text(r), FileId = Text(r), Identity = Text(r), PairBinding = Text(r) };
                    int enabled = r.ReadInt32(); Require(enabled == 0 || enabled == 1, "Invalid journal operation"); j.Enabled = enabled == 1;
                    j.Original = Bytes(r); j.Intended = Bytes(r);
                    Require(m.Position == m.Length, "Trailing account journal data");
                }
                Require(j.Target == target && j.Root == root && j.RootId == rootId && j.FileId == fileId && j.ParentId == parentId, "Account journal location or object binding changed");
                Require(AccountPreferenceDocument.Edit(j.Original, j.Identity, j.Enabled).SequenceEqual(j.Intended), "Account journal intent mismatch");
                return j;
            }
            catch { Clear(j); throw; }
            finally { Array.Clear(plain, 0, plain.Length); }
        }
        static void Clear(Journal j)
        {
            if (j == null) return;
            if (j.Original != null) Array.Clear(j.Original, 0, j.Original.Length);
            if (j.Intended != null) Array.Clear(j.Intended, 0, j.Intended.Length);
        }
        static bool Present(string root)
        {
            try { File.GetAttributes(root); return true; }
            catch (FileNotFoundException) { return false; }
            catch (DirectoryNotFoundException) { return false; }
        }
        static void Inventory(string root)
        {
            using (var e = Directory.EnumerateFileSystemEntries(root).GetEnumerator())
            {
                Require(e.MoveNext() && e.Current == JournalPath(root) && !e.MoveNext(), "Unknown or incomplete account recovery records; retained unchanged");
            }
        }
        static PairState.Record Find(DefaultSetupPlan plan)
        {
#if ACCOUNT_TRANSACTION_TESTS && NETFRAMEWORK
            return DefaultSetupDiscovery.TestFind(plan);
#else
            return DefaultSetupDiscovery.Find();
#endif
        }
        static bool ApplyCore(DefaultSetupPlan plan, string selectedIdentity, bool enabled)
        {
            Platform();
            var pair = Find(plan);
            Require(pair != null && Path.GetFileName(pair.Plugin.Component.Root) + "@skills-dir" == selectedIdentity, "Displayed account-change identity is stale; recheck and consent again");
            string target = Target(plan), root = RecoveryRoot(plan), journalPath = JournalPath(root), parent = Path.GetDirectoryName(target);
            WindowsPreflight.Check(target, new string[0]); WindowsPreflight.Check(root, new[] { "prepared.bin" });
            var guards = new Held(); FileStream file = null, journalFile = null;
            Journal journal = null, decoded = null; byte[] original = null, intended = null;
            bool mutating = false, changed = false;
            var errors = new List<Exception>();
            try
            {
                guards.Ancestors(parent); guards.Ancestors(plan.LocalData); guards.Pair(pair);
                file = Stream(target, 3); // OPEN_EXISTING only; absent support is a separate story.
                string targetId = Identity(file.SafeFileHandle, target, false);
                original = Read(file, MaxDocument); intended = AccountPreferenceDocument.Edit(original, selectedIdentity, enabled);
                bool pending = Present(root);
                if (pending)
                {
                    guards.Ancestors(root); Inventory(root); journalFile = Stream(journalPath, 3);
                    decoded = Decode(Read(journalFile, MaxCipher), target, root, guards.Identities[root], Identity(journalFile.SafeFileHandle, journalPath, false), guards.Identities[parent]);
                }
                if (!original.SequenceEqual(intended))
                {
                    Require(!pending, "An earlier account change needs recovery review before another change; originals retained");
                    var createdRoot = Bootstrap.CreateEmpty(root); // Preserve original creation authority.
                    Observe("recovery-created");
                    guards.Ancestors(root);
                    Require(guards.Identities[root] == createdRoot.Identities[root], "Created recovery root changed before journal acquisition; retained unchanged");
                    journalFile = Stream(journalPath, 1); // CREATE_NEW; sole immutable original.
                    journal = new Journal { Target = target, TargetId = targetId, ParentId = guards.Identities[parent], Root = root, RootId = guards.Identities[root], FileId = Identity(journalFile.SafeFileHandle, journalPath, false), Identity = selectedIdentity,
                        PairBinding = pair.Plugin.Component.Identities[pair.Plugin.Component.Root] + "/" + pair.Plugin.State.Identities[pair.Plugin.State.Root], Enabled = enabled, Original = original, Intended = intended };
                    byte[] cipher = Encode(journal);
                    Observe("before-journal-write");
                    journalFile.Write(cipher, 0, cipher.Length);
                    Observe("before-journal-flush"); journalFile.Flush(true);
                    Observe("before-journal-readback");
                    Require(Read(journalFile, MaxCipher).SequenceEqual(cipher), "Protected original readback mismatch; settings unchanged");
                    decoded = Decode(cipher, target, root, journal.RootId, journal.FileId, journal.ParentId);
                    Require(decoded.TargetId == targetId && decoded.Original.SequenceEqual(original) && decoded.Intended.SequenceEqual(intended), "Protected original binding mismatch; settings unchanged");
                    Observe("journal-verified");
                    Inventory(root); PairState.Verify(pair);
                    Require(Identity(file.SafeFileHandle, target, false) == targetId, "Account object changed before write");
                    Observe("before-target-write");
                    mutating = true; // BEFORE first potentially mutating call.
                    file.Position = 0;
#if ACCOUNT_TRANSACTION_TESTS
                    TargetWrites++;
                    if (Fault != null && intended.Length > 0) { file.WriteByte(intended[0]); file.Flush(); Observe("target-partial"); file.Position = 0; }
#endif
                    file.Write(intended, 0, intended.Length);
                    Observe("before-target-eof"); file.SetLength(intended.Length);
                    Observe("before-target-flush"); file.Flush(true);
                    Observe("before-target-readback");
                    Require(Read(file, MaxDocument).SequenceEqual(intended) && Identity(file.SafeFileHandle, target, false) == targetId, "Account change readback failed");
                    changed = true;
                }
            }
            catch (Exception error) { errors.Add(error); }
            finally
            {
                // Keep the original on EVERY outcome. No automatic stale restore and
                // no deletion of user settings, incomplete journals or unknown content.
                foreach (IDisposable item in new IDisposable[] { file, journalFile, guards })
                    if (item != null) try { item.Dispose(); if (object.ReferenceEquals(item, file)) Observe("target-disposed"); } catch (Exception close) { errors.Add(close); }
                Clear(decoded); Clear(journal);
                if (original != null) Array.Clear(original, 0, original.Length);
                if (intended != null) Array.Clear(intended, 0, intended.Length);
            }
            if (errors.Count != 0)
                throw new AggregateException(mutating ? "Account settings may be incomplete. Protected originals retained; do not delete recovery files." : "Account settings were not written. Any recovery files were retained.", errors);
            return changed;
        }
#if ACCOUNT_TRANSACTION_TESTS
        internal static bool TestApply(DefaultSetupPlan plan, string identity, bool enabled) { return ApplyCore(plan, identity, enabled); }
        internal static byte[] TestOriginal(DefaultSetupPlan plan)
        {
            Platform(); string root = RecoveryRoot(plan), target = Target(plan), parent = Path.GetDirectoryName(target), path = JournalPath(root);
            using (var guards = new Held())
            {
                guards.Ancestors(root); guards.Ancestors(parent); Inventory(root);
                using (var file = Stream(path, 3))
                {
                    Journal j = Decode(Read(file, MaxCipher), target, root, guards.Identities[root], Identity(file.SafeFileHandle, path, false), guards.Identities[parent]);
                    try { return (byte[])j.Original.Clone(); } finally { Clear(j); }
                }
            }
        }
#endif
        [StructLayout(LayoutKind.Sequential)] struct FileInformation { public uint Attributes, CreatedLow, CreatedHigh, AccessLow, AccessHigh, WriteLow, WriteHigh, Volume, SizeHigh, SizeLow, Links, IndexHigh, IndexLow; }
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)] static extern SafeFileHandle CreateFileW(string path, uint access, uint share, IntPtr security, uint creation, uint flags, IntPtr template);
        [DllImport("kernel32.dll", SetLastError = true)] static extern bool GetFileInformationByHandle(SafeFileHandle handle, out FileInformation info);
        [DllImport("kernel32.dll", SetLastError = true)] static extern uint GetFileType(SafeFileHandle handle);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)] static extern uint GetFinalPathNameByHandleW(SafeFileHandle handle, StringBuilder result, uint size, uint flags);
    }
}
