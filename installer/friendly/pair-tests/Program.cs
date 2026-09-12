using System;
using System.IO;
using System.IO.Compression;
using System.Collections.Generic;
using System.Reflection;
using Trojaino.Setup;
class Program
{
    static void Check(bool ok, string why) { if (!ok) throw new Exception(why); }
    static object Call(string method, params object[] args)
    {
        var type = typeof(Bootstrap).Assembly.GetType("Trojaino.Setup.PairState");
        Check(type != null, "Missing pair persistent lifecycle");
        var entry = type.GetMethod(method, BindingFlags.Static | BindingFlags.NonPublic);
        Check(entry != null, "Missing pair " + method);
        try { return entry.Invoke(null, args); }
        catch (TargetInvocationException e) { throw e.InnerException; }
    }
    static void Refuse(Action action)
    {
        try { action(); }
        catch (Exception e) { if (e is IOException || e is InvalidDataException || e is AggregateException || e is System.ComponentModel.Win32Exception) return; throw; }
        throw new Exception("Unsafe pair operation accepted");
    }
    static Bootstrap.Receipt Component(string root)
    {
        byte[] bytes = new byte[] { 1, 2, 3, 4 }, archive;
        using (var memory = new MemoryStream())
        {
            using (var zip = new ZipArchive(memory, ZipArchiveMode.Create, true))
            using (var output = zip.CreateEntry("nested/owned.bin").Open()) output.Write(bytes, 0, bytes.Length);
            archive = memory.ToArray();
        }
        return Bootstrap.Install(archive, Bootstrap.Hash(archive), new Dictionary<string, string> { { "nested/owned.bin", Bootstrap.Hash(bytes) } }, root);
    }
    static void Main()
    {
        string temp = Path.Combine(Environment.OSVersion.Platform == PlatformID.Win32NT ? Path.GetTempPath() : "/private/tmp", "trojaino-pair-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(temp);
        try
        {
            string runtime = Path.Combine(temp, "runtime"), plugin = Path.Combine(temp, "plugin"), rs = Path.Combine(temp, "runtime-state"), ps = Path.Combine(temp, "plugin-state");
            var r = Component(runtime); var p = Component(plugin);
            string[] roots = new[] { runtime, plugin, rs, ps };
            Call("Locations", new object[] { roots });
            for (int i = 0; i < roots.Length; i++)
                for (int j = 0; j < roots.Length; j++)
                    if (i != j)
                        foreach (bool nested in new[] { false, true })
                        {
                            var aliases = (string[])roots.Clone();
                            aliases[i] = roots[j] + (nested ? Path.DirectorySeparatorChar + "child" : "");
                            Refuse(() => Call("Locations", new object[] { aliases }));
                        }
            int writes = 0;
            StateStore.Fault = (phase, target) => { if (phase == "before") writes++; };
            try {
                Refuse(() => Call("Save", r, p, rs, rs));
                Refuse(() => Call("Save", r, p, Path.Combine(plugin, "child"), ps));
                Refuse(() => Call("Save", r, p, rs, Path.Combine(runtime, "child")));
                Refuse(() => Call("Save", r, p, temp, ps));
                Refuse(() => Call("Save", r, p, rs, temp));
            }
            finally { StateStore.Fault = null; }
            Check(writes == 0 && !Directory.Exists(rs), "Overlapping pair wrote state before refusal");
            string pluginFile = Path.Combine(plugin, "nested", "owned.bin");
            byte[] original = File.ReadAllBytes(pluginFile);
            File.WriteAllBytes(pluginFile, new byte[] { 4, 3, 2, 1 });
            writes = 0; StateStore.Fault = (phase, target) => { if (phase == "before") writes++; };
            try { Refuse(() => Call("Save", r, p, rs, ps)); }
            finally { StateStore.Fault = null; }
            Check(writes == 0, "Invalid second component was not refused before state writes");
            File.WriteAllBytes(pluginFile, original);
            Directory.CreateDirectory(ps); File.WriteAllText(Path.Combine(ps, "prior"), "retain");
            Refuse(() => Call("Save", r, p, rs, ps));
            Check(!Directory.Exists(rs), "First state not rolled back after second-state failure");
            Check(File.ReadAllText(Path.Combine(ps, "prior")) == "retain", "Prior state altered");
            Bootstrap.Verify(r); Bootstrap.Verify(p);
            Directory.Delete(ps, true); // Disposable fixture.
            foreach (bool unknownSecond in new[] { false, true })
            {
                StateStore.Fault = (phase, target) => {
                    if (phase == "after" && target == Path.Combine(ps, "receipt.bin"))
                    {
                        File.WriteAllText(Path.Combine(rs, "unknown"), "retain runtime state");
                        if (unknownSecond)
                        {
                            File.WriteAllText(Path.Combine(ps, "unknown"), "retain plugin state");
                            throw new IOException("injected second state failure");
                        }
                    }
                };
                AggregateException errors = null;
                try { Call("Save", r, p, rs, ps); }
                catch (AggregateException e) { errors = e; }
                finally { StateStore.Fault = null; }
                Check(errors != null, "Unknown state cleanup failures lost");
                var all = errors.Flatten().InnerExceptions;
                Check(all.Count == (unknownSecond ? 3 : 2), "Original plus each cleanup error not retained");
                Check(File.ReadAllText(Path.Combine(rs, "unknown")) == "retain runtime state", "Unknown runtime state deleted");
                Check(Directory.Exists(ps) == unknownSecond, "Known second state rollback incorrect");
                if (unknownSecond) Check(File.ReadAllText(Path.Combine(ps, "unknown")) == "retain plugin state", "Unknown second state deleted");
                Bootstrap.Verify(r); Bootstrap.Verify(p);
                Directory.Delete(rs, true); if (Directory.Exists(ps)) Directory.Delete(ps, true); // Disposable fixtures only.
            }
            Call("Save", r, p, rs, ps);
            Refuse(() => Call("Load", runtime, runtime, rs, rs));
            var single = StateStore.Load(runtime, rs);
            Refuse(() => Call("Verify", new PairState.Record(single, single)));
            var loaded = Call("Load", runtime, plugin, rs, ps);
            foreach (string tree in new[] { runtime, plugin, rs, ps })
            {
                string unknown = Path.Combine(tree, "unknown"); File.WriteAllText(unknown, "retain");
                Refuse(() => Call("Load", runtime, plugin, rs, ps));
                Refuse(() => Call("Remove", loaded));
                Check(File.ReadAllText(unknown) == "retain" && File.Exists(Path.Combine(rs, "receipt.bin"))
                    && File.Exists(Path.Combine(ps, "receipt.bin")), "Pair predelete refusal altered state");
                if (tree != runtime) Bootstrap.Verify(r);
                if (tree != plugin) Bootstrap.Verify(p);
                File.Delete(unknown); Bootstrap.Verify(r); Bootstrap.Verify(p);
            }
            Call("Remove", loaded);
            Check(!Directory.Exists(runtime) && !Directory.Exists(plugin) && !Directory.Exists(rs) && !Directory.Exists(ps), "Pair removal incomplete");
            Console.WriteLine("PASS two nonempty owned components persistent pair reload/removal; test-only codec NOT DPAPI");
        }
        finally { Directory.Delete(temp, true); } // Disposable test fixture only.
    }
}
