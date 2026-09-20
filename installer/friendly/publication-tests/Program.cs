// Portable test-only injected output. Never a production trust entry point.
using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Text;
using Trojaino.Setup;

internal static class PublicationTests
{
    static void Assert(bool ok, string why) { if (!ok) throw new Exception(why); }
    static Dictionary<string, byte[]> Files()
    {
        var files = new Dictionary<string, byte[]>(StringComparer.Ordinal);
        foreach (string name in new[] { ".claude-plugin/plugin.json", "LICENSE", "README.md", "hooks/hooks.json", "scripts/preflight.py", "skills/scan/SKILL.md" })
            files.Add(name, Encoding.UTF8.GetBytes("inert fixture: " + name));
        Manifest(files);
        return files;
    }
    static void Manifest(Dictionary<string, byte[]> files)
    {
        string text = "{\n" + string.Join(",\n", files.Where(p => p.Key != "MANIFEST.sha256.json").OrderBy(p => p.Key, StringComparer.Ordinal)
            .Select(p => "  \"" + p.Key + "\": \"" + Bootstrap.Hash(p.Value) + "\"")) + "\n}\n";
        files["MANIFEST.sha256.json"] = Encoding.UTF8.GetBytes(text);
    }
    static byte[] Archive(Dictionary<string, byte[]> files, Func<string, string> rename = null, int attributes = unchecked((int)0x81a40000))
    {
        using (var memory = new MemoryStream())
        {
            using (var zip = new ZipArchive(memory, ZipArchiveMode.Create, true))
                foreach (var file in files)
                {
                    var entry = zip.CreateEntry(rename == null ? file.Key : rename(file.Key)); entry.ExternalAttributes = attributes;
                    using (var output = entry.Open()) output.Write(file.Value, 0, file.Value.Length);
                }
            return memory.ToArray();
        }
    }
    static Bootstrap.Receipt Publish(byte[] bytes, string final)
    {
        var method = typeof(TrustedPreparation).GetMethod("TestPublish", BindingFlags.Static | BindingFlags.NonPublic);
        Assert(method != null, "Missing authenticated-output publication boundary");
        try { return (Bootstrap.Receipt)method.Invoke(null, new object[] {bytes, final}); }
        catch (TargetInvocationException e) { throw e.InnerException; }
    }
    static void Reject(byte[] bytes, string final, string label)
    {
        bool refused = false;
        try { Publish(bytes, final); } catch (InvalidDataException) { refused = true; }
        Assert(refused, label + " was accepted");
        Assert(!Directory.Exists(final), label + " created final tree");
        Console.WriteLine("PASS refused before writes: " + label);
    }
    static int Main()
    {
        Bootstrap.AfterWrite = null; Bootstrap.DuringWrite = null;
        string parent = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "trojaino-publication-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(parent);
        try
        {
            string final = Path.Combine(parent, "trojaino-local-publication-test");
            var files = Files(); var receipt = Publish(Archive(files), final);
            foreach (var file in files) Assert(File.ReadAllBytes(Path.Combine(final, file.Key)).SequenceEqual(file.Value), "exact published bytes: " + file.Key);
            Bootstrap.Verify(receipt); Bootstrap.Remove(receipt);
            Assert(!Directory.Exists(final), "owned publication removed");
            Console.WriteLine("PASS exact8-file output publication and owned Verify/Remove (test-only inert bytes)");
            var missing = Files(); missing.Remove("LICENSE"); Manifest(missing);
            Reject(Archive(missing), final, "missing license even with consistent manifest");
            var stale = Files(); stale["README.md"] = Encoding.UTF8.GetBytes("changed after manifest");
            Reject(Archive(stale), final, "stale manifest digest");
            var extra = Files(); extra.Add("extra.txt", new byte[] {1}); Manifest(extra);
            Reject(Archive(extra), final, "extra member");
            foreach (string alias in new[] { "README.md", "readme.md", "../LICENSE", "LICENSE:stream", "unknown.txt" })
                Reject(Archive(Files(), key => key == "LICENSE" ? alias : key), final, "renamed license " + alias);
            foreach (int attr in new[] { 0x10, 0x8, 0x400, unchecked((int)0xa1a40000), unchecked((int)0x41ed0000), unchecked((int)0x81a40010) })
                Reject(Archive(Files(), null, attr), final, "nonregular attributes " + attr);
            var huge = Files(); huge["scripts/preflight.py"] = new byte[8 * 1024 * 1024 + 1]; Manifest(huge);
            Reject(Archive(huge), final, "per-file expanded budget");
            huge = Files(); huge["scripts/preflight.py"] = new byte[8 * 1024 * 1024]; huge["README.md"] = new byte[8 * 1024 * 1024]; Manifest(huge);
            Reject(Archive(huge), final, "total expanded budget");
            Reject(new byte[16 * 1024 * 1024 + 1], final, "compressed budget before ZIP parser");
            Reject(null, final, "null output"); Reject(new byte[0], final, "empty output");
            Reject(new byte[] {1,2,3}, final, "malformed ZIP");
            files = Files(); receipt = Publish(Archive(files), final);
            bool existingDenied = false;
            try { Publish(Archive(Files()), final); } catch (System.ComponentModel.Win32Exception) { existingDenied = true; }
            Assert(existingDenied, "existing final accepted");
            foreach (var file in files) Assert(File.ReadAllBytes(Path.Combine(final, file.Key)).SequenceEqual(file.Value), "existing bytes preserved");
            Bootstrap.Verify(receipt); Bootstrap.Remove(receipt);
            Console.WriteLine("PASS existing destination refused with every prior byte preserved");
            foreach (bool partial in new[] {false, true})
            {
                Action<string> fail = path => { throw new IOException("injected publication write failure"); };
                if (partial) Bootstrap.DuringWrite = fail; else Bootstrap.AfterWrite = fail;
                bool failed = false;
                try { Publish(Archive(Files()), final); } catch (IOException e) { failed = e.Message == "injected publication write failure"; }
                finally { Bootstrap.AfterWrite = null; Bootstrap.DuringWrite = null; }
                Assert(failed && !Directory.Exists(final), "owned partial publication rollback");
                Console.WriteLine("PASS owned write rollback partial=" + partial);
            }
            Bootstrap.AfterWrite = path => { File.WriteAllText(Path.Combine(final, "unknown.txt"), "retain unknown bytes"); throw new IOException("injected unknown content"); };
            bool retained = false;
            try { Publish(Archive(Files()), final); } catch (AggregateException e) { retained = e.InnerExceptions.Count == 2; }
            finally { Bootstrap.AfterWrite = null; }
            Assert(retained && File.ReadAllText(Path.Combine(final, "unknown.txt")) == "retain unknown bytes", "unknown content must survive cleanup refusal with both errors");
            Console.WriteLine("PASS unknown content retained and original plus cleanup error preserved");
            Directory.Delete(final, true); // Test-only fixture cleanup; never production logic.
            var install = typeof(TrustedPreparation).GetMethod("Install", BindingFlags.NonPublic | BindingFlags.Static);
            Assert(install != null, "Missing production authenticated Install entry point");
            if (Environment.OSVersion.Platform != PlatformID.Win32NT)
            {
                bool denied = false;
                try { install.Invoke(null, new object[] {null, final, Path.GetFileName(final), null, System.Threading.CancellationToken.None}); }
                catch (TargetInvocationException e) { denied = e.InnerException is PlatformNotSupportedException; }
                Assert(denied && !Directory.Exists(final), "production publication must refuse non-Windows");
                Console.WriteLine("PASS production Install refuses non-Windows before writes; native integration NOT executed");
            }
            return 0;
        }
        catch (Exception e) { Console.WriteLine("FAIL " + e); return 1; }
        finally { Bootstrap.AfterWrite = null; Bootstrap.DuringWrite = null; Directory.Delete(parent, true); }
    }
}
