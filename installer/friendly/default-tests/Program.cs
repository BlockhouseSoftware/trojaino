using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Diagnostics;
using System.Threading;
using Trojaino.Setup;

internal static class DefaultTests
{
    static void Assert(bool ok, string why) { if (!ok) throw new Exception("ASSERT: " + why); }
    static PairState.Record Install(DefaultSetupPlan plan, CancellationToken cancellation)
    {
        var type = Assembly.GetExecutingAssembly().GetType("Trojaino.Setup.DefaultSetup");
        Assert(type != null, "default plan/parents/controller composition missing");
        var method = type.GetMethod("Install", BindingFlags.NonPublic | BindingFlags.Static);
        Assert(method != null, "default composition entry missing");
        try { return (PairState.Record)method.Invoke(null, new object[] {plan, cancellation}); }
        catch (TargetInvocationException error) { throw error.InnerException; }
    }
    static PairState.Record Discover(DefaultSetupPlan fixture)
    {
        var type = Assembly.GetExecutingAssembly().GetType("Trojaino.Setup.DefaultSetupDiscovery");
        Assert(type != null, "discovery missing");
        var method = type.GetMethod("TestFind", BindingFlags.Static | BindingFlags.NonPublic);
        Assert(method != null, "native discovery fixture seam missing");
        try { return (PairState.Record)method.Invoke(null, new object[] {fixture}); }
        catch (TargetInvocationException error) { throw error.InnerException; }
    }
    static int Main(string[] args)
    {
        Assert(typeof(SharedParents).GetMethod("TestRun", BindingFlags.NonPublic | BindingFlags.Static) == null, "raw parent seam leaked");
        Assert(typeof(SetupController).GetMethod("TestInstall", BindingFlags.NonPublic | BindingFlags.Static) == null, "controller helper injection leaked");
#if !NETFRAMEWORK
        bool refused = false;
        try { Install(null, CancellationToken.None); } catch (PlatformNotSupportedException) { refused = true; }
        Assert(refused, "exact unsupported-platform refusal required");
        Console.WriteLine("PASS default composition production controller/parent seams absent; exact non-Framework refusal; NOT native execution");
#else
        if (args.Length == 3 && args[0] == "--rediscover-remove")
        {
            // Only fixture OS-folder inputs cross processes; no saved component paths or identity.
            var fixture = DefaultSetupPlan.TestCreate(args[1], args[2], null, Guid.NewGuid().ToString("N"));
            var found = Discover(fixture);
            Assert(found != null, "fresh process failed to rediscover existing install");
            PairState.Remove(found);
            Assert(Discover(fixture) == null, "removed install still discovered");
            return 0;
        }
        Assert(args.Length == 0, "unexpected fixture arguments");
        string root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "dc-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root); string local = Path.Combine(root, "local"); Directory.CreateDirectory(local);
        try
        {
            var plan = DefaultSetupPlan.TestCreate(root, local, null, Guid.NewGuid().ToString("N"));
            string[] roots = plan.Roots; string config = Path.Combine(root, ".claude");
            bool cancelled = false;
            try { Install(plan, new CancellationToken(true)); } catch (OperationCanceledException) { cancelled = true; }
            Assert(cancelled && !Directory.Exists(config) && Directory.GetFileSystemEntries(local).Length == 0, "pre-cancel wrote parents/components");
            File.WriteAllText(roots[5], "retain"); bool refused = false;
            try { Install(plan, CancellationToken.None); } catch (InvalidDataException) { refused = true; }
            Assert(refused && !Directory.Exists(config) && File.ReadAllText(roots[5]) == "retain" && Directory.GetFileSystemEntries(local).Length == 1, "last-role conflict wrote parents or changed prior");
            File.Delete(roots[5]);
            Assert(Discover(plan) == null && !Directory.Exists(config), "discovery wrote optional parents");
            File.WriteAllText(config, "keep config file"); byte[] configBytes = File.ReadAllBytes(config); bool configFileRefused = false;
            try { Discover(plan); } catch (InvalidDataException) { configFileRefused = true; }
            Assert(configFileRefused && File.ReadAllBytes(config).SequenceEqual(configBytes), "config file accepted/changed");
            File.Delete(config); Directory.CreateDirectory(config);
            string skillsFolder = Path.Combine(config, "skills");
            Assert(Discover(plan) == null && !Directory.Exists(skillsFolder), "missing skills incorrectly created");
            File.WriteAllText(skillsFolder, "keep skills file"); byte[] skillsBytes = File.ReadAllBytes(skillsFolder); bool skillsFileRefused = false;
            try { Discover(plan); } catch (InvalidDataException) { skillsFileRefused = true; }
            Assert(skillsFileRefused && File.ReadAllBytes(skillsFolder).SequenceEqual(skillsBytes), "skills file accepted/changed");
            File.Delete(skillsFolder); Directory.Delete(config);
            Console.WriteLine("PASS native discovery missing .claude/missing skills zero writes; file at either optional folder refused with exact bytes retained");
            var pair = Install(plan, CancellationToken.None); PairState.Verify(pair);
            var reopened = Discover(DefaultSetupPlan.TestCreate(root, local, null, Guid.NewGuid().ToString("N")));
            Assert(reopened.Runtime.Component.Root == roots[0], "rediscovery invented a new installation");
            string unknown = Path.Combine(roots[5], "unknown"); File.WriteAllText(unknown, "keep");
            bool unknownRefused = false;
            try { Discover(plan); } catch (InvalidDataException) { unknownRefused = true; }
            Assert(unknownRefused && File.ReadAllText(unknown) == "keep", "unknown state accepted or changed");
            File.Delete(unknown);
            string residual = roots[2]; Directory.CreateDirectory(residual);
            bool residualRefused = false;
            try { Discover(plan); } catch (InvalidDataException) { residualRefused = true; }
            Assert(residualRefused && Directory.Exists(residual), "transient residual accepted/deleted");
            Directory.Delete(residual);
            Assert(!Directory.Exists(roots[1]) && !Directory.Exists(roots[2]), "transient inputs remain");
            Assert(pair.Runtime.Component.Root == roots[0] && pair.Plugin.Component.Root == roots[3] && pair.Runtime.State.Root == roots[4] && pair.Plugin.State.Root == roots[5], "different plan/returned ownership");
            var json = new System.Web.Script.Serialization.JavaScriptSerializer();
            var meta = json.Deserialize<System.Collections.Generic.Dictionary<string, object>>(File.ReadAllText(Path.Combine(roots[3], ".claude-plugin", "plugin.json")));
            Assert((string)meta["name"] == plan.Name && (bool)meta["defaultEnabled"] == false, "default-disabled exact identity");
            string python = Path.Combine(roots[0], "python.exe"), entry = Path.Combine(roots[3], "scripts", "preflight.py");
            string hook = File.ReadAllText(Path.Combine(roots[3], "hooks", "hooks.json"));
            Assert(hook.Contains(json.Serialize(python)) && hook.Contains(json.Serialize(entry)), "final literal hook roots");
            string binding = "_EXPECTED_BINDING = ('" + entry.Replace("\\", "\\\\") + "', '" + python.Replace("\\", "\\\\") + "')";
            Assert(File.ReadAllLines(entry).Single(l => l.StartsWith("_EXPECTED_BINDING = ", StringComparison.Ordinal)) == binding, "sealed final binding");
            string[] paths = new[] {roots[0], roots[3], roots[4], roots[5]};
            Assert(paths.All(p => !p.Contains("\"") && !p.EndsWith("\\")), "safe child fixture quoting");
            using (var child = Process.Start(new ProcessStartInfo { FileName = Process.GetCurrentProcess().MainModule.FileName,
                UseShellExecute = false, CreateNoWindow = true, Arguments = "--rediscover-remove \"" + root + "\" \"" + local + "\"" }))
            {
                if (!child.WaitForExit(30000)) { child.Kill(); child.WaitForExit(5000); throw new TimeoutException("remove fixture child timed out"); }
                Assert(child.ExitCode == 0, "fresh process DPAPI remove failed");
            }
            Assert(roots.All(p => !Directory.Exists(p)) && Directory.Exists(Path.Combine(config, "skills")), "components removed/shared parents retained");
            Console.WriteLine("PASS native default plan -> missing shared parents -> actual approved CPython/controller -> verified exact persistent roots, disabled name/literal binding -> fresh-process identity-free rediscovery and DPAPI removal; absent optional folders zero writes, unknown state/residual refusal; pre-cancel and occupied last role zero parent writes; shared parents retained; NOT GUI/activation/Windows11");
        }
        finally { Directory.Delete(root, true); }
#endif
        return 0;
    }
}
