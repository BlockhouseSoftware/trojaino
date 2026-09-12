// Pre-Python staging core. Not an installer UI or activation authority.
// Pins must come from reviewed compiled build resources, never the input archive.
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text.RegularExpressions;

namespace Trojaino.Setup
{
    public static class Bootstrap
    {
#if BOOTSTRAP_TESTS
        internal static Action<string> AfterWrite;
        internal static Action<string> DuringWrite;
#endif
        const int MaxArchive = 64 * 1024 * 1024;
        const int MaxFile = 32 * 1024 * 1024;
        const int MaxTotal = 128 * 1024 * 1024;
        internal static string Hash(byte[] bytes)
        {
            using (var hash = SHA256.Create())
                return BitConverter.ToString(hash.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant();
        }
        static void Require(bool ok, string why) { if (!ok) throw new InvalidDataException(why); }
        static void SafeName(string name)
        {
            Require(name.Length <= 200 && name.Split('/').Length <= 12, "Archive path budget exceeded");
            foreach (string part in name.Split('/'))
                Require(Regex.IsMatch(part, @"\A[A-Za-z0-9_.-]{1,120}\z") && part != "." && part != ".."
                    && !part.EndsWith(".", StringComparison.Ordinal)
                    && !Regex.IsMatch(part.Split('.')[0], @"\A(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])\z", RegexOptions.IgnoreCase), "Unsafe archive path");
        }
        static Dictionary<string, byte[]> VerifiedFiles(byte[] archive, string archiveHash, IDictionary<string, string> pins)
        {
            Require(archive.Length <= MaxArchive, "Compressed archive budget exceeded");
            Require(Hash(archive) == archiveHash, "Archive digest mismatch");
            var result = new Dictionary<string, byte[]>(StringComparer.Ordinal);
            var paths = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            var files = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var directories = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            using (var memory = new MemoryStream(archive, false))
            using (var zip = new ZipArchive(memory, ZipArchiveMode.Read))
            {
                Require(zip.Entries.Count > 0 && zip.Entries.Count <= 4096 && pins.Count == zip.Entries.Count, "Archive inventory mismatch or budget exceeded");
                long total = 0;
                foreach (var entry in zip.Entries)
                {
                    SafeName(entry.FullName);
                    int kind = (entry.ExternalAttributes >> 16) & 0xf000;
                    Require((kind == 0 || kind == 0x8000) && (entry.ExternalAttributes & 0x418) == 0, "Only regular files permitted");
                    string expected;
                    Require(pins.TryGetValue(entry.FullName, out expected), "Unapproved archive member");
                    var parts = entry.FullName.Split('/');
                    for (int i = 1; i <= parts.Length; i++)
                    {
                        string prefix = string.Join("/", parts.Take(i));
                        string old;
                        Require(!paths.TryGetValue(prefix, out old) || old == prefix, "Case alias in archive");
                        paths[prefix] = prefix;
                        if (i < parts.Length) { Require(!files.Contains(prefix), "File/directory collision"); directories.Add(prefix); }
                        else { Require(!directories.Contains(prefix) && files.Add(prefix), "Duplicate or colliding member"); }
                    }
                    Require(entry.Length >= 0 && entry.Length <= MaxFile && (total += entry.Length) <= MaxTotal, "Expanded archive budget exceeded");
                    using (var input = entry.Open())
                    using (var output = new MemoryStream())
                    {
                        var buffer = new byte[8192];
                        int count;
                        while ((count = input.Read(buffer, 0, buffer.Length)) > 0)
                        {
                            Require(output.Length + count <= entry.Length, "Expanded member length mismatch");
                            output.Write(buffer, 0, count);
                        }
                        var data = output.ToArray();
                        Require(data.Length == entry.Length && Hash(data) == expected, "Member digest or length mismatch");
                        result.Add(entry.FullName, data);
                    }
                }
            }
            return result;
        }
        internal static void PlainAncestors(string path)
        {
            for (var current = new DirectoryInfo(path); current != null; current = current.Parent)
                Require(current.Exists && (current.Attributes & FileAttributes.ReparsePoint) == 0, "Missing or reparse ancestor");
        }
        static void CreatePrivate(string path)
        {
            if (Environment.OSVersion.Platform == PlatformID.Win32NT)
            {
                string sid = WindowsIdentity.GetCurrent().User.Value;
                IntPtr descriptor;
                uint size;
                if (!ConvertStringSecurityDescriptorToSecurityDescriptorW("O:" + sid + "D:P(A;OICI;FA;;;" + sid + ")", 1, out descriptor, out size))
                    throw new Win32Exception(Marshal.GetLastWin32Error());
                try
                {
                    var attributes = new SecurityAttributes { Length = Marshal.SizeOf(typeof(SecurityAttributes)), Descriptor = descriptor, Inherit = 0 };
                    if (!CreateDirectoryW(path, ref attributes)) throw new Win32Exception(Marshal.GetLastWin32Error());
                }
                finally { LocalFree(descriptor); }
            }
            else if (RuntimeInformation.IsOSPlatform(OSPlatform.OSX))
            {
                if (mkdir(path, 448) != 0) throw new Win32Exception(Marshal.GetLastWin32Error()); // 0700; exclusive.
            }
            else throw new PlatformNotSupportedException("Only Windows and the macOS development harness are supported");
        }
        public static Receipt Install(byte[] archive, string archiveHash, IDictionary<string, string> pins, string destination)
        {
            var payload = VerifiedFiles(archive, archiveHash, pins); // Before any writes or runtime execution.
            if (Environment.OSVersion.Platform == PlatformID.Win32NT) WindowsPreflight.Check(destination, payload.Keys);
            Require(Path.IsPathRooted(destination) && Path.GetFullPath(destination) == destination, "Literal absolute destination required");
            PlainAncestors(Path.GetDirectoryName(destination));
            CreatePrivate(destination); // Never accept an existing name.
            var receipt = new Receipt(destination);
            receipt.Identities.Add(destination, Identity(destination));
            var directories = new HashSet<string>(StringComparer.Ordinal) { destination };
            try
            {
            foreach (var file in payload.OrderBy(p => p.Key, StringComparer.Ordinal))
            {
                var parts = file.Key.Split('/');
                string parent = destination;
                foreach (string part in parts.Take(parts.Length - 1))
                {
                    parent = Path.Combine(parent, part);
                    if (directories.Add(parent)) { CreatePrivate(parent); receipt.Identities.Add(parent, Identity(parent)); }
                }
                // ZIP member '/' is archive syntax, not a native separator.
                // The validated components above already built the literal parent.
                var target = Path.Combine(parent, parts[parts.Length - 1]);
                using (var output = new FileStream(target, FileMode.CreateNew, FileAccess.ReadWrite, FileShare.None))
                {
                    receipt.Identities.Add(target, Identity(target));
                    try
                    {
#if BOOTSTRAP_TESTS
                        if (DuringWrite != null && file.Value.Length > 0) { output.WriteByte(file.Value[0]); output.Flush(); DuringWrite(target); output.Position = 0; }
#endif
                        output.Write(file.Value, 0, file.Value.Length); output.Flush(true);
                    }
                    finally
                    {
                        // Snapshot partial bytes from the owned handle, never from a replacement path.
                        // If the disk also prevents reading these bytes, cleanup refuses the unknown file.
                        output.Flush(); output.Position = 0;
                        using (var hash = SHA256.Create())
                            receipt.Hashes.Add(target, BitConverter.ToString(hash.ComputeHash(output)).Replace("-", "").ToLowerInvariant());
                        receipt.Lengths.Add(target, output.Length);
                    }
                }
                Require(receipt.Hashes[target] == Hash(file.Value), "Written file digest mismatch");
#if BOOTSTRAP_TESTS
                if (AfterWrite != null) AfterWrite(target);
#endif
            }
            Verify(receipt);
            return receipt;
            }
            catch (Exception failure)
            {
                try { Remove(receipt); }
                catch (Exception cleanup) { throw new AggregateException("Setup failed; unverified partial tree retained, never activated", failure, cleanup); }
                throw;
            }
        }
        public static Receipt CreateEmpty(string destination)
        {
            if (Environment.OSVersion.Platform == PlatformID.Win32NT) WindowsPreflight.Check(destination, new string[0]);
            Require(!string.IsNullOrEmpty(destination) && Path.IsPathRooted(destination) && Path.GetFullPath(destination) == destination, "Literal absolute scratch destination required");
            PlainAncestors(Path.GetDirectoryName(destination));
            CreatePrivate(destination); // Exclusive and private, never adopt an existing directory.
            var receipt = new Receipt(destination);
            receipt.Identities.Add(destination, Identity(destination));
            Verify(receipt);
            return receipt; // On identity/probe failure retain the new tree; never guess ownership.
        }
        public sealed class Receipt
        {
            internal readonly string Root;
            internal readonly Dictionary<string, string> Identities = new Dictionary<string, string>(StringComparer.Ordinal);
            internal readonly Dictionary<string, string> Hashes = new Dictionary<string, string>(StringComparer.Ordinal);
            internal readonly Dictionary<string, long> Lengths = new Dictionary<string, long>(StringComparer.Ordinal);
            internal Receipt(string root) { Root = root; }
        }
        public static void Verify(Receipt receipt)
        {
            PlainAncestors(Path.GetDirectoryName(receipt.Root));
            var pending = new Stack<string>(); pending.Push(receipt.Root);
            var found = new HashSet<string>(StringComparer.Ordinal);
            while (pending.Count > 0)
            {
                var path = pending.Pop();
                string expected;
                Require(receipt.Identities.TryGetValue(path, out expected), "Unknown installed content; nothing removed");
                Require(Identity(path) == expected, "Installed object replaced; nothing removed");
                found.Add(path);
                if (receipt.Hashes.ContainsKey(path))
                {
                    using (var input = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
                    using (var hash = SHA256.Create())
                    {
                        Require(input.Length == receipt.Lengths[path], "Installed length changed; nothing removed");
                        Require(BitConverter.ToString(hash.ComputeHash(input)).Replace("-", "").ToLowerInvariant() == receipt.Hashes[path], "Installed bytes changed; nothing removed");
                    }
                }
                else foreach (var child in Directory.GetFileSystemEntries(path)) pending.Push(child);
            }
            Require(found.SetEquals(receipt.Identities.Keys), "Missing installed content; nothing removed");
        }
        public static void Remove(Receipt receipt)
        {
            Verify(receipt); // Complete preflight before the first deletion. No recursive deletion.
            foreach (var path in receipt.Hashes.Keys) File.Delete(path);
            foreach (var path in receipt.Identities.Keys.Where(p => !receipt.Hashes.ContainsKey(p)).OrderByDescending(p => p.Length)) Directory.Delete(path, false);
        }
        internal static string Identity(string path)
        {
            Require((File.GetAttributes(path) & FileAttributes.ReparsePoint) == 0, "Reparse object refused");
            if (Environment.OSVersion.Platform == PlatformID.Win32NT)
            {
                Require(new DriveInfo(Path.GetPathRoot(path)).DriveFormat == "NTFS", "Native setup currently requires local NTFS");
                using (var handle = CreateFileW(path, 0, 7, IntPtr.Zero, 3, 0x02200000, IntPtr.Zero))
                {
                    if (handle.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error());
                    FileInformation info;
                    if (!GetFileInformationByHandle(handle, out info)) throw new Win32Exception(Marshal.GetLastWin32Error());
                    Require((info.Attributes & 0x400) == 0 && ((info.Attributes & 0x10) != 0 || info.Links == 1), "Reparse or hard-linked object refused");
                    return info.Volume + ":" + info.IndexHigh + ":" + info.IndexLow + ":" + info.CreatedHigh + ":" + info.CreatedLow;
                }
            }
            if (!RuntimeInformation.IsOSPlatform(OSPlatform.OSX)) throw new PlatformNotSupportedException();
            // Darwin stat64 layout from the Apple SDK sys/stat.h; not a Linux ABI.
            IntPtr stat = Marshal.AllocHGlobal(256);
            try
            {
                if (lstat(path, stat) != 0) throw new Win32Exception(Marshal.GetLastWin32Error());
                int mode = (ushort)Marshal.ReadInt16(stat, 4);
                Require((mode & 0xf000) == 0x4000 || ((mode & 0xf000) == 0x8000 && Marshal.ReadInt16(stat, 6) == 1), "Only plain owned objects permitted");
                return Marshal.ReadInt32(stat, 0) + ":" + Marshal.ReadInt64(stat, 8) + ":" + Marshal.ReadInt64(stat, 80) + ":" + Marshal.ReadInt64(stat, 88);
            }
            finally { Marshal.FreeHGlobal(stat); }
        }
        [StructLayout(LayoutKind.Sequential)] struct FileInformation
        {
            public uint Attributes, CreatedLow, CreatedHigh, AccessLow, AccessHigh, WriteLow, WriteHigh, Volume, SizeHigh, SizeLow, Links, IndexHigh, IndexLow;
        }
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)] static extern Microsoft.Win32.SafeHandles.SafeFileHandle CreateFileW(string path, uint access, uint share, IntPtr security, uint creation, uint flags, IntPtr template);
        [DllImport("kernel32.dll", SetLastError = true)] static extern bool GetFileInformationByHandle(Microsoft.Win32.SafeHandles.SafeFileHandle handle, out FileInformation info);
        [DllImport("libc", SetLastError = true)] static extern int lstat(string path, IntPtr info);
        [StructLayout(LayoutKind.Sequential)] struct SecurityAttributes { public int Length; public IntPtr Descriptor; public int Inherit; }
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)] static extern bool CreateDirectoryW(string path, ref SecurityAttributes attributes);
        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)] static extern bool ConvertStringSecurityDescriptorToSecurityDescriptorW(string text, uint revision, out IntPtr descriptor, out uint size);
        [DllImport("kernel32.dll")] static extern IntPtr LocalFree(IntPtr memory);
        [DllImport("libc", SetLastError = true)] static extern int mkdir(string path, uint mode);
    }
}
