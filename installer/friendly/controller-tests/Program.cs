using System;
using System.IO;
using System.Linq;
using System.Threading;
using Trojaino.Setup;

internal static class ControllerTests
{
    static void Assert(bool ok, string why) { if (!ok) throw new Exception(why); }
    static string[] Roots(string parent)
    { return new[] {"runtime", "source", "scratch", "trojaino-local-controller-test", "runtime-state", "plugin-state"}.Select(n => Path.Combine(parent, n)).ToArray(); }
    static Bootstrap.Receipt Inert(string final)
    {
        byte[] bytes;
        using (var memory = new System.IO.MemoryStream())
        {
            using (var zip = new System.IO.Compression.ZipArchive(memory, System.IO.Compression.ZipArchiveMode.Create, true))
            using (var stream = zip.CreateEntry("nested/inert.txt").Open())
            { bytes = System.Text.Encoding.UTF8.GetBytes("not executable"); stream.Write(bytes, 0, bytes.Length); }
            var archive = memory.ToArray();
            return Bootstrap.Install(archive, Bootstrap.Hash(archive), new System.Collections.Generic.Dictionary<string,string> {{"nested/inert.txt", Bootstrap.Hash(bytes)}}, final);
        }
    }
    static int Main()
    {
        string parent = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "tj-controller-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(parent);
        try
        {
            var roots = Roots(parent);
            int calls = 0;
            var record = SetupController.TestInstall(roots, "trojaino-local-controller-test", CancellationToken.None,
                (staged, final, name, scratch, token) => {
                    calls++; StagedPayload.Verify(staged); Bootstrap.Verify(scratch);
                    Assert(final == roots[3] && name == "trojaino-local-controller-test", "exact helper binding");
                    return Inert(final); // Inert test only, no trusted-helper claim.
                }, null);
            Assert(calls == 1, "one preparation");
            Assert(!Directory.Exists(roots[1]) && !Directory.Exists(roots[2]), "source and scratch retired");
            PairState.Verify(record);
            var loaded = PairState.Load(roots[0], roots[3], roots[4], roots[5]);
            PairState.Remove(loaded);
            Assert(roots.All(r => !Directory.Exists(r)), "all owned roots removed");
            Console.WriteLine("PASS controller transaction composition with real embedded staging and inert helper; persisted reload/remove; portable codec only");
            foreach (bool released in new[] {true, false})
            {
                var original = new TrustedPreparation.ProcessFailureException(released, new[] {new IOException("primary")});
                Exception failure = null;
                try { SetupController.TestInstall(roots, "trojaino-local-controller-test", CancellationToken.None,
                    (s, f, n, w, t) => { throw original; }, null); }
                catch (Exception e) { failure = e; }
                Assert(object.ReferenceEquals(failure, original) || (failure is AggregateException && ((AggregateException)failure).InnerExceptions.Contains(original)), "primary identity retained");
                Assert(Directory.Exists(roots[0]) == !released && Directory.Exists(roots[1]) == !released && Directory.Exists(roots[2]) == !released, "typed lifetime cleanup: " + released);
                Assert(!Directory.Exists(roots[3]) && !Directory.Exists(roots[4]) && !Directory.Exists(roots[5]), "failure no publication/state");
                if (!released) { Directory.Delete(roots[0], true); Directory.Delete(roots[1], true); Directory.Delete(roots[2], true); } // Test fixture teardown, NOT controller recovery.
            }
            Console.WriteLine("PASS typed released failure cleans owned inputs; unconfirmed lifetime retains every input; primary preserved");
            foreach (string target in new[] {"staged", "scratch", "prepared", "saved", "source-retired", "scratch-retired"})
            {
                var original = new IOException("phase-" + target); Exception failure = null;
                try { SetupController.TestInstall(roots, "trojaino-local-controller-test", CancellationToken.None,
                    (s, f, n, w, t) => Inert(f), phase => { if (phase == target) throw original; }); }
                catch (Exception e) { failure = e; }
                Assert(object.ReferenceEquals(failure, original), "phase failure preserved: " + target);
                Assert(roots.All(r => !Directory.Exists(r)), "phase owned rollback: " + target);
            }
            Console.WriteLine("PASS every post-stage phase fault preserves primary and cleans owned trees");
            foreach (string kind in new[] {"generic", "partial-plugin", "owned-plugin", "saved-state", "multi-cleanup"})
            {
                var original = new IOException("primary-" + kind); Exception failure = null;
                try { SetupController.TestInstall(roots, "trojaino-local-controller-test", CancellationToken.None,
                    (s, f, n, w, t) => {
                        if (kind == "generic") throw original;
                        if (kind == "partial-plugin") {
                            Directory.CreateDirectory(f); File.WriteAllText(Path.Combine(f, "unknown"), "retain");
                            throw new TrustedPreparation.ProcessFailureException(true, new[] {original});
                        }
                        return Inert(f);
                    }, phase => {
                        if (kind == "owned-plugin" && phase == "prepared") { File.WriteAllText(Path.Combine(roots[3], "unknown"), "retain"); throw original; }
                        if (kind == "saved-state" && phase == "saved") { File.WriteAllText(Path.Combine(roots[5], "unknown"), "retain"); throw original; }
                        if (kind == "multi-cleanup" && phase == "prepared") {
                            foreach (int i in new[] {1,2,3}) File.WriteAllText(Path.Combine(roots[i], "unknown"), "retain");
                            throw original;
                        }
                    }); }
                catch (Exception e) { failure = e; }
                Assert(failure != null, "negative failure observed: " + kind);
                Assert(object.ReferenceEquals(failure, original) || (failure is AggregateException && ((AggregateException)failure).Flatten().InnerExceptions.Contains(original)), "all primary retained: " + kind);
                Assert(Directory.Exists(roots[0]), "runtime retained: " + kind);
                if (kind == "generic") Assert(Directory.Exists(roots[1]) && Directory.Exists(roots[2]), "generic lifetime retains all inputs");
                else if (kind != "multi-cleanup") Assert(!Directory.Exists(roots[1]) && !Directory.Exists(roots[2]), "released independent inputs cleaned");
                if (kind == "partial-plugin" || kind == "owned-plugin") Assert(File.ReadAllText(Path.Combine(roots[3], "unknown")) == "retain", "unknown plugin untouched");
                if (kind == "saved-state") Assert(File.ReadAllText(Path.Combine(roots[5], "unknown")) == "retain" && Directory.Exists(roots[3]) && Directory.Exists(roots[4]), "all four retained on pair predelete failure");
                if (kind == "multi-cleanup") {
                    Assert(((AggregateException)failure).InnerExceptions.Count == 4, "original plus each three cleanup failures");
                    foreach (int i in new[] {1,2,3}) Assert(File.ReadAllText(Path.Combine(roots[i], "unknown")) == "retain", "independent unknown retained");
                }
                foreach (string root in roots) if (Directory.Exists(root)) Directory.Delete(root, true); // Fixture teardown only.
            }
            Console.WriteLine("PASS generic lifetime and unreturned/owned unknown plugin retention; all-four persistent refusal; independent cleanup errors preserved");
            using (var cancel = new CancellationTokenSource())
            {
                cancel.Cancel(); bool refused = false;
                try { SetupController.TestInstall(roots, "trojaino-local-controller-test", cancel.Token, (s,f,n,w,t) => { throw new Exception("must not execute"); }, null); }
                catch (OperationCanceledException) { refused = true; }
                Assert(refused && roots.All(r => !Directory.Exists(r)), "pre-stage cancellation zero writes");
            }
            using (var cancel = new CancellationTokenSource())
            {
                bool called = false, refused = false;
                try { SetupController.TestInstall(roots, "trojaino-local-controller-test", cancel.Token, (s,f,n,w,t) => { called = true; return Inert(f); }, p => { if (p == "scratch") cancel.Cancel(); }); }
                catch (OperationCanceledException) { refused = true; }
                Assert(refused && !called && roots.All(r => !Directory.Exists(r)), "pre-helper cancellation rollback without execution");
            }
            using (var cancel = new CancellationTokenSource())
            {
                var committed = SetupController.TestInstall(roots, "trojaino-local-controller-test", cancel.Token, (s,f,n,w,t) => Inert(f), p => { if (p == "prepared") cancel.Cancel(); });
                PairState.Verify(committed); PairState.Remove(committed);
                Assert(roots.All(r => !Directory.Exists(r)), "late cancellation returns valid ownership receipt");
            }
            Console.WriteLine("PASS pre-stage/pre-helper cancellation and documented synchronous commit cutoff");
            foreach (int stateRole in new[] {4,5})
            foreach (string point in new[] {"before", "partial", "after"})
            foreach (bool unknown in new[] {false,true})
            {
                var original = new IOException("state-fault"); Exception failure = null; int reached = 0;
                StateStore.Fault = (phase, target) => {
                    if (phase == point && target == Path.Combine(roots[stateRole], "receipt.bin")) {
                        reached++;
                        if (unknown) File.WriteAllText(Path.Combine(roots[stateRole], "unknown"), "retain state");
                        throw original;
                    }
                };
                try { SetupController.TestInstall(roots, "trojaino-local-controller-test", CancellationToken.None, (s,f,n,w,t) => Inert(f), null); }
                catch (Exception e) { failure = e; }
                finally { StateStore.Fault = null; }
                Assert(reached == 1, "actual inner save phase exercised");
                Assert(object.ReferenceEquals(failure, original) || (failure is AggregateException && ((AggregateException)failure).Flatten().InnerExceptions.Contains(original)), "inner save original retained");
                foreach (int role in new[] {0,1,2,3, stateRole == 4 ? 5 : 4}) Assert(!Directory.Exists(roots[role]), "known components/other state cleaned after inner failure");
                if (unknown) {
                    Assert(File.ReadAllText(Path.Combine(roots[stateRole], "unknown")) == "retain state", "unknown partial state retained");
                    Assert(File.Exists(Path.Combine(roots[stateRole], "receipt.bin")), "owned partial receipt retained alongside unknown state");
                    Directory.Delete(roots[stateRole], true); // Fixture teardown, never production adoption.
                }
                else Assert(!Directory.Exists(roots[stateRole]), "failed owned state cleaned");
            }
            Console.WriteLine("PASS both inner state saves at before/partial/after writes; known rollback, unknown partial state retained, original errors conserved");
            return 0;
        }
        catch (Exception e) { Console.WriteLine("FAIL " + e); return 1; }
        finally { Directory.Delete(parent, true); }
    }
}
