using System;
using System.IO;
using System.Reflection;

internal static class ParentTests
{
    static void Assert(bool ok, string why) { if (!ok) throw new Exception("ASSERT: " + why); }
    static void Run(string[] missing, Action gate, Action<string> afterCreate, Action continuation)
    {
        var type = Assembly.GetExecutingAssembly().GetType("Trojaino.Setup.SharedParents");
        Assert(type != null, "shared-parent provisioner missing");
        var method = type.GetMethod("TestRun", BindingFlags.Static | BindingFlags.NonPublic);
        Assert(method != null, "test-only parent transaction seam missing");
        try { method.Invoke(null, new object[] {missing, gate, afterCreate, continuation}); }
        catch (TargetInvocationException error) { throw error.InnerException; }
    }
    static string Fresh(string root) { string p = Path.Combine(root, Guid.NewGuid().ToString("N")); Directory.CreateDirectory(p); return p; }
    static int Main()
    {
        string root = Path.Combine(Environment.CurrentDirectory, "parent-tests-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            string area = Fresh(root), config = Path.Combine(area, ".claude"), skills = Path.Combine(config, "skills");
            bool called = false;
            Run(new[] {config, skills}, () => Assert(!Directory.Exists(config), "gate after writes"), null,
                () => { Assert(Directory.Exists(skills), "continuation missing parents"); called = true; });
            Assert(called && Directory.Exists(config) && Directory.Exists(skills), "success must retain shared parents");
            Console.WriteLine("PASS actual private exclusive two-parent creation before continuation; success retains shared parents");
            area = Fresh(root); config = Path.Combine(area, ".claude"); skills = Path.Combine(config, "skills");
            var primary = new InvalidOperationException("continuation failed");
            Exception caught = null;
            try { Run(new[] {config, skills}, () => {}, null, () => { throw primary; }); }
            catch (Exception error) { caught = error; }
            Assert(object.ReferenceEquals(caught, primary), "primary exception changed");
            Assert(!Directory.Exists(config), "known empty parents not rolled back child before parent");
            Console.WriteLine("PASS known empty parent rollback in reverse order; original failure identity preserved");
            area = Fresh(root); config = Path.Combine(area, ".claude"); skills = Path.Combine(config, "skills");
            Directory.CreateDirectory(config); string settings = Path.Combine(config, "settings.json"); File.WriteAllText(settings, "unchanged settings");
            caught = null;
            try { Run(new[] {skills}, () => {}, null, () => { throw primary; }); } catch (Exception error) { caught = error; }
            Assert(object.ReferenceEquals(caught, primary) && !Directory.Exists(skills) && File.ReadAllText(settings) == "unchanged settings", "existing parent modified/adopted");
            called = false; caught = null;
            try { Run(new[] {skills}, () => { throw primary; }, null, () => { called = true; }); } catch (Exception error) { caught = error; }
            Assert(object.ReferenceEquals(caught, primary) && !called && !Directory.Exists(skills), "failed gate wrote or continued");
            Console.WriteLine("PASS existing parent bytes preserved and prewrite gate failure has zero creation/continuation");
            for (int faultRole = 0; faultRole < 2; faultRole++)
            {
                area = Fresh(root); config = Path.Combine(area, ".claude"); skills = Path.Combine(config, "skills");
                string unknown = Path.Combine(faultRole == 0 ? config : skills, "unknown"); caught = null;
                try { Run(new[] {config, skills}, () => {}, null, () => { File.WriteAllText(unknown, "retain"); throw primary; }); } catch (Exception error) { caught = error; }
                var aggregate = caught as AggregateException;
                Assert(aggregate != null && object.ReferenceEquals(aggregate.InnerExceptions[0], primary), "unknown rollback masked original error");
                Assert(aggregate.InnerExceptions.Count == (faultRole == 0 ? 2 : 3), "not every cleanup failure retained");
                Assert(File.ReadAllText(unknown) == "retain", "unknown content removed");
                Assert(Directory.Exists(skills) == (faultRole == 1), "known empty child cleanup skipped");
            }
            Console.WriteLine("PASS unknown content in either parent retained; reverse cleanup attempted; all errors preserved");
            area = Fresh(root); config = Path.Combine(area, ".claude"); skills = Path.Combine(config, "skills"); caught = null; called = false;
            try { Run(new[] {config, skills}, () => {}, path => { if (path == config) { Directory.CreateDirectory(skills); File.WriteAllText(Path.Combine(skills, "unreturned"), "retain"); } }, () => { called = true; }); } catch (Exception error) { caught = error; }
            Assert(caught is AggregateException && !called && File.ReadAllText(Path.Combine(skills, "unreturned")) == "retain", "exclusive collision adopted or deleted unreturned child");
            area = Fresh(root); config = Path.Combine(area, ".claude"); skills = Path.Combine(config, "skills"); string moved = Path.Combine(area, "original"); caught = null;
            try { Run(new[] {config}, () => {}, null, () => { Directory.Move(config, moved); Directory.CreateDirectory(config); throw primary; }); } catch (Exception error) { caught = error; }
            Assert(caught is AggregateException && Directory.Exists(config) && Directory.Exists(moved), "replaced same-empty directory adopted/deleted");
            Console.WriteLine("PASS exclusive collision/unreturned child and same-empty replacement refusal; no disk-tree adoption");
        }
        finally { Directory.Delete(root, true); }
        return 0;
    }
}
