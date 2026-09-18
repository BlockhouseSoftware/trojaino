using System;
using System.IO;
using System.Linq;
using System.Reflection;
using Trojaino.Setup;

internal static class NativePlanTests
{
    static void Assert(bool ok, string why) { if (!ok) throw new Exception("ASSERT: " + why); }
    static DefaultSetupPlan Resolve()
    {
        var method = typeof(DefaultSetupPlan).GetMethod("Resolve", BindingFlags.NonPublic | BindingFlags.Static);
        Assert(method != null, "native known-folder resolver missing");
        try { return (DefaultSetupPlan)method.Invoke(null, null); }
        catch (TargetInvocationException error) { throw error.InnerException; }
    }
    static int Main()
    {
        Assert(typeof(DefaultSetupPlan).GetMethod("TestCreate", BindingFlags.NonPublic | BindingFlags.Static) == null, "production raw folder/identity injection seam");
#if !NETFRAMEWORK
        bool refused = false;
        try { Resolve(); } catch (PlatformNotSupportedException) { refused = true; }
        Assert(refused, "exact non-Framework refusal required before environment/folder probes");
        Console.WriteLine("PASS production plan has no raw-input seam; exact non-Framework platform refusal; not native folder qualification");
#else
        string prior = Environment.GetEnvironmentVariable("CLAUDE_CONFIG_DIR");
        try
        {
            Environment.SetEnvironmentVariable("CLAUDE_CONFIG_DIR", "default-override-refused");
            bool refused = false;
            try { Resolve(); } catch (InvalidDataException) { refused = true; }
            Assert(refused, "native default-profile setup accepted override");
            Environment.SetEnvironmentVariable("CLAUDE_CONFIG_DIR", null);
            string profile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
            string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            var first = Resolve(); var second = Resolve();
            Assert(first.Name != second.Name, "native resolver reused installation identity");
            Assert(first.Roots[3] == profile + "\\.claude\\skills\\" + first.Name, "actual OS profile mapping");
            foreach (int role in new[] {0, 1, 2, 4, 5}) Assert(Path.GetDirectoryName(first.Roots[role]) == local, "actual OS local data mapping");
            foreach (string root in first.Roots.Concat(second.Roots)) Assert(!Directory.Exists(root) && !File.Exists(root), "resolver wrote a destination");
            string[] roots = first.Roots; roots[0] = "changed";
            Assert(first.Roots[0] != "changed", "native plan mutability");
            Console.WriteLine("PASS actual native Framework OS known-folder default-profile mapping; fresh identities; zero destination writes; override refusal and no production raw-input seam; not parent provisioning/GUI/Claude/Windows11");
        }
        finally { Environment.SetEnvironmentVariable("CLAUDE_CONFIG_DIR", prior); }
#endif
        return 0;
    }
}
