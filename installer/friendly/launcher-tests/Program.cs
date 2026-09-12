using System;
using System.IO;
using System.Diagnostics;
using System.Security.Principal;
using System.Reflection;
using System.Threading;

internal static class LauncherTests
{
    static void Assert(bool ok, string why) { if (!ok) throw new Exception("ASSERT: " + why); }
    static Type ProgramType()
    {
        var type = Assembly.GetExecutingAssembly().GetType("Trojaino.Setup.SetupProgram");
        Assert(type != null, "production setup executable entry is missing"); return type;
    }
    static bool Run(Action body)
    {
        var method = ProgramType().GetMethod("TestRun", BindingFlags.NonPublic | BindingFlags.Static);
        Assert(method != null, "native launcher guard test entry missing");
        try { return (bool)method.Invoke(null, new object[] {body}); }
        catch (TargetInvocationException error) { throw error.InnerException; }
    }
    static void Probe(int expected)
    {
        using (var child = new Process())
        {
            child.StartInfo = new ProcessStartInfo(Assembly.GetExecutingAssembly().Location, "--probe") { UseShellExecute = false, CreateNoWindow = true };
            Assert(child.Start(), "self-probe did not start");
            if (!child.WaitForExit(10000))
            {
                child.Kill(); Assert(child.WaitForExit(5000), "self-probe stop unconfirmed");
                throw new Exception("ASSERT: self-probe timed out");
            }
            Assert(child.ExitCode == expected, "self-probe guard exit " + child.ExitCode);
        }
    }
    [STAThread]
    static int Main(string[] args)
    {
        if (args.Length == 1 && args[0] == "--probe")
        {
            bool body = false;
            bool acquired = Run(delegate { body = true; });
            Assert(acquired == body, "probe body/result mismatch");
            return acquired ? 0 : 2;
        }
        Assert(args.Length == 0, "unexpected fixture argument");
        var type = ProgramType();
        var main = type.GetMethod("Main", BindingFlags.NonPublic | BindingFlags.Static);
        Assert(main != null && main.GetParameters().Length == 0 && main.GetCustomAttributes(typeof(STAThreadAttribute), false).Length == 1, "launcher must be STA and accept no path/config arguments");
        bool secondBody = false, secondAcquired = true; Exception secondError = null;
        Assert(Run(delegate {
            var thread = new Thread(delegate() { try { secondAcquired = Run(delegate { secondBody = true; }); } catch (Exception e) { secondError = e; } });
            thread.Start(); Assert(thread.Join(5000), "second launcher guard blocked instead of refusing");
            Assert(secondError == null && !secondAcquired && !secondBody, "second instance entered setup body");
        }), "first launcher refused");
        bool after = false; Assert(Run(delegate { after = true; }) && after, "guard not released on normal exit");
        var primary = new IOException("fixture body failure"); bool failed = false;
        try { Run(delegate { throw primary; }); } catch (IOException e) { failed = Object.ReferenceEquals(e, primary); }
        Assert(failed && Run(delegate { }), "body failure lost or mutex retained");
        Assert(Run(delegate { Probe(2); }), "cross-process holder refused");
        Probe(0);
        string name;
        using (var identity = WindowsIdentity.GetCurrent()) name = "Global\\Blockhouse.Trojaino.Setup." + identity.User.Value;
        Mutex retained = null;
        Assert(Run(delegate { retained = Mutex.OpenExisting(name); }), "could not retain guard handle");
        using (retained)
        {
            Exception ownerError = null;
            var owner = new Thread(delegate() { try { Assert(retained.WaitOne(0), "abandonment fixture could not own mutex"); } catch (Exception e) { ownerError = e; } });
            owner.Start(); Assert(owner.Join(5000) && ownerError == null, "abandonment fixture failed");
            bool recovered = false; Assert(Run(delegate { recovered = true; }) && recovered, "abandoned mutex not handled as acquired");
            Probe(0); // A different process detects an unreleased abandoned ownership.
        }
        using (var wrongType = new EventWaitHandle(false, EventResetMode.ManualReset, name))
        {
            bool entered = false, refused = false;
            try { Run(delegate { entered = true; }); }
            catch (WaitHandleCannotBeOpenedException) { refused = true; }
            Assert(refused && !entered, "wrong-object collision bypassed guard");
        }
        Probe(0);
        Console.WriteLine("PASS native zero-argument STA entry; actual same-user Global mutex concurrent-thread and fresh-process exclusion, normal/error release, abandoned-owner recovery/release and wrong-object refusal before body; inert self-probe only, no normal profile/UI or crash-recovery qualification");
        return 0;
    }
}
