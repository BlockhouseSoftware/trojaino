// Shared parent ownership is transient, never persistent uninstall authority.
using System;
using System.Collections.Generic;

namespace Trojaino.Setup
{
    internal static class SharedParents
    {
        internal static void Run(DefaultSetupPlan plan, Action continuation)
        {
#if NETFRAMEWORK
            if (Environment.OSVersion.Platform != PlatformID.Win32NT)
                throw new PlatformNotSupportedException("Setup requires native Windows Framework");
            if (plan == null || continuation == null) throw new ArgumentNullException("plan or continuation");
            string[] roots = plan.Roots; string name = plan.Name;
            SetupLocations.ValidateLayout(roots, name);
            string skills = System.IO.Path.GetDirectoryName(roots[3]);
            string config = System.IO.Path.GetDirectoryName(skills);
            string profile = System.IO.Path.GetDirectoryName(config);
            Bootstrap.PlainAncestors(profile); // Missing OS root is never recursively created.
            var missing = new List<string>();
            foreach (string parent in new[] {config, skills})
            {
                if (!Present(parent)) missing.Add(parent);
                else Bootstrap.PlainAncestors(parent); // Refuse files/reparse parents; preserve contents.
            }
            // Full expanded member budgets were checked above. Check the actual
            // closest existing plugin ancestor without creating the missing chain.
            WindowsPreflight.Check(missing.Count == 0 ? roots[3] : missing[0], new string[0]);
            for (int role = 0; role < roots.Length; role++)
            {
                if (role != 3) WindowsPreflight.Check(roots[role], new string[0]);
                if (Present(roots[role])) throw new System.IO.InvalidDataException("Setup destination already exists");
            }
            Execute(missing.ToArray(), null, () => { SetupLocations.Check(roots, name); continuation(); });
#else
            throw new PlatformNotSupportedException("Setup requires native Windows Framework");
#endif
        }
#if NETFRAMEWORK
        static bool Present(string path)
        {
            try { System.IO.File.GetAttributes(path); return true; }
            catch (System.IO.FileNotFoundException) { return false; }
            catch (System.IO.DirectoryNotFoundException) { return false; }
        }
#endif
        static void Execute(string[] missing, Action<string> afterCreate, Action continuation)
        {
            var owned = new List<Bootstrap.Receipt>();
            try
            {
                foreach (string path in missing)
                {
                    owned.Add(Bootstrap.CreateEmpty(path));
                    if (afterCreate != null) afterCreate(path);
                }
                continuation();
            }
            catch (Exception failure)
            {
                var errors = new List<Exception> {failure};
                for (int i = owned.Count - 1; i >= 0; i--)
                    try { Bootstrap.Remove(owned[i]); } catch (Exception cleanup) { errors.Add(cleanup); }
                if (errors.Count > 1) throw new AggregateException("Parent setup failed; unverified shared content retained", errors);
                throw;
            }
        }
#if SETUP_PARENTS_TESTS
        internal static void TestRun(string[] missing, Action gate, Action<string> afterCreate, Action continuation)
        { gate(); Execute((string[])missing.Clone(), afterCreate, continuation); }
#endif
    }
}
