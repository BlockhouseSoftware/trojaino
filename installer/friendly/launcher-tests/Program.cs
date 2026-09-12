using System;
using System.IO;
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
    [STAThread]
    static int Main()
    {
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
        Console.WriteLine("PASS native executable entry is zero-argument STA; actual same-user mutex excludes concurrent thread before body, releases on normal/error paths; launcher body fixture only, no normal profile or UI started");
        return 0;
    }
}
