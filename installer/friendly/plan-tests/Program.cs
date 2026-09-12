using System;
using System.IO;
using System.Reflection;
using System.Linq;

internal static class PlanTests
{
    static void Assert(bool ok, string why) { if (!ok) throw new Exception("ASSERT: " + why); }
    static Type Target()
    {
        var type = Assembly.GetExecutingAssembly().GetType("Trojaino.Setup.DefaultSetupPlan");
        Assert(type != null, "read-only known-folder setup plan missing"); return type;
    }
    static object Create(string profile, string local, string config, string id)
    {
        var method = Target().GetMethod("TestCreate", BindingFlags.Static | BindingFlags.NonPublic);
        Assert(method != null, "test-only pure plan seam missing");
        try { return method.Invoke(null, new object[] {profile, local, config, id}); }
        catch (TargetInvocationException error) { throw error.InnerException; }
    }
    static object Property(object plan, string name)
    { return plan.GetType().GetProperty(name, BindingFlags.Instance | BindingFlags.NonPublic).GetValue(plan, null); }
    static void Refuse(string profile, string local, string config, string id)
    {
        bool refused = false;
        try { Create(profile, local, config, id); } catch (InvalidDataException) { refused = true; }
        Assert(refused, "unsafe default-profile plan accepted");
    }
    static int Main()
    {
        const string id = "0123456789abcdef0123456789abcdef";
        const string profile = @"C:\Users\Sig Å";
        const string local = @"D:\Local Data\Sig Å";
        var plan = Create(profile, local, null, id);
        string name = "trojaino-local-" + id;
        Assert((string)Property(plan, "Name") == name, "exact fresh identity");
        var roots = (string[])Property(plan, "Roots");
        var expected = new[] {local + "\\trj-" + id + "-runtime", local + "\\trj-" + id + "-source", local + "\\trj-" + id + "-scratch", profile + "\\.claude\\skills\\" + name, local + "\\trj-" + id + "-runtime-state", local + "\\trj-" + id + "-plugin-state"};
        Assert(roots.SequenceEqual(expected), "exact OS-folder mapping without common-parent creation");
        roots[0] = "mutated";
        Assert(((string[])Property(plan, "Roots")).SequenceEqual(expected), "plan roots leaked mutable state");
        Console.WriteLine("PASS read-only Unicode known-folder mapping, exact identity and immutable six-root snapshot; no native APIs/writes");
        foreach (string bad in new[] {null, "", "relative", @"\\server\share", @"C:\x\..\user", @"C:\Users\Sig\", "C:\\Users\\Sig\n", @"C:\NUL", @"C:\" + new string('a', 230)})
        {
            Refuse(bad, local, null, id); Refuse(profile, bad, null, id);
        }
        foreach (string bad in new[] {null, "", "abc", id.ToUpperInvariant(), id + "\n", "0123456789abcdef0123456789abcdeg", "../elsewhere"}) Refuse(profile, local, null, bad);
        foreach (string config in new[] {" ", @"C:\Other", profile + @"\.claude", "relative"}) Refuse(profile, local, config, id);
        Create(profile, local, "", id);
        Console.WriteLine("PASS missing/unsafe known folders, malformed identity, nonempty override and expanded path budget refusals");
        return 0;
    }
}
