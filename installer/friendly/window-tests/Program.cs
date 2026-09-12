using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading;
using System.Windows.Forms;
using Trojaino.Setup;

internal static class WindowTests
{
    static void Assert(bool ok, string why) { if (!ok) throw new Exception("ASSERT: " + why); }
    static T Control<T>(Form form, string name) where T : Control
    { return (T)form.Controls.Find(name, true).Single(); }
    static Form Open(DefaultSetupPlan plan)
    {
        var type = Assembly.GetExecutingAssembly().GetType("Trojaino.Setup.SetupWindow");
        Assert(type != null, "friendly consent/setup window is missing");
        var factory = type.GetMethod("TestCreate", BindingFlags.Static | BindingFlags.NonPublic);
        Assert(factory != null, "fixture-only window entry missing");
        var form = (Form)factory.Invoke(null, new object[] {plan});
        form.Show(); return form;
    }
    static void Idle(Form form)
    {
        var clock = Stopwatch.StartNew();
        while (!Control<Button>(form, "refresh").Enabled)
        {
            Assert(clock.ElapsedMilliseconds < 90000, "window operation did not finish");
            Application.DoEvents(); Thread.Sleep(10);
        }
        Application.DoEvents();
    }
    [STAThread]
    static int Main()
    {
        Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
        string root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "ui-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root); string local = Path.Combine(root, "local"); Directory.CreateDirectory(local);
        try
        {
            var plan = DefaultSetupPlan.TestCreate(root, local, null, Guid.NewGuid().ToString("N"));
            using (var form = Open(plan))
            {
                Assert(!Control<CheckBox>(form, "consent").Checked && !Control<Button>(form, "install").Enabled, "consent/install default unsafe");
                Idle(form);
                Assert(!Directory.Exists(Path.Combine(root, ".claude")) && Directory.GetFileSystemEntries(local).Length == 0, "opening window wrote setup files");
                Control<Button>(form, "install").PerformClick();
                Assert(Directory.GetFileSystemEntries(local).Length == 0, "unconsented click wrote files");
                var consent = Control<CheckBox>(form, "consent"); consent.Checked = true;
                Assert(Control<Button>(form, "install").Enabled, "explicit consent did not enable install");
                consent.Checked = false; Assert(!Control<Button>(form, "install").Enabled, "revoked consent ignored");
                consent.Checked = true; Control<Button>(form, "install").PerformClick();
                Assert(!Control<Button>(form, "install").Enabled && !consent.Enabled, "busy controls allow duplicate operation");
                form.Close(); Assert(!form.IsDisposed, "busy close abandoned setup");
                Idle(form);
                Assert(Control<Label>(form, "status").Text.Contains("activation has not been checked"), "file installation misreported protection or failed");
                Assert(!Control<Button>(form, "install").Enabled, "installed copy permits duplicate install");
                var pair = DefaultSetupDiscovery.TestFind(plan); Assert(pair != null, "UI did not call actual default setup"); PairState.Verify(pair);
                Assert(File.ReadAllText(Path.Combine(pair.Plugin.Component.Root, ".claude-plugin", "plugin.json")).Contains("false"), "prepared plugin not disabled");
                form.Close();
            }
            using (var reopened = Open(DefaultSetupPlan.TestCreate(root, local, null, Guid.NewGuid().ToString("N"))))
            {
                Idle(reopened);
                Assert(Control<Label>(reopened, "status").Text.Contains("activation has not been checked") && !Control<Button>(reopened, "install").Enabled, "reopened UI failed authenticated rediscovery");
                reopened.Close();
            }
            PairState.Remove(DefaultSetupDiscovery.TestFind(plan));
            using (var stale = Open(plan))
            {
                Idle(stale);
                string unknown = Path.Combine(local, "trj-unknown"); byte[] bytes = new byte[] {0, 255, 10}; File.WriteAllBytes(unknown, bytes);
                Control<CheckBox>(stale, "consent").Checked = true; Control<Button>(stale, "install").PerformClick(); Idle(stale);
                Assert(Control<Label>(stale, "status").Text.Contains("could not") && !Control<Button>(stale, "install").Enabled, "stale discovery authorized another installation");
                Assert(Directory.GetFileSystemEntries(local).Length == 1 && File.ReadAllBytes(unknown).SequenceEqual(bytes), "stale refusal wrote/deleted unknown files");
                Assert(Control<TextBox>(stale, "details").ReadOnly && Control<TextBox>(stale, "details").Text.Length > 0, "failure details unavailable");
                stale.Close(); File.Delete(unknown);
            }
            Console.WriteLine("PASS native actual WinForms controls: unchecked/revoked consent zero writes, real approved default setup, busy close retained, existing authenticated rediscovery, stale hint refusal/exact unknown bytes retained; protection never claimed; NOT Windows11/visual/keyboard/Claude qualification");
        }
        finally { Directory.Delete(root, true); }
        return 0;
    }
}
