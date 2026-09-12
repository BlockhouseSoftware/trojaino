// Exercises the real account transaction only in isolated OS-folder fixtures.
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using Trojaino.Setup;

internal static class AccountTransactionTests
{
    static void Assert(bool ok, string why) { if (!ok) throw new Exception("ASSERT: " + why); }
    static object Invoke(Type type, string name, params object[] args)
    {
        var method = type.GetMethod(name, BindingFlags.NonPublic | BindingFlags.Static);
        Assert(method != null, "account transaction entry missing: " + name);
        try { return method.Invoke(null, args); }
        catch (TargetInvocationException e) { throw e.InnerException; }
    }
    static int Main(string[] args)
    {
        var type = Assembly.GetExecutingAssembly().GetType("Trojaino.Setup.AccountPreferenceTransaction");
        if (args.Length != 0)
        {
            Assert(args.Length == 3 && args[0] == "--read-status", "unexpected fixture child arguments");
            var childPlan = DefaultSetupPlan.TestCreate(args[1], args[2], null, Guid.NewGuid().ToString("N"));
            object status = Invoke(type, "TestReadRecoveryStatus", childPlan);
            Func<string, object> field = name => status.GetType().GetProperty(name, BindingFlags.Instance | BindingFlags.NonPublic).GetValue(status, null);
            Console.WriteLine(field("State") + "|" + field("OriginalSha256") + "|" + field("CurrentSha256"));
            return 0;
        }
        Assert(type != null, "authenticated journaled account preference transaction is missing");
        Assert(type.GetField("Fault", BindingFlags.Static | BindingFlags.NonPublic) != null && type.GetField("TargetWrites", BindingFlags.Static | BindingFlags.NonPublic) != null, "account transaction temporal fault observation is missing");
        if (Environment.OSVersion.Platform != PlatformID.Win32NT)
        {
            bool refused = false;
            try { Invoke(type, "Apply", "unused", true); }
            catch (PlatformNotSupportedException) { refused = true; }
            Assert(refused, "production transaction did not refuse non-Windows before discovery");
            refused = false;
            try { Invoke(type, "ReadRecoveryStatus"); }
            catch (PlatformNotSupportedException) { refused = true; }
            Assert(refused, "production recovery reader did not refuse non-Windows before discovery");
            Console.WriteLine("PASS production account transaction and recovery reader platform refusal; NOT native evidence"); return 0;
        }
        string root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "account-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        string local = Path.Combine(root, "local"); Directory.CreateDirectory(local);
        bool passed = false;
        try
        {
            var plan = DefaultSetupPlan.TestCreate(root, local, null, Guid.NewGuid().ToString("N"));
            // Real approved helper and DPAPI install, never normal account settings.
            var pair = DefaultSetup.Install(plan, System.Threading.CancellationToken.None);
            string identity = plan.Name + "@skills-dir", path = Path.Combine(root, ".claude", "settings.json");
            var utf8 = new UTF8Encoding(false, true);
            byte[] original = utf8.GetBytes("{\"other\":[1e9999,-0,\"é\\u0061\"],\"enabledPlugins\":{\"" + identity + "\":false}}\r\n");
            using (var file = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None)) file.Write(original, 0, original.Length);
            string nativeId = Bootstrap.Identity(path);
            byte[] expected = AccountPreferenceDocument.Edit(original, identity, true);
            var fault = type.GetField("Fault", BindingFlags.Static | BindingFlags.NonPublic);
            var writes = type.GetField("TargetWrites", BindingFlags.Static | BindingFlags.NonPublic);
            foreach (string phase in new[] { "before-journal-write", "before-journal-flush", "before-journal-readback", "journal-verified", "before-target-write", "target-partial", "before-target-eof", "before-target-flush", "before-target-readback", "target-disposed" })
            {
                writes.SetValue(null, 0); bool reached = false;
                Action<string> inject = delegate(string current) {
                    if (current != phase) return;
                    reached = true; throw new IOException("fixture fault: " + phase);
                };
                fault.SetValue(null, inject);
                Exception failure = null;
                try { Invoke(type, "TestApply", plan, identity, true); }
                catch (AggregateException e) { failure = e; }
                finally { fault.SetValue(null, null); }
                Assert(reached && failure != null && failure.ToString().Contains("fixture fault: " + phase), "fault phase or original error lost: " + phase);
                bool prewrite = phase.StartsWith("before-journal", StringComparison.Ordinal) || phase == "journal-verified" || phase == "before-target-write";
                if (prewrite)
                    Assert((int)writes.GetValue(null) == 0 && File.ReadAllBytes(path).SequenceEqual(original), "journal preparation failure transiently wrote user settings: " + phase);
                else
                    Assert((int)writes.GetValue(null) > 0 && failure.Message.Contains("may be incomplete") && ((byte[])Invoke(type, "TestOriginal", plan)).SequenceEqual(original), "postwrite failure lost protected originals or truthful error: " + phase);
                if (phase == "target-partial")
                {
                    byte[] partial = File.ReadAllBytes(path);
                    int firstDifference = Enumerable.Range(0, Math.Min(original.Length, expected.Length)).First(i => original[i] != expected[i]);
                    byte[] expectedPartial = (byte[])original.Clone();
                    Array.Copy(expected, expectedPartial, firstDifference + 1);
                    Assert(!partial.SequenceEqual(original) && !partial.SequenceEqual(expected)
                        && partial.SequenceEqual(expectedPartial), "partial fault did not preserve a genuinely changed incomplete target");
                }
                Assert(Bootstrap.Identity(path) == nativeId, "failure replaced account file"); PairState.Verify(pair);
                // Synchronous test transaction has returned; no helper is launched by
                // Apply. These are isolated test-owned bytes, not a production restore.
                using (var reset = new FileStream(path, FileMode.Open, FileAccess.Write, FileShare.None)) { reset.Write(original, 0, original.Length); reset.SetLength(original.Length); reset.Flush(true); }
                string recovery = Path.Combine(local, "Trojaino-settings-recovery-v1"), prepared = Path.Combine(recovery, "prepared.bin");
                string[] children = Directory.GetFileSystemEntries(recovery);
                Assert(children.Length <= 1 && children.All(p => p == prepared), "unknown fixture recovery content; retain fixture");
                if (children.Length == 1) File.Delete(prepared);
                Directory.Delete(recovery, false);
            }
            writes.SetValue(null, 0);
            string recoveryRoot = Path.Combine(local, "Trojaino-settings-recovery-v1"), movedRoot = recoveryRoot + "-original";
            string createdId = null, replacementId = null;
            fault.SetValue(null, (Action<string>)delegate(string phase) {
                if (phase != "recovery-created") return;
                createdId = Bootstrap.Identity(recoveryRoot);
                Directory.Move(recoveryRoot, movedRoot); Directory.CreateDirectory(recoveryRoot);
                replacementId = Bootstrap.Identity(recoveryRoot);
            });
            bool rootRefused = false;
            try { Invoke(type, "TestApply", plan, identity, true); }
            catch (AggregateException e) { rootRefused = e.Flatten().InnerExceptions.Any(x => x is InvalidDataException && x.Message.Contains("recovery root")); }
            finally { fault.SetValue(null, null); }
            Assert(createdId != null && replacementId != null, "recovery-root handoff barrier not reached");
            Assert(rootRefused && (int)writes.GetValue(null) == 0 && File.ReadAllBytes(path).SequenceEqual(original), "recovery root substitution was adopted before account mutation");
            Assert(Bootstrap.Identity(movedRoot) == createdId && Bootstrap.Identity(recoveryRoot) == replacementId
                && Directory.GetFileSystemEntries(movedRoot).Length == 0 && Directory.GetFileSystemEntries(recoveryRoot).Length == 0, "root refusal changed either original or replacement");
            Directory.Delete(recoveryRoot, false); Directory.Delete(movedRoot, false); // Empty fixture-created objects only.
            Console.WriteLine("PASS native ten journal/target boundary exceptions retain original evidence; recovery-root substitution refuses before journal/target writes and retains both directory identities; not physical IO or power-loss proof");
            string[] before = Snapshot(root);
            bool wrongIdentity = false;
            try { Invoke(type, "TestApply", plan, "trojaino-local-" + new string('f', 32) + "@skills-dir", true); }
            catch (InvalidDataException) { wrongIdentity = true; }
            Assert(wrongIdentity && Snapshot(root).SequenceEqual(before), "stale identity changed account data");
            Invoke(type, "TestApply", plan, identity, true);
            Assert(File.ReadAllBytes(path).SequenceEqual(expected) && Bootstrap.Identity(path) == nativeId, "journaled edit lost bytes or replaced user settings");
            PairState.Verify(pair);
            byte[] recovered = (byte[])Invoke(type, "TestOriginal", plan);
            Assert(recovered.SequenceEqual(original), "persistent protected journal did not retain exact original bytes");
            string[] noOp = Snapshot(root);
            Invoke(type, "TestApply", plan, identity, true);
            Assert(Snapshot(root).SequenceEqual(noOp), "already requested preference changed files");
            // Until explicit recovery resolution, a second mutation must not consume
            // or silently overwrite the first recoverable original.
            bool pending = false;
            try { Invoke(type, "TestApply", plan, identity, false); }
            catch (AggregateException e) { pending = e.Flatten().InnerExceptions.Any(x => x is InvalidDataException && x.Message.Contains("earlier account change")); }
            Assert(pending && Snapshot(root).SequenceEqual(noOp), "unresolved journal permitted a second mutation");
            PairState.Remove(pair);
            Assert(((byte[])Invoke(type, "TestOriginal", plan)).SequenceEqual(original), "uninstall lost original settings recovery evidence");
            var readStatus = type.GetMethod("TestReadRecoveryStatus", BindingFlags.Static | BindingFlags.NonPublic);
            Assert(readStatus != null, "authenticated read-only account recovery status is missing");
            string[] beforeStatus = Snapshot(root);
            object recoveryStatus;
            using (var readOnlyTarget = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
            using (var readOnlyJournal = new FileStream(Path.Combine(recoveryRoot, "prepared.bin"), FileMode.Open, FileAccess.Read, FileShare.Read))
                recoveryStatus = Invoke(type, "TestReadRecoveryStatus", plan);
            Assert(recoveryStatus != null, "persisted account recovery was reported absent after uninstall");
            Func<string, object> value = name => {
                var property = recoveryStatus.GetType().GetProperty(name, BindingFlags.Instance | BindingFlags.NonPublic);
                Assert(property != null && property.GetSetMethod(true) == null, "recovery snapshot property missing or mutable: " + name);
                return property.GetValue(recoveryStatus, null);
            };
            Assert(value("State").ToString() == "Intended" && (string)value("TargetPath") == path
                && (string)value("RecordedIdentity") == identity && (string)value("OriginalSha256") == Bootstrap.Hash(original)
                && (string)value("CurrentSha256") == Bootstrap.Hash(expected), "recovery snapshot lost authenticated history or current version");
            Assert(Snapshot(root).SequenceEqual(beforeStatus), "read-only recovery status changed account or journal data");
            Action<string> checkState = state => {
                string[] snapshot = Snapshot(root);
                recoveryStatus = Invoke(type, "TestReadRecoveryStatus", plan);
                Assert(value("State").ToString() == state && (string)value("OriginalSha256") == Bootstrap.Hash(original), "wrong recovery classification: " + state);
                Assert(Snapshot(root).SequenceEqual(snapshot), "recovery classification changed files: " + state);
            };
            File.WriteAllBytes(path, utf8.GetBytes("{ordinary later edit"));
            Assert(Bootstrap.Identity(path) == nativeId, "ordinary edit fixture replaced target"); checkState("Changed");
            File.WriteAllBytes(path, original); checkState("Original");
            File.WriteAllBytes(path, expected); checkState("Intended");
            string heldOriginal = path + ".fixture-original";
            File.Move(path, heldOriginal); File.WriteAllBytes(path, expected);
            Assert(Bootstrap.Identity(path) != nativeId, "replacement fixture reused original identity"); checkState("Replaced");
            File.Delete(path); checkState("Missing"); // Remove only the newly-created fixture replacement.
            File.Move(heldOriginal, path); checkState("Intended");
            string unknownRecovery = Path.Combine(recoveryRoot, "unknown.fixture");
            File.WriteAllText(unknownRecovery, "unowned sentinel"); string[] withUnknown = Snapshot(root);
            bool unknownRefused = false;
            try { Invoke(type, "TestReadRecoveryStatus", plan); }
            catch (AggregateException e) { unknownRefused = e.Flatten().InnerExceptions.Any(x => x is InvalidDataException && x.Message.Contains("Unknown or incomplete")); }
            Assert(unknownRefused && Snapshot(root).SequenceEqual(withUnknown), "recovery status adopted or changed unknown record");
            File.Delete(unknownRecovery); // Exact fixture-created sentinel only.
            string[] beforeChild = Snapshot(root);
            Assert(root.IndexOf('"') < 0 && local.IndexOf('"') < 0, "unsafe fixture command quoting");
            var childStart = new System.Diagnostics.ProcessStartInfo {
                FileName = System.Diagnostics.Process.GetCurrentProcess().MainModule.FileName,
                Arguments = "--read-status \"" + root + "\" \"" + local + "\"",
                UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true
            };
            using (var child = System.Diagnostics.Process.Start(childStart))
            {
                var stdout = child.StandardOutput.ReadToEndAsync(); var stderr = child.StandardError.ReadToEndAsync();
                if (!child.WaitForExit(30000))
                {
                    child.Kill(); Assert(child.WaitForExit(5000), "reader child exit unconfirmed; retain fixture");
                    throw new Exception("reader child timeout; retain fixture");
                }
                Assert(System.Threading.Tasks.Task.WaitAll(new System.Threading.Tasks.Task[] { stdout, stderr }, 5000), "reader child streams incomplete; retain fixture");
                Assert(child.ExitCode == 0 && stderr.Result.Length == 0
                    && stdout.Result.Trim() == "Intended|" + Bootstrap.Hash(original) + "|" + Bootstrap.Hash(expected), "fresh-process recovery snapshot failed: " + stderr.Result);
            }
            Assert(Snapshot(root).SequenceEqual(beforeChild), "fresh-process recovery status changed persisted data");
            passed = true;
            Console.WriteLine("PASS native read-only recovery after uninstall: immutable Intended/Original/Changed/Replaced/Missing snapshots, compatible shared-read handles, unknown-record refusal, fresh-process fixed-folder rediscovery, unchanged inventories and IDs; no restore or UI qualification");
            Console.WriteLine("PASS native existing false-to-true journaled lexical edit, unchanged settings ID, authenticated exact original, stale consent refusal, zero-write no-op and second-mutation refusal; original survives uninstall");
        }
        finally
        {
            // Journals may contain protected fixture originals. Retain all failed
            // journeys and successful artifacts for fresh-process recovery tests.
            Console.WriteLine((passed ? "RETAINED verified" : "RETAINED unsuccessful") + " account fixture: " + root);
        }
        return 0;
    }
    static string[] Snapshot(string root)
    {
        return Directory.GetFileSystemEntries(root, "*", SearchOption.AllDirectories).OrderBy(p => p, StringComparer.Ordinal)
            .Select(p => p + "|" + Bootstrap.Identity(p) + "|" + (Directory.Exists(p) ? "dir" : Bootstrap.Hash(File.ReadAllBytes(p)))).ToArray();
    }
}
