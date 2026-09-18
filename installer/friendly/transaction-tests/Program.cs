// Developer-only real payload transaction fault injection. Never execute archive content.
using System;
using System.IO;
using System.Linq;
using Trojaino.Setup;

internal static class TransactionTests
{
    static void Assert(bool ok, string message) { if (!ok) throw new Exception("ASSERT: " + message); }
    static void FinalPairIntegrity(string parent)
    {
        string runtime = Path.Combine(parent, "runtime"), source = Path.Combine(parent, "source");
        bool fired = false;
        Bootstrap.AfterWrite = path => {
            if (!fired && path.StartsWith(source + Path.DirectorySeparatorChar, StringComparison.Ordinal))
            {
                fired = true;
                File.WriteAllText(Path.Combine(runtime, "unexpected.txt"), "preserve");
            }
        };
        Exception failure = null;
        try { StagedPayload.Install(runtime, source); } catch (Exception e) { failure = e; }
        finally { Bootstrap.AfterWrite = null; }
        Assert(fired, "post-runtime change injected during second stage");
        Assert(failure is AggregateException, "must not return an already-invalid pair; report verification failure and rollback refusal");
        var errors = ((AggregateException)failure).Flatten().InnerExceptions;
        Assert(errors.Count == 2 && errors.All(e => e is InvalidDataException), "original integrity failure plus runtime cleanup refusal preserved");
        Assert(!Directory.Exists(source), "valid owned second stage cleaned up");
        Assert(File.ReadAllText(Path.Combine(runtime, "unexpected.txt")) == "preserve" && File.Exists(Path.Combine(runtime, "python.exe")), "unknown runtime tree entirely retained");
        Console.WriteLine("PASS FinalPairIntegrity: final verification fails; owned source removed; unknown runtime retained with both errors");
    }
    static void StageFailure(string parent, bool secondStage, bool partial, bool unknownSource, bool unknownRuntime)
    {
        string runtime = Path.Combine(parent, "runtime"), source = Path.Combine(parent, "source");
        bool fired = false;
        Action<string> inject = path => {
            string stage = secondStage ? source : runtime;
            if (!fired && path.StartsWith(stage + Path.DirectorySeparatorChar, StringComparison.Ordinal))
            {
                fired = true;
                if (unknownSource) File.WriteAllText(Path.Combine(source, "unexpected.txt"), "source preserve");
                if (unknownRuntime) File.WriteAllText(Path.Combine(runtime, "unexpected.txt"), "runtime preserve");
                throw new IOException("injected stage failure");
            }
        };
        if (partial) Bootstrap.DuringWrite = inject; else Bootstrap.AfterWrite = inject;
        Exception failure = null;
        try { StagedPayload.Install(runtime, source); } catch (Exception e) { failure = e; }
        finally { Bootstrap.AfterWrite = null; Bootstrap.DuringWrite = null; }
        Assert(fired && failure != null, "stage write fault must fire");
        if (unknownSource || unknownRuntime)
        {
            Assert(failure is AggregateException, "original failure and cleanup refusal reported");
            var errors = ((AggregateException)failure).Flatten().InnerExceptions;
            Assert(errors.Count == 2 && errors.Any(e => e is IOException && e.Message == "injected stage failure")
                && errors.Any(e => e is InvalidDataException), "both specific failures preserved");
        }
        else Assert(failure is IOException && failure.Message == "injected stage failure", "original write failure rethrown");
        Assert(Directory.Exists(runtime) == unknownRuntime, "only unknown runtime retained");
        Assert(Directory.Exists(source) == unknownSource, "only unknown source retained");
        if (unknownRuntime) Assert(File.ReadAllText(Path.Combine(runtime, "unexpected.txt")) == "runtime preserve", "runtime unknown bytes preserved");
        if (unknownSource) Assert(File.ReadAllText(Path.Combine(source, "unexpected.txt")) == "source preserve", "source unknown bytes preserved");
        Console.WriteLine("PASS StageFailure: second=" + secondStage + "; partial=" + partial + "; unknown-source=" + unknownSource + "; unknown-runtime=" + unknownRuntime);
    }
    static int Main()
    {
        string parent = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "trojaino-transaction-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(parent);
        try
        {
            string final = Path.Combine(parent, "final"); Directory.CreateDirectory(final);
            FinalPairIntegrity(final);
            int count = 0;
            foreach (bool second in new[] {false, true})
                foreach (bool partial in new[] {false, true})
                {
                    string stage = Path.Combine(parent, "fault-" + count++); Directory.CreateDirectory(stage);
                    StageFailure(stage, second, partial, false, false);
                }
            foreach (bool unknownSource in new[] {false, true})
            {
                string stage = Path.Combine(parent, "fault-" + count++); Directory.CreateDirectory(stage);
                StageFailure(stage, true, false, unknownSource, !unknownSource);
            }
            Console.WriteLine("PASS transaction fault cases: " + (count + 1));
            return 0;
        }
        catch (Exception e) { Console.WriteLine("FAIL " + e); return 1; }
        finally { Bootstrap.AfterWrite = null; Bootstrap.DuringWrite = null; Directory.Delete(parent, true); } // Only disposable test root.
    }
}
