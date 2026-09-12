// Controller prewrite location validation only. No ownership or setup success.
using System;
using System.IO;

namespace Trojaino.Setup
{
    internal static class SetupLocations
    {
        static void Platform()
        {
#if NETFRAMEWORK
            if (Environment.OSVersion.Platform != PlatformID.Win32NT) throw new PlatformNotSupportedException("Setup requires native Windows Framework");
#else
            throw new PlatformNotSupportedException("Setup requires native Windows Framework");
#endif
        }
        internal static void Check(string[] roots, string name)
        {
            Platform(); // Refuse unsupported runtimes before input or filesystem probes.
            if (roots == null) throw new InvalidDataException("Six setup roots required");
            var snapshot = (string[])roots.Clone();
            ValidateLayout(snapshot, name);
            var members = Members();
            for (int i = 0; i < snapshot.Length; i++)
            {
                WindowsPreflight.Check(snapshot[i], members[i]);
                try { File.GetAttributes(snapshot[i]); }
                catch (FileNotFoundException) { continue; }
                catch (DirectoryNotFoundException) { continue; }
                throw new InvalidDataException("Setup destination already exists");
            }
        }

        static string[][] Members()
        {
            return new[] {
                ApprovedPayload.RuntimeMembers(), ApprovedPayload.SourceMembers(), new string[0],
                new[] {".claude-plugin/plugin.json", "LICENSE", "MANIFEST.sha256.json", "README.md", "hooks/hooks.json", "scripts/hook.sh", "scripts/preflight.py", "skills/scan/SKILL.md"},
                new[] {"receipt.bin"}, new[] {"receipt.bin"}
            };
        }
        internal static void ValidateLayout(string[] roots, string name)
        {
            if (roots == null || roots.Length != 6) throw new InvalidDataException("Six setup roots required");
            var members = Members();
            for (int i = 0; i < roots.Length; i++) WindowsPreflight.ValidateSpelling(roots[i], members[i]);
            for (int i = 0; i < roots.Length; i++)
                for (int j = 0; j < i; j++)
                    if (string.Equals(roots[i], roots[j], StringComparison.OrdinalIgnoreCase)
                        || roots[i].StartsWith(roots[j] + "\\", StringComparison.OrdinalIgnoreCase)
                        || roots[j].StartsWith(roots[i] + "\\", StringComparison.OrdinalIgnoreCase))
                        throw new InvalidDataException("Setup roots must not overlap");
            string parent = roots[0].Substring(0, roots[0].LastIndexOf('\\'));
            for (int i = 1; i <= 2; i++)
                if (roots[i].Substring(0, roots[i].LastIndexOf('\\')) != parent)
                    throw new InvalidDataException("Runtime, source and scratch must be literal siblings");
            if (name == null || name.Length > 120
                || !System.Text.RegularExpressions.Regex.IsMatch(name, @"\Atrojaino-local-[a-z0-9]+(?:-[a-z0-9]+)*\z")
                || roots[3].Substring(roots[3].LastIndexOf('\\') + 1) != name)
                throw new InvalidDataException("Exact distinct personal plugin name required");
        }
    }
}
