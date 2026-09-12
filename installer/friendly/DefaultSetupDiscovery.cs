// Hints select a fixed identity only; authenticated ownership remains PairState's job.
using System;
using System.Collections.Generic;
using System.IO;
using System.Text.RegularExpressions;

namespace Trojaino.Setup
{
    internal static class DefaultSetupDiscovery
    {
        internal static PairState.Record Find()
        {
#if NETFRAMEWORK
            return FindCore(DefaultSetupPlan.Resolve());
#else
            throw new PlatformNotSupportedException("Setup requires native Windows Framework");
#endif
        }
#if NETFRAMEWORK
        static PairState.Record FindCore(DefaultSetupPlan folders)
        {
            if (Environment.OSVersion.Platform != PlatformID.Win32NT)
                throw new PlatformNotSupportedException("Setup requires native Windows Framework");
            CheckFolder(folders.Profile); CheckFolder(folders.LocalData);
            string config = Path.Combine(folders.Profile, ".claude");
            string skills = Path.Combine(config, "skills");
            IEnumerable<string> skillNames = new string[0];
            if (OptionalFolder(config) && OptionalFolder(skills)) skillNames = Names(skills);
            string id = Select(Names(folders.LocalData), skillNames);
            if (id == null) return null;
            string[] roots = folders.WithIdentity(id).Roots;
            // Hints are not ownership. Load authenticates all four exact trees and identities.
            return PairState.Load(roots[0], roots[3], roots[4], roots[5]);
        }
        static void CheckFolder(string folder)
        {
            // Check validates its parent, including native volume/alias/reparse gates;
            // this nonexistent child name is never opened or created.
            WindowsPreflight.Check(Path.Combine(folder, "discovery-probe"), new string[0]);
        }
        static bool OptionalFolder(string folder)
        {
            FileAttributes attributes;
            try { attributes = File.GetAttributes(folder); }
            catch (FileNotFoundException) { return false; }
            catch (DirectoryNotFoundException) { return false; }
            if ((attributes & FileAttributes.Directory) == 0 || (attributes & FileAttributes.ReparsePoint) != 0)
                throw new InvalidDataException("Claude's settings folder cannot be checked safely. Nothing was changed.");
            CheckFolder(folder); return true;
        }
        static IEnumerable<string> Names(string folder)
        {
            foreach (string entry in Directory.EnumerateFileSystemEntries(folder)) yield return Path.GetFileName(entry);
        }
#if SETUP_DISCOVERY_TESTS
        internal static PairState.Record TestFind(DefaultSetupPlan folders) { return FindCore(folders); }
#endif
#endif
        static string Select(IEnumerable<string> local, IEnumerable<string> skills)
        {
            var identities = new Dictionary<string, int>(StringComparer.Ordinal);
            Collect(local, false, identities); Collect(skills, true, identities);
            if (identities.Count == 0) return null;
            if (identities.Count != 1) throw new InvalidDataException("More than one Trojaino installation was found. Nothing was changed.");
            foreach (var entry in identities)
            {
                if (entry.Value != 15) throw new InvalidDataException("Trojaino setup is incomplete. Existing files were kept; do not install another copy.");
                return entry.Key;
            }
            throw new InvalidDataException("Installation hints changed");
        }
        static void Collect(IEnumerable<string> names, bool skills, Dictionary<string, int> identities)
        {
            int count = 0;
            foreach (string name in names)
            {
                if (++count > 4096) throw new InvalidDataException("Too many entries to check safely. Nothing was changed.");
                string prefix = skills ? "trojaino-local-" : "trj-";
                if (!name.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)) continue;
                var match = Regex.Match(name, skills ? @"\Atrojaino-local-([a-f0-9]{32})\z" : @"\Atrj-([a-f0-9]{32})-(runtime|runtime-state|plugin-state)\z", RegexOptions.CultureInvariant);
                if (!match.Success) throw new InvalidDataException("Unrecognized Trojaino setup files were found. They were kept unchanged.");
                string id = match.Groups[1].Value;
                int bit = skills ? 8 : match.Groups[2].Value == "runtime" ? 1 : match.Groups[2].Value == "runtime-state" ? 2 : 4;
                int prior; identities.TryGetValue(id, out prior);
                if ((prior & bit) != 0) throw new InvalidDataException("Duplicate Trojaino setup hint");
                identities[id] = prior | bit;
            }
        }
#if SETUP_DISCOVERY_TESTS
        internal static string TestSelect(IEnumerable<string> local, IEnumerable<string> skills) { return Select(local, skills); }
#endif
    }
}
