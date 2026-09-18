using System;
using System.IO;
using System.Reflection;
using Trojaino.Setup;

internal static class NativeParentTests
{
    static void Assert(bool ok, string why) { if (!ok) throw new Exception("ASSERT: " + why); }
    static void Run(DefaultSetupPlan plan, Action continuation)
    {
        var method = typeof(SharedParents).GetMethod("Run", BindingFlags.NonPublic | BindingFlags.Static);
        Assert(method != null, "native whole-plan parent provisioning missing");
        try { method.Invoke(null, new object[] {plan, continuation}); }
        catch (TargetInvocationException error) { throw error.InnerException; }
    }
#if NETFRAMEWORK
    static DefaultSetupPlan Plan(string root)
    {
        Directory.CreateDirectory(root); Directory.CreateDirectory(Path.Combine(root, "local"));
        return DefaultSetupPlan.TestCreate(root, Path.Combine(root, "local"), null, Guid.NewGuid().ToString("N"));
    }
    static void Refuse(DefaultSetupPlan plan)
    {
        bool refused = false, called = false;
        try { Run(plan, () => { called = true; }); }
        catch (InvalidDataException) { refused = true; }
        catch (IOException) { refused = true; }
        Assert(refused && !called, "unsafe parent preparation continued");
    }
#endif
    static int Main()
    {
        Assert(typeof(SharedParents).GetMethod("TestRun", BindingFlags.NonPublic | BindingFlags.Static) == null, "production parent raw-operation seam present");
#if !NETFRAMEWORK
        bool refused = false;
        try { Run(null, null); } catch (PlatformNotSupportedException) { refused = true; }
        Assert(refused, "exact non-Framework refusal before inputs/probes");
        Console.WriteLine("PASS production parent entry has no raw-operation seam; exact non-Framework refusal; NOT native parent qualification");
#else
        string root = Path.Combine(Path.GetTempPath(), "pr-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            string area = Path.Combine(root, "success"); var plan = Plan(area); bool called = false;
            Run(plan, () => { SetupLocations.Check(plan.Roots, plan.Name); called = true; });
            Assert(called && Directory.Exists(Path.Combine(area, ".claude", "skills")), "actual parent provisioning failed");
            foreach (string destination in plan.Roots) Assert(!Directory.Exists(destination) && !File.Exists(destination), "parent helper wrote component");
            Console.WriteLine("PASS native Framework complete-plan preflight, private missing two-parent creation and continuation joint recheck; zero component writes");
            area = Path.Combine(root, "rollback"); plan = Plan(area); var primary = new InvalidOperationException("native continuation failure"); Exception caught = null;
            try { Run(plan, () => { throw primary; }); } catch (Exception error) { caught = error; }
            Assert(object.ReferenceEquals(caught, primary) && !Directory.Exists(Path.Combine(area, ".claude")), "native known parent rollback");
            area = Path.Combine(root, "existing"); plan = Plan(area); string config = Path.Combine(area, ".claude"); Directory.CreateDirectory(config); string settings = Path.Combine(config, "settings.json"); File.WriteAllText(settings, "preserve");
            Run(plan, () => {}); Assert(File.ReadAllText(settings) == "preserve", "existing settings changed");
            Console.WriteLine("PASS native reverse known-empty rollback and existing configuration preservation");
            for (int role = 0; role < 6; role++)
            {
                area = Path.Combine(root, "occupied" + role); plan = Plan(area); string destination = plan.Roots[role];
                Directory.CreateDirectory(Path.GetDirectoryName(destination)); File.WriteAllText(destination, "retain");
                Refuse(plan); Assert(File.ReadAllText(destination) == "retain", "existing destination changed");
                if (role != 3) Assert(!Directory.Exists(Path.Combine(area, ".claude")), "other occupied role created parents before refusing");
            }
            foreach (string at in new[] {".claude", ".claude/skills"})
            {
                area = Path.Combine(root, "file" + Guid.NewGuid().ToString("N").Substring(0, 4)); plan = Plan(area);
                string file = Path.Combine(area, at.Replace('/', Path.DirectorySeparatorChar)); Directory.CreateDirectory(Path.GetDirectoryName(file)); File.WriteAllText(file, "retain");
                Refuse(plan); Assert(File.ReadAllText(file) == "retain", "parent file changed");
            }
            area = Path.Combine(root, "missing-local"); plan = Plan(area); Directory.Delete(Path.Combine(area, "local")); Refuse(plan);
            Assert(!Directory.Exists(Path.Combine(area, ".claude")), "missing local parent wrote profile config");
            area = Path.Combine(root, "missing-profile"); plan = Plan(area); Directory.Delete(area, true); Refuse(plan); Assert(!Directory.Exists(area), "missing profile recursively created");
            Console.WriteLine("PASS native all-six occupied-destination refusal before parent writes; parent files and missing OS roots retained/refused; no GUI/activation/Windows11 qualification");
        }
        finally { Directory.Delete(root, true); }
#endif
        return 0;
    }
}
