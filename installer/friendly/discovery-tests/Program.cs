using System;
using System.IO;
using System.Reflection;
using System.Collections.Generic;
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
#endif
        return 0;
    }
}
