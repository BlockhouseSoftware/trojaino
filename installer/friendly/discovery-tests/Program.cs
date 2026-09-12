using System;
using System.IO;
using System.Reflection;
using System.Collections.Generic;
using System.Linq;
using System.IO.Compression;
using System.Security.Cryptography;
using Trojaino.Setup;

internal static class DiscoveryTests
{
    static void Assert(bool value, string why) { if (!value) throw new Exception("ASSERT: " + why); }
    static string Select(IEnumerable<string> local, IEnumerable<string> skills)
    {
        var type = Assembly.GetExecutingAssembly().GetType("Trojaino.Setup.DefaultSetupDiscovery");
        Assert(type != null, "existing-install discovery missing");
        var method = type.GetMethod("TestSelect", BindingFlags.Static | BindingFlags.NonPublic);
        Assert(method != null, "bounded hint selection missing");
        try { return (string)method.Invoke(null, new object[] {local, skills}); }
        catch (TargetInvocationException error) { throw error.InnerException; }
    }
    static void Refuse(IEnumerable<string> local, IEnumerable<string> skills)
    {
        bool refused = false;
        try { Select(local, skills); } catch (InvalidDataException) { refused = true; }
        Assert(refused, "unsafe hints accepted");
    }
    static IEnumerable<string> Many(int count)
    { for (int i = 0; i < count; i++) yield return "unrelated-" + i; }
    static int observed;
    static IEnumerable<string> GuardedInfinite()
    {
        while (true)
        {
            if (++observed > 4097) throw new Exception("enumerated past overflow boundary");
            yield return "unrelated";
        }
    }
    static IEnumerable<string> Throws()
    { yield return "unrelated"; throw new UnauthorizedAccessException("fixture access failure"); }
#if NETFRAMEWORK
    static string[] Snapshot(string root)
    {
        return new[] {root}.Concat(Directory.GetFileSystemEntries(root, "*", SearchOption.AllDirectories)).OrderBy(p => p, StringComparer.Ordinal).Select(p =>
            p + "|" + Bootstrap.Identity(p) + "|" + (Directory.Exists(p) ? "directory" : Bootstrap.Hash(File.ReadAllBytes(p)))).ToArray();
    }
    static void RecoveryRefuses(DefaultSetupPlan plan, string reason)
    {
        string[] before = Snapshot(plan.Profile); bool refused = false;
        try { DefaultSetupDiscovery.TestFindRemaining(plan); }
        catch (Exception error)
        {
            if (!(error is IOException || error is InvalidDataException || error is CryptographicException || error is System.ComponentModel.Win32Exception)) throw;
            Assert(reason == null || error.Message.Contains(reason), "wrong recovery refusal: " + error.Message);
            refused = true;
        }
        Assert(refused, "unsafe native recovery hints accepted");
        Assert(Snapshot(plan.Profile).SequenceEqual(before), "native recovery refusal changed inventory/identities/bytes");
    }
    static void NativeRecovery()
    {
        string root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "rd-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            string local = Path.Combine(root, "local"); Directory.CreateDirectory(local);
            var plan = DefaultSetupPlan.TestCreate(root, local, null, "0123456789abcdef0123456789abcdef");
            string config = Path.Combine(root, ".claude"), skills = Path.Combine(config, "skills");
            string[] before = Snapshot(root);
            Assert(DefaultSetupDiscovery.TestFindRemaining(plan) == null && Snapshot(root).SequenceEqual(before), "missing config recovery created files");
            File.WriteAllText(config, "keep"); RecoveryRefuses(plan, "settings folder cannot be checked safely"); File.Delete(config);
            Directory.CreateDirectory(config); before = Snapshot(root);
            Assert(DefaultSetupDiscovery.TestFindRemaining(plan) == null && Snapshot(root).SequenceEqual(before), "missing skills recovery created files");
            File.WriteAllText(skills, "keep"); RecoveryRefuses(plan, "settings folder cannot be checked safely"); File.Delete(skills); Directory.CreateDirectory(skills);
            string[] roles = new[] {plan.Roots[0], plan.Roots[4], plan.Roots[5], plan.Roots[3]};
            foreach (bool directories in new[] {false, true})
            for (int mask = 0; mask < 16; mask++)
            {
                for (int role = 0; role < roles.Length; role++)
                    if ((mask & (1 << role)) != 0) { if (directories) Directory.CreateDirectory(roles[role]); else File.WriteAllText(roles[role], "untrusted hint only"); }
                before = Snapshot(root);
                if (mask == 0 || mask == 15)
                {
                    Assert(DefaultSetupDiscovery.TestFindRemaining(plan) == null, "absent/full mask should defer without ownership");
                    if (mask == 15)
                    {
                        bool refused = false;
                        try { DefaultSetupDiscovery.TestFind(plan); }
                        catch (Exception error) { if (!(error is IOException || error is InvalidDataException || error is System.ComponentModel.Win32Exception)) throw; refused = true; }
                        Assert(refused, "full hint deferral conferred ownership");
                    }
                    Assert(Snapshot(root).SequenceEqual(before), "deferred recovery changed hints");
                }
                else RecoveryRefuses(plan, mask == 3 ? null : "setup is incomplete");
                for (int role = 0; role < roles.Length; role++)
                    if ((mask & (1 << role)) != 0) { if (directories) Directory.Delete(roles[role]); else File.Delete(roles[role]); }
            }
            byte[] bytes = new byte[] {1, 2, 3}, archive;
            using (var memory = new MemoryStream())
            {
                using (var zip = new ZipArchive(memory, ZipArchiveMode.Create, true))
                foreach (string name in new[] {"keep.bin", "missing.bin"})
                    using (var output = zip.CreateEntry(name).Open()) output.Write(bytes, 0, bytes.Length);
                archive = memory.ToArray();
            }
            var component = Bootstrap.Install(archive, Bootstrap.Hash(archive), new Dictionary<string, string> {{"keep.bin", Bootstrap.Hash(bytes)}, {"missing.bin", Bootstrap.Hash(bytes)}}, roles[0]);
            StateStore.Store(component, roles[1]); File.Delete(Path.Combine(roles[0], "missing.bin"));
            var remaining = DefaultSetupDiscovery.TestFindRemaining(plan);
            Assert(remaining != null && remaining.Root == roles[0] && remaining.StateRoot == roles[1], "native authenticated recovery did not select exact locations");
            foreach (string hint in new[] {Path.Combine(local, "trj-"), plan.Roots[1], plan.Roots[2], Path.Combine(skills, "trojaino-local-"), Path.Combine(skills, "trojaino-local-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")})
            {
                File.WriteAllText(hint, "keep unknown");
                RecoveryRefuses(plan, hint.EndsWith("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", StringComparison.Ordinal) ? "More than one" : "Unrecognized");
                File.Delete(hint);
            }
            string upper = Path.Combine(local, Path.GetFileName(roles[0]).ToUpperInvariant()), held = Path.Combine(root, "held-runtime");
            Directory.Move(roles[0], held); Directory.Move(held, upper); RecoveryRefuses(plan, "Unrecognized");
            Directory.Move(upper, held); Directory.Move(held, roles[0]);
            remaining.Remove();
            Assert(DefaultSetupDiscovery.TestFindRemaining(plan) == null && DefaultSetupDiscovery.TestFind(plan) == null, "native recovery did not establish absence");
            Assert(!Directory.EnumerateFileSystemEntries(local).Any() && !Directory.EnumerateFileSystemEntries(skills).Any(), "native recovery left role entries");
            Console.WriteLine("PASS native recovery FindRemaining: all16 masks as files/directories, strict full-hint fallback, optional-parent file/missing, malformed/case/residual/second identity snapshot refusals; actual DPAPI missing-file recovery with exact selected roots and entry-based final absence; inert bytes only");
        }
        finally { Directory.Delete(root, true); } // This fixture executes no helper or candidate.
    }
#endif
    static int Main()
    {
        const string id = "0123456789abcdef0123456789abcdef";
        string prefix = "trj-" + id;
        Assert(Select(new[] {"unrelated"}, new string[0]) == null, "empty hints must return absence");
        Assert(Select(new[] {prefix + "-runtime", prefix + "-plugin-state", prefix + "-runtime-state"},
            new[] {"trojaino-local-" + id}) == id, "existing exact identity must be returned without generating a new id");
        Console.WriteLine("PASS absent/unrelated hints and complete exact existing identity; no filesystem writes");
        string[] complete = new[] {prefix + "-runtime", prefix + "-plugin-state", prefix + "-runtime-state"};
        string[] plugin = new[] {"trojaino-local-" + id};
        foreach (string malformed in new[] {"trj-", prefix + "-scratch", prefix + "-source", prefix.ToUpperInvariant() + "-runtime", prefix + "-runtime\n", prefix + "-runtime-state/child"})
            Refuse(new[] {malformed}, plugin);
        foreach (string malformed in new[] {"trojaino-local-", "trojaino-local-" + id.ToUpperInvariant(), "trojaino-local-" + id + "\n"})
            Refuse(complete, new[] {malformed});
        for (int missing = 0; missing < 3; missing++)
        {
            var partial = new List<string>(complete); partial.RemoveAt(missing); Refuse(partial, plugin);
        }
        Refuse(complete, new string[0]); Refuse(new string[0], plugin);
        Refuse(new[] {complete[0], complete[0]}, plugin);
        Refuse(complete, new[] {plugin[0], "trojaino-local-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"});
        Assert(Select(Many(4096), Many(4096)) == null, "exact enumeration budget rejected");
        Refuse(Many(4097), new string[0]); Refuse(new string[0], Many(4097));
        observed = 0; Refuse(GuardedInfinite(), new string[0]); Assert(observed == 4097, "local overflow read count");
        observed = 0; Refuse(new string[0], GuardedInfinite()); Assert(observed == 4097, "skills overflow read count");
        Console.WriteLine("PASS both lazy infinite sources stop on the 4097th name, never read the 4098th");
        bool access = false;
        try { Select(Throws(), new string[0]); } catch (UnauthorizedAccessException) { access = true; }
        Assert(access, "enumeration failure incorrectly became absence");
        Console.WriteLine("PASS partial/orphan/residual/malformed/case-alias/duplicate/multiple refusal; both enumeration budgets; access errors preserved");
        var type = Assembly.GetExecutingAssembly().GetType("Trojaino.Setup.DefaultSetupDiscovery");
        var find = type.GetMethod("Find", BindingFlags.Static | BindingFlags.NonPublic);
        Assert(find != null, "production path-free discovery entry missing");
#if !NETFRAMEWORK
        bool refused = false;
        try { find.Invoke(null, null); }
        catch (TargetInvocationException error) { refused = error.InnerException is PlatformNotSupportedException; }
        Assert(refused, "exact unsupported platform refusal required");
#else
        NativeRecovery();
#endif
        return 0;
    }
}
