using System;
using System.Collections.Generic;
using System.IO;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;
using System.Text.RegularExpressions;

namespace Trojaino.Setup
{
    internal static class WindowsPreflight
    {
        static void Require(bool ok, string why) { if (!ok) throw new InvalidDataException(why); }
        internal static void Check(string destination, IEnumerable<string> members)
        {
            if (Environment.OSVersion.Platform != PlatformID.Win32NT) throw new PlatformNotSupportedException("Windows native preflight requires Windows");
            ValidateSpelling(destination, members);
            ushort processMachine, nativeMachine;
            if (!IsWow64Process2(GetCurrentProcess(), out processMachine, out nativeMachine))
                throw new Win32Exception(Marshal.GetLastWin32Error());
            var drive = new DriveInfo(destination.Substring(0, 3));
            ValidateEnvironment(nativeMachine, drive.DriveType, drive.DriveFormat);
            string parent = Path.GetDirectoryName(destination);
            Bootstrap.PlainAncestors(parent);
            var longPath = new StringBuilder(512);
            uint length = GetLongPathNameW(parent, longPath, (uint)longPath.Capacity);
            if (length == 0) throw new Win32Exception(Marshal.GetLastWin32Error());
            Require(length < longPath.Capacity && string.Equals(parent, longPath.ToString(), StringComparison.OrdinalIgnoreCase), "Short-name parent alias refused");
            using (var handle = CreateFileW(parent, 0, 7, IntPtr.Zero, 3, 0x02200000, IntPtr.Zero))
            {
                if (handle.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error());
                var finalPath = new StringBuilder(512);
                length = GetFinalPathNameByHandleW(handle, finalPath, (uint)finalPath.Capacity, 0);
                if (length == 0) throw new Win32Exception(Marshal.GetLastWin32Error());
                Require(length < finalPath.Capacity && string.Equals(@"\\?\" + parent, finalPath.ToString(), StringComparison.OrdinalIgnoreCase), "Mapped or redirected parent refused");
            }
        }
        [DllImport("kernel32.dll", SetLastError = true)] static extern bool IsWow64Process2(IntPtr process, out ushort processMachine, out ushort nativeMachine);
        [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)] static extern uint GetLongPathNameW(string path, StringBuilder output, uint size);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)] static extern SafeFileHandle CreateFileW(string path, uint access, uint share, IntPtr security, uint creation, uint flags, IntPtr template);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)] static extern uint GetFinalPathNameByHandleW(SafeFileHandle handle, StringBuilder output, uint size, uint flags);

        internal static void ValidateEnvironment(ushort nativeMachine, DriveType driveType, string format)
        {
            Require(nativeMachine == 0x8664, "This approved runtime requires native Windows x64, not ARM emulation");
            Require(driveType == DriveType.Fixed && format == "NTFS", "Setup requires a local fixed NTFS volume");
        }
        internal static void ValidateSpelling(string destination, IEnumerable<string> members)
        {
            Require(destination != null && Regex.IsMatch(destination, @"\A[A-Za-z]:\\[^\\]"), "Literal drive-qualified Windows destination required");
            Require(destination.Length < 248, "Destination exceeds conservative Windows directory budget");
            foreach (string part in destination.Substring(3).Split('\\'))
            {
                Require(part.Length > 0 && part != "." && part != ".." && !part.EndsWith(".", StringComparison.Ordinal)
                    && !part.EndsWith(" ", StringComparison.Ordinal), "Nonliteral Windows path component");
                foreach (char c in part)
                    Require(!char.IsControl(c) && "<>:\"/|?*".IndexOf(c) < 0, "Unsafe Windows destination character");
                Require(!Regex.IsMatch(part.Split('.')[0].TrimEnd(' '), @"\A(CON|CONIN\$|CONOUT\$|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])\z", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant), "Reserved Windows device name");
            }
            foreach (string member in members)
                // Also bounds directories conservatively, without enabling long-path policy.
                Require(destination.Length + 1 + member.Length < 248, "Installed member exceeds conservative Windows path budget");
        }
    }
}
