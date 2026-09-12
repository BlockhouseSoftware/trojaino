// Reviewed self-child fixture; never execute source/candidates or use PATH.
using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Threading;

internal static class ProcessTests
{
    static void Assert(bool ok, string why) { if (!ok) throw new Exception(why); }
    static byte[] Run(string mode, int timeout, int outputLimit, int errorLimit, CancellationToken token, Action<int> started)
    {
        var type = Assembly.GetExecutingAssembly().GetType("Trojaino.Setup.TrustedPreparation");
        Assert(type != null, "Missing authenticated preparation process boundary");
        var method = type.GetMethod("TestRun", BindingFlags.Static | BindingFlags.NonPublic);
        Assert(method != null, "Missing test-only process boundary adapter");
        var start = new ProcessStartInfo {
            FileName = Process.GetCurrentProcess().MainModule.FileName,
            Arguments = "--child " + mode,
            UseShellExecute = false, CreateNoWindow = true,
            RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true
        };
        try { return (byte[])method.Invoke(null, new object[] { start, timeout, outputLimit, errorLimit, token, started }); }
        catch (TargetInvocationException e) { throw e.InnerException; }
    }
    static int Child(string mode)
    {
        if (mode == "ok") { Console.OpenStandardOutput().Write(new byte[] {0, 10, 13, 128, 255}, 0, 5); return 0; }
        if (mode == "nonzero") return 23;
        if (mode == "stderr") { Console.Error.Write("not clean"); return 0; }
        if (mode == "pipes")
        {
            for (int i = 0; i < 128; i++) { Console.Out.Write(new string('o', 4096)); Console.Error.Write(new string('e', 4096)); }
            return 0;
        }
        if (mode == "stdout-over") { Console.Out.Write(new string('o', 8192)); Console.Out.Flush(); }
        else if (mode == "stderr-over") { Console.Error.Write(new string('e', 8192)); Console.Error.Flush(); }
        Thread.Sleep(1500); return 0;
    }
    static void Stopped(int pid)
    {
        Assert(pid > 0, "fixture actually started");
        try { using (var child = Process.GetProcessById(pid)) Assert(child.HasExited, "failed helper remains alive"); }
        catch (ArgumentException) { }
    }
    static void Fails(string mode, string expected, int timeout = 3000, bool cancel = false)
    {
        int pid = 0;
        using (var cancellation = new CancellationTokenSource())
        {
            var clock = Stopwatch.StartNew();
            try
            {
                Run(mode, timeout, 4096, 4096, cancellation.Token,
                    id => { pid = id; if (cancel) cancellation.Cancel(); });
                throw new Exception("Expected refusal: " + mode);
            }
            catch (Exception e) { Assert(e.ToString().IndexOf(expected, StringComparison.OrdinalIgnoreCase) >= 0, "wrong failure: " + e); }
            Stopped(pid); Assert(clock.ElapsedMilliseconds < 12000, "unbounded failure exit");
        }
        Console.WriteLine("PASS " + mode + ": " + expected + ", child confirmed stopped");
    }
    static int Main(string[] args)
    {
        if (args.Length == 2 && args[0] == "--child") return Child(args[1]);
        try
        {
            int pid = 0;
            byte[] output = Run("ok", 3000, 1024, 1024, CancellationToken.None, id => pid = id);
            Assert(output.SequenceEqual(new byte[] {0, 10, 13, 128, 255}), "binary stdout changed"); Stopped(pid);
            Console.WriteLine("PASS exact binary stdout and stopped successful child");
            var boundary = Assembly.GetExecutingAssembly().GetType("Trojaino.Setup.TrustedPreparation")
                .GetMethod("Render", BindingFlags.Static | BindingFlags.NonPublic);
            Assert(boundary != null, "Missing authenticated Render entry point");
            Assert(boundary.GetParameters()[3].ParameterType == typeof(Trojaino.Setup.Bootstrap.Receipt), "Scratch must require private empty ownership receipt, not a caller path");
            if (Environment.OSVersion.Platform != PlatformID.Win32NT)
            {
                try { boundary.Invoke(null, new object[] { null, null, null, null, CancellationToken.None }); throw new Exception("Windows-only entry accepted on Mac"); }
                catch (TargetInvocationException e) { Assert(e.InnerException is PlatformNotSupportedException, "wrong non-Windows refusal"); }
                Console.WriteLine("PASS Render refuses non-Windows; native execution explicitly skipped");
            }
            Fails("nonzero", "exit code 23");
            Fails("stderr", "unexpected helper stderr");
            Fails("stdout-over", "output budget exceeded");
            Fails("stderr-over", "output budget exceeded");
            Fails("sleep", "timed out", 100);
            Fails("sleep", "canceled", 3000, true);
            Fails("pipes", "output budget exceeded");
            return 0;
        }
        catch (Exception e) { Console.WriteLine("FAIL " + e); return 1; }
    }
}
