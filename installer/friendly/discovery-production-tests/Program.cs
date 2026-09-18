using System;
using System.IO;
using System.Reflection;
using Trojaino.Setup;
internal static class ProductionDiscoveryTests
{
    static void Assert(bool ok, string why) { if (!ok) throw new Exception("ASSERT: " + why); }
    static int Main()
    {
        foreach (string method in new[] {"TestFind", "TestSelect"})
            Assert(typeof(DefaultSetupDiscovery).GetMethod(method, BindingFlags.Static | BindingFlags.NonPublic) == null, "discovery raw input seam leaked");
        Assert(typeof(DefaultSetupPlan).GetMethod("TestCreate", BindingFlags.Static | BindingFlags.NonPublic) == null, "plan raw input seam leaked");
#if NETFRAMEWORK
        string original = Environment.GetEnvironmentVariable("CLAUDE_CONFIG_DIR");
        try
        {
            Environment.SetEnvironmentVariable("CLAUDE_CONFIG_DIR", "unsupported-fixture-value");
            bool refused = false;
            try { DefaultSetupDiscovery.Find(); } catch (InvalidDataException) { refused = true; }
            Assert(refused, "custom config value must refuse before enumeration");
        }
        finally { Environment.SetEnvironmentVariable("CLAUDE_CONFIG_DIR", original); }
        Console.WriteLine("PASS native production discovery raw seams absent and custom-config value refusal; actual fixture lifecycle tested separately");
#else
        bool refused = false;
        try { DefaultSetupDiscovery.Find(); } catch (PlatformNotSupportedException) { refused = true; }
        Assert(refused, "exact non-Framework platform refusal required");
        Console.WriteLine("PASS production discovery raw seams absent and exact non-Framework refusal; NOT native rediscovery");
#endif
        return 0;
    }
}
