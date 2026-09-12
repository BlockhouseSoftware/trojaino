// Developer-only native preparation feasibility. NOT an installer controller.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using Trojaino.Setup;

internal static class PreparationTests
{
    static void Assert(bool ok, string why) { if (!ok) throw new InvalidDataException(why); }
    static string Quote(string value)
    {
        Assert(!string.IsNullOrEmpty(value) && value.IndexOfAny(new[] {'"', '\r', '\n', '\0'}) < 0 && !value.EndsWith("\\"), "unsafe developer argument");
        return "\"" + value + "\"";
    }
    static byte[] ReadBounded(Stream input, int limit)
    {
        using (var output = new MemoryStream())
        {
            var buffer = new byte[8192]; int count;
            while ((count = input.Read(buffer, 0, buffer.Length)) > 0)
            {
                Assert(output.Length + count <= limit, "helper output budget exceeded");
                output.Write(buffer, 0, count);
            }
            return output.ToArray();
        }
    }
    static byte[] RunPlan(string python, string helper, string final, string name, string scratch)
    {
        var start = new ProcessStartInfo {
            FileName = python,
            Arguments = "-I -S -B " + Quote(helper) + " " + Quote(final) + " --personal-plugin-name " + Quote(name) + " --plan",
            UseShellExecute = false, CreateNoWindow = true,
            RedirectStandardOutput = true, RedirectStandardError = true,
            RedirectStandardInput = true, WorkingDirectory = scratch
        };
        start.EnvironmentVariables.Clear();
        start.EnvironmentVariables["SystemRoot"] = Environment.GetFolderPath(Environment.SpecialFolder.Windows);
        start.EnvironmentVariables["TEMP"] = scratch;
        start.EnvironmentVariables["TMP"] = scratch;
        using (var process = new Process { StartInfo = start })
        {
            Assert(process.Start(), "approved helper did not start");
            process.StandardInput.Close();
            var output = Task.Run(() => ReadBounded(process.StandardOutput.BaseStream, 16 * 1024 * 1024));
            var error = Task.Run(() => ReadBounded(process.StandardError.BaseStream, 64 * 1024));
            var timer = Stopwatch.StartNew();
            try
            {
                while (!process.WaitForExit(50))
                {
                    Assert(!output.IsFaulted && !error.IsFaulted, "helper stream failure");
                    Assert(timer.ElapsedMilliseconds < 60000, "helper timed out");
                }
                Assert(Task.WaitAll(new Task[] {output, error}, 5000), "helper stream EOF timeout");
                Assert(process.ExitCode == 0, "approved helper failed: " + Encoding.UTF8.GetString(error.Result));
                Assert(error.Result.Length == 0, "unexpected helper stderr");
                return output.Result;
            }
            finally
            {
                if (!process.HasExited) { process.Kill(); Assert(process.WaitForExit(5000), "helper did not stop"); }
            }
        }
    }
    static int Main()
    {
        if (Environment.OSVersion.Platform != PlatformID.Win32NT) { Console.WriteLine("FAIL native Windows required"); return 1; }
        string parent = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "trojaino-plan-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(parent);
        try
        {
            string runtime = Path.Combine(parent, "runtime"), source = Path.Combine(parent, "source");
            string scratch = Path.Combine(parent, "scratch"); Directory.CreateDirectory(scratch);
            string name = "trojaino-local-native-plan-test", final = Path.Combine(parent, name);
            var pair = StagedPayload.Install(runtime, source);
            StagedPayload.Verify(pair);
            string python = Path.Combine(runtime, "python.exe");
            string helper = Path.Combine(source, "trojaino-source", "scripts", "prepare_preflight_plugin.py");
            byte[] plan = RunPlan(python, helper, final, name, scratch);
            Assert(!Directory.Exists(final), "plan must not publish final plugin");
            StagedPayload.Verify(pair); // -B must leave every authenticated input byte unchanged.
            var files = new Dictionary<string, byte[]>(StringComparer.Ordinal);
            using (var memory = new MemoryStream(plan))
            using (var zip = new ZipArchive(memory, ZipArchiveMode.Read))
                foreach (var entry in zip.Entries)
                    using (var input = entry.Open()) files.Add(entry.FullName, ReadBounded(input, 16 * 1024 * 1024));
            var json = new JavaScriptSerializer { MaxJsonLength = 16 * 1024 * 1024 };
            var pins = json.Deserialize<Dictionary<string, string>>(Encoding.UTF8.GetString(files["MANIFEST.sha256.json"]));
            Assert(pins.Count + 1 == files.Count && !pins.ContainsKey("MANIFEST.sha256.json"), "exact rendered inventory");
            foreach (var pin in pins) Assert(files.ContainsKey(pin.Key) && Bootstrap.Hash(files[pin.Key]) == pin.Value, "rendered byte digest: " + pin.Key);
            var plugin = json.Deserialize<Dictionary<string, object>>(Encoding.UTF8.GetString(files[".claude-plugin/plugin.json"]));
            Assert((string)plugin["name"] == name && (bool)plugin["defaultEnabled"] == false, "disabled distinct personal identity");
            string hook = Encoding.UTF8.GetString(files["hooks/hooks.json"]);
            Assert(hook.Contains(json.Serialize(python)) && hook.Contains(json.Serialize(Path.Combine(final, "scripts", "preflight.py"))), "literal final hook paths");
            Assert(files.ContainsKey("LICENSE") && files.ContainsKey("scripts/preflight.py"), "license and sealed entry preserved");
            string entryText = Encoding.UTF8.GetString(files["scripts/preflight.py"]);
            // This developer fixture uses known quote-free paths, not a general Python literal encoder.
            Assert(final.IndexOf('\'') < 0 && python.IndexOf('\'') < 0, "quote-free native test fixture required");
            string expectedBinding = "_EXPECTED_BINDING = ('" + Path.Combine(final, "scripts", "preflight.py").Replace("\\", "\\\\") + "', '" + python.Replace("\\", "\\\\") + "')";
            var bindings = entryText.Split('\n').Where(line => line.StartsWith("_EXPECTED_BINDING = ", StringComparison.Ordinal)).ToArray();
            Assert(bindings.Length == 1 && bindings[0] == expectedBinding, "exact sealed entry and interpreter binding");
            // Authenticated transformation result, test-only publication at disposable final path.
            pins.Add("MANIFEST.sha256.json", Bootstrap.Hash(files["MANIFEST.sha256.json"]));
            var installed = Bootstrap.Install(plan, Bootstrap.Hash(plan), pins, final);
            foreach (var file in files)
                Assert(File.ReadAllBytes(Path.Combine(final, file.Key)).SequenceEqual(file.Value), "exact final prepared bytes");
            Bootstrap.Verify(installed); Bootstrap.Remove(installed);
            StagedPayload.Remove(pair);
            Assert(!Directory.Exists(final) && !Directory.Exists(runtime) && !Directory.Exists(source), "owned native preparation trees removed");
            Console.WriteLine("PASS approved CPython3.14.7 native --plan: " + files.Count + " rendered files, all digests and final bytes, disabled identity, literal hooks, Verify/Remove; approved runtime EXECUTED, no candidate execution or Claude activation");
            return 0;
        }
        catch (Exception e) { Console.WriteLine("FAIL " + e); return 1; }
        finally { Directory.Delete(parent, true); } // Only this developer harness's disposable root.
    }
}
