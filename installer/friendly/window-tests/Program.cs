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
    static int uiThread;
    static void ObserveThread(Control control)
    {
        control.EnabledChanged += delegate { Assert(Thread.CurrentThread.ManagedThreadId == uiThread, "control update left owning UI thread: " + control.Name); };
        foreach (Control child in control.Controls) ObserveThread(child);
    }
    static Form Open(DefaultSetupPlan plan)
    {
        var type = Assembly.GetExecutingAssembly().GetType("Trojaino.Setup.SetupWindow");
        Assert(type != null, "friendly consent/setup window is missing");
        var factory = type.GetMethod("TestCreate", BindingFlags.Static | BindingFlags.NonPublic);
        Assert(factory != null, "fixture-only window entry missing");
        var form = (Form)factory.Invoke(null, new object[] {plan});
        ObserveThread(form); form.Show(); return form;
    }
    static void Idle(Form form)
    {
        Assert(Thread.CurrentThread.ManagedThreadId == uiThread && SynchronizationContext.Current is WindowsFormsSynchronizationContext && Application.MessageLoop, "operation lost persistent UI context");
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
        Application.SetUnhandledExceptionMode(UnhandledExceptionMode.ThrowException);
        System.Windows.Forms.Control.CheckForIllegalCrossThreadCalls = true;
        uiThread = Thread.CurrentThread.ManagedThreadId;
        Exception failure = null;
        using (var context = new ApplicationContext())
        using (var dispatch = new System.Windows.Forms.Control())
        {
            var handle = dispatch.Handle;
            dispatch.BeginInvoke((Action)delegate {
                try { Journey(); Journey(); }
                catch (Exception error) { failure = error; }
                finally { context.ExitThread(); }
            });
            // Unlike standalone DoEvents, this outer loop keeps the same WinForms
            // synchronization context alive across every operation and reopened form.
            Application.Run(context);
        }
        if (failure != null) System.Runtime.ExceptionServices.ExceptionDispatchInfo.Capture(failure).Throw();
        return 0;
    }
    static string[] Snapshot(string root)
    {
        return Directory.GetFileSystemEntries(root, "*", SearchOption.AllDirectories).OrderBy(p => p, StringComparer.Ordinal).Select(p => {
            string identity = Bootstrap.Identity(p);
            if (Directory.Exists(p)) return p + "|directory|" + identity;
            using (var input = File.OpenRead(p))
            using (var hash = System.Security.Cryptography.SHA256.Create())
                return p + "|file|" + identity + "|" + BitConverter.ToString(hash.ComputeHash(input));
        }).ToArray();
    }
    static void Journey()
    {
        Assert(SynchronizationContext.Current is WindowsFormsSynchronizationContext && Application.MessageLoop, "journey requires persistent native UI loop");
        string root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "ui-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root); string local = Path.Combine(root, "local"); Directory.CreateDirectory(local);
        bool journeyFinished = false;
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
                Assert(Control<TextBox>(form, "details").Text.Contains("Account settings recovery: none"), "installed status omitted absent account recovery classification");
                var pair = DefaultSetupDiscovery.TestFind(plan); Assert(pair != null, "UI did not call actual default setup"); PairState.Verify(pair);
                Assert(System.Text.RegularExpressions.Regex.IsMatch(File.ReadAllText(Path.Combine(pair.Plugin.Component.Root, ".claude-plugin", "plugin.json")), "\\\"defaultEnabled\\\"\\s*:\\s*false"), "prepared plugin not disabled");
                Assert(form.Controls.Find("enableConsent", true).Length == 1 && form.Controls.Find("enable", true).Length == 1, "separate account-enable consent controls are missing");
                var enableConsent = Control<CheckBox>(form, "enableConsent");
                var enable = Control<Button>(form, "enable");
                Assert(!enableConsent.Checked && !enable.Enabled, "account enable consent defaults unsafe");
                string[] beforeEnable = Snapshot(root);
                enable.PerformClick();
                Assert(Snapshot(root).SequenceEqual(beforeEnable), "unconsented account-enable wrote files");
                Assert(enableConsent.Text.Contains("account") && enableConsent.Text.Contains("settings"), "account-enable consent lacks explicit account-settings scope");
                enableConsent.Checked = true;
                Assert(enable.Enabled && Snapshot(root).SequenceEqual(beforeEnable), "checking enable consent wrote files or did not enable deliberate action");
                enableConsent.Checked = false; enable.PerformClick();
                Assert(!enable.Enabled && Snapshot(root).SequenceEqual(beforeEnable), "revoked account-enable consent wrote files");
                enableConsent.Checked = true; enable.PerformClick();
                Assert(!enableConsent.Checked && !enable.Enabled && Snapshot(root).SequenceEqual(beforeEnable), "account-enable preview retained consent or wrote files");
                string extra = Path.Combine(pair.Plugin.State.Root, "unknown"); File.WriteAllBytes(extra, new byte[] {0, 255});
                Control<Button>(form, "refresh").PerformClick(); Idle(form);
                Assert(Control<Label>(form, "status").Text.Contains("could not") && !Control<Button>(form, "install").Enabled && File.ReadAllBytes(extra).SequenceEqual(new byte[] {0, 255}), "refresh trusted changed state or changed bytes");
                File.Delete(extra); Control<Button>(form, "refresh").PerformClick(); Idle(form);
                Assert(Control<Label>(form, "status").Text.Contains("activation has not been checked"), "refresh did not recover after fixture restored");
                form.Close();
            }
            using (var reopened = Open(DefaultSetupPlan.TestCreate(root, local, null, Guid.NewGuid().ToString("N"))))
            {
                Idle(reopened);
                Assert(Control<Label>(reopened, "status").Text.Contains("activation has not been checked") && !Control<Button>(reopened, "install").Enabled, "reopened UI failed authenticated rediscovery");
                Assert(reopened.Controls.Find("remove", true).Length == 1 && reopened.Controls.Find("removalConsent", true).Length == 1, "consented removal controls are missing");
                var remove = Control<Button>(reopened, "remove");
                var removalConsent = Control<CheckBox>(reopened, "removalConsent");
                Assert(!removalConsent.Checked && !remove.Enabled, "removal consent defaults unsafe");
                Assert(removalConsent.Text.Contains("all Claude Code sessions") && removalConsent.Text.Contains("remove") && removalConsent.Text.Contains("runtime"), "removal consent lacks closed-session/destructive scope explanation");
                string setting = Path.Combine(root, ".claude", "settings.json");
                byte[] settingBytes = System.Text.Encoding.UTF8.GetBytes("{\"testOnly\":true}"); File.WriteAllBytes(setting, settingBytes);
                string sibling = Path.Combine(root, ".claude", "skills", "unrelated.txt"); File.WriteAllBytes(sibling, new byte[] {1, 2, 3});
                remove.PerformClick(); PairState.Verify(DefaultSetupDiscovery.TestFind(plan));
                removalConsent.Checked = true; Assert(remove.Enabled, "explicit removal consent ignored");
                removalConsent.Checked = false; Assert(!remove.Enabled, "revoked removal consent ignored");
                remove.PerformClick(); PairState.Verify(DefaultSetupDiscovery.TestFind(plan));
                removalConsent.Checked = true; Control<Button>(reopened, "refresh").PerformClick(); Idle(reopened);
                Assert(!removalConsent.Checked && !remove.Enabled, "recheck retained prior removal consent");
                var pair = DefaultSetupDiscovery.TestFind(plan);
                removalConsent.Checked = true;
                string extra = Path.Combine(pair.Plugin.State.Root, "unknown-after-consent");
                File.WriteAllBytes(extra, new byte[] {0, 255, 17});
                remove.PerformClick();
                Assert(!remove.Enabled && !removalConsent.Enabled, "removal busy controls unsafe");
                reopened.Close(); Assert(!reopened.IsDisposed, "busy removal close abandoned operation");
                Idle(reopened);
                Assert(Control<Label>(reopened, "status").Text.Contains("could not") && !remove.Enabled && !removalConsent.Checked, "stale removal was trusted or consent retained after failure");
                Assert(File.ReadAllBytes(extra).SequenceEqual(new byte[] {0, 255, 17}), "unknown removal-state bytes altered");
                Bootstrap.Verify(pair.Runtime.Component); Bootstrap.Verify(pair.Runtime.State); Bootstrap.Verify(pair.Plugin.Component);
                File.Delete(extra); PairState.Verify(pair);
                Control<Button>(reopened, "refresh").PerformClick(); Idle(reopened);
                Assert(!removalConsent.Checked && !remove.Enabled && removalConsent.Enabled, "verified recheck did not restore unchecked removal choice: checked=" + removalConsent.Checked + "; remove=" + remove.Enabled + "; consent=" + removalConsent.Enabled + "; status=" + Control<Label>(reopened, "status").Text + "; details=" + Control<TextBox>(reopened, "details").Text);
                removalConsent.Checked = true; remove.PerformClick(); Idle(reopened);
                Assert(Control<Label>(reopened, "status").Text.Contains("Removed") && !remove.Enabled && !removalConsent.Checked, "actual UI removal did not complete honestly");
                Assert(new[] {pair.Runtime.Component.Root, pair.Runtime.State.Root, pair.Plugin.Component.Root, pair.Plugin.State.Root}.All(p => !Directory.Exists(p)), "UI removal left owned pair trees");
                Assert(DefaultSetupDiscovery.TestFind(plan) == null, "removed pair still discovered");
                Assert(Directory.Exists(Path.Combine(root, ".claude", "skills")), "removal deleted shared parents");
                Assert(File.ReadAllBytes(setting).SequenceEqual(settingBytes) && File.ReadAllBytes(sibling).SequenceEqual(new byte[] {1, 2, 3}), "removal changed unrelated Claude settings/skill bytes");
                reopened.Close();
            }
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
            string recoveryDetails;
            string[] survivors;
            using (var partial = Open(plan))
            {
                Idle(partial);
                Control<CheckBox>(partial, "consent").Checked = true;
                Control<Button>(partial, "install").PerformClick(); Idle(partial);
                var pair = DefaultSetupDiscovery.TestFind(plan); Assert(pair != null, "partial-removal fixture install failed");
                string runtimeFile = Path.Combine(pair.Runtime.Component.Root, "python.exe");
                byte[] runtimeBytes = File.ReadAllBytes(runtimeFile);
                using (var held = new FileStream(runtimeFile, FileMode.Open, FileAccess.Read, FileShare.Read))
                {
                    PairState.Verify(pair); // The lock permits verification, not deletion.
                    Control<CheckBox>(partial, "removalConsent").Checked = true;
                    Control<Button>(partial, "remove").PerformClick(); Idle(partial);
                    Assert(!Directory.Exists(pair.Plugin.Component.Root) && !Directory.Exists(pair.Plugin.State.Root), "lock did not reproduce failure AFTER plugin retirement");
                    Assert(File.ReadAllBytes(runtimeFile).SequenceEqual(runtimeBytes), "locked approved runtime bytes changed");
                    Bootstrap.Verify(pair.Runtime.State);
                    recoveryDetails = Control<TextBox>(partial, "details").Text;
                    Assert(Control<Label>(partial, "status").Text.Contains("could not") && recoveryDetails.Contains("System.IO.IOException"), "actual partial removal error missing");
                    Assert(!Control<Button>(partial, "install").Enabled && !Control<Button>(partial, "remove").Enabled, "partial removal authorized a new operation");
                }
                // Deterministic companion to the real lock failure: retire one known
                // fixture file so the missing-original-file recovery branch is exercised.
                string retired = pair.Runtime.Component.Hashes.Keys.First(p => p != runtimeFile && File.Exists(p));
                File.Delete(retired);
                try { Bootstrap.Verify(pair.Runtime.Component); throw new Exception("ASSERT: ordinary runtime verification accepted missing file"); }
                catch (InvalidDataException) { }
                survivors = Snapshot(root);
                partial.Close();
            }
            using (var recovery = Open(DefaultSetupPlan.TestCreate(root, local, null, Guid.NewGuid().ToString("N"))))
            {
                Idle(recovery);
                Assert(Control<Label>(recovery, "status").Text.Contains("could not") && !Control<Button>(recovery, "install").Enabled && !Control<Button>(recovery, "remove").Enabled, "reopen adopted partial removal");
                Assert(Snapshot(root).SequenceEqual(survivors), "reopen changed partial-removal survivor inventory, identity or bytes");
                recovery.Close();
            }
            Assert(recoveryDetails.Contains("Keep all Claude Code sessions closed") && recoveryDetails.Contains("partway") && recoveryDetails.Contains("Do not delete or move"), "partial removal lacks specific closed-session and retained-output recovery guidance");
            using (var finish = Open(DefaultSetupPlan.TestCreate(root, local, null, Guid.NewGuid().ToString("N"))))
            {
                Idle(finish);
                Assert(finish.Controls.Find("finishRemoval", true).Length == 1 && finish.Controls.Find("finishRemovalConsent", true).Length == 1, "authenticated interrupted-removal recovery controls are missing");
                var action = Control<Button>(finish, "finishRemoval");
                var agreement = Control<CheckBox>(finish, "finishRemovalConsent");
                Assert(!agreement.Checked && !action.Enabled && agreement.Enabled, "finish-removal choice did not require fresh consent");
                Assert(Control<TextBox>(finish, "details").Text.Contains(plan.Roots[0]) && Control<TextBox>(finish, "details").Text.Contains(plan.Roots[4]), "recovery consent does not display the authenticated runtime and ownership-state locations");
                Assert(!Control<Button>(finish, "install").Enabled && !Control<Button>(finish, "remove").Enabled, "fresh recovery display enabled ordinary actions");
                Assert(agreement.Text.Contains("all Claude Code sessions") && agreement.Text.Contains("remaining"), "finish-removal consent lacks closed-session and remaining-file scope");
                action.PerformClick(); Assert(Snapshot(root).SequenceEqual(survivors), "unconsented finish removal changed survivors");
                agreement.Checked = true; Assert(action.Enabled, "finish-removal consent ignored");
                agreement.Checked = false; action.PerformClick();
                Assert(!action.Enabled && Snapshot(root).SequenceEqual(survivors), "revoked finish-removal consent ignored");
                foreach (string role in new[] {plan.Roots[0], plan.Roots[4]})
                {
                    agreement.Checked = true;
                    string extra = Path.Combine(role, "unknown-before-finish"); File.WriteAllBytes(extra, new byte[] {7, 0, 255});
                    string[] unknownSnapshot = Snapshot(root);
                    action.PerformClick(); Idle(finish);
                    Assert(Control<Label>(finish, "status").Text.Contains("could not") && !action.Enabled && !agreement.Checked, "stale interrupted-removal recovery trusted unknown content");
                    Assert(!Control<Button>(finish, "install").Enabled && !Control<Button>(finish, "remove").Enabled, "recovery failure enabled ordinary actions");
                    Assert(Snapshot(root).SequenceEqual(unknownSnapshot), "failed finish removal changed unknown or owned survivor bytes/identities");
                    File.Delete(extra); // Only the test-created unknown file, never production recovery.
                    Control<Button>(finish, "refresh").PerformClick(); Idle(finish);
                    Assert(agreement.Enabled && !agreement.Checked && !action.Enabled, "recheck failed to restore fresh recovery choice");
                    Assert(!Control<Button>(finish, "install").Enabled && !Control<Button>(finish, "remove").Enabled, "recovery recheck enabled ordinary actions");
                }
                var secondPlan = DefaultSetupPlan.TestCreate(root, local, null, Guid.NewGuid().ToString("N"));
                var second = DefaultSetup.Install(secondPlan, CancellationToken.None);
                agreement.Checked = true;
                string[] ambiguousSnapshot = Snapshot(root);
                action.PerformClick(); Idle(finish);
                Assert(!agreement.Checked && !action.Enabled && Snapshot(root).SequenceEqual(ambiguousSnapshot), "second identity did not revoke stale recovery consent without writes");
                PairState.Remove(second); // Only the test's returned original pair authority.
                Control<Button>(finish, "refresh").PerformClick(); Idle(finish);
                Assert(agreement.Enabled && !agreement.Checked && !action.Enabled, "second-identity recovery failed to require renewed consent");
                agreement.Checked = true;
                second = DefaultSetup.Install(secondPlan, CancellationToken.None);
                StateStore.Remove(second.Plugin); // Make a different authentic remainder using original authority.
                string heldRuntime = Path.Combine(root, "held-runtime"), heldState = Path.Combine(root, "held-state");
                Directory.Move(plan.Roots[0], heldRuntime); Directory.Move(plan.Roots[4], heldState);
                string[] switchedSnapshot = Snapshot(root);
                action.PerformClick(); Idle(finish);
                Assert(Control<TextBox>(finish, "details").Text.Contains("displayed remaining installation changed") && Control<Label>(finish, "status").Text.Contains("could not") && !agreement.Checked && !action.Enabled && Snapshot(root).SequenceEqual(switchedSnapshot), "consent silently rebound to a different authentic remaining identity");
                Directory.Move(heldRuntime, plan.Roots[0]); Directory.Move(heldState, plan.Roots[4]);
                StateStore.LoadRemaining(secondPlan.Roots[0], secondPlan.Roots[4]).Remove();
                Control<Button>(finish, "refresh").PerformClick(); Idle(finish);
                Assert(agreement.Enabled && !agreement.Checked && !action.Enabled, "identity-switch refusal failed to reset consent");
                foreach (bool fullPair in new[] {false, true})
                {
                    agreement.Checked = true;
                    Assert(!Control<Button>(finish, "install").Enabled && !Control<Button>(finish, "remove").Enabled, "recovery consent enabled ordinary actions");
                    if (fullPair) second = DefaultSetup.Install(secondPlan, CancellationToken.None);
                    Directory.Move(plan.Roots[0], heldRuntime); Directory.Move(plan.Roots[4], heldState);
                    string[] staleSnapshot = Snapshot(root);
                    action.PerformClick(); Idle(finish);
                    Assert(Control<TextBox>(finish, "details").Text.Contains("no longer eligible") && !agreement.Checked && !action.Enabled && Snapshot(root).SequenceEqual(staleSnapshot), "stale full/absent recovery changed files or dispatched another operation");
                    Directory.Move(heldRuntime, plan.Roots[0]); Directory.Move(heldState, plan.Roots[4]);
                    if (fullPair) PairState.Remove(second);
                    Control<Button>(finish, "refresh").PerformClick(); Idle(finish);
                    Assert(agreement.Enabled && !agreement.Checked && !action.Enabled, "stale full/absent recovery did not require fresh consent");
                }
                string[] unrelated = new[] {Path.Combine(root, ".claude"), Path.Combine(root, ".claude", "skills"), Path.Combine(root, ".claude", "settings.json"), Path.Combine(root, ".claude", "skills", "unrelated.txt")};
                string[] unrelatedBefore = Snapshot(root).Where(line => unrelated.Any(path => line.StartsWith(path + "|", StringComparison.Ordinal))).ToArray();
                agreement.Checked = true; action.PerformClick();
                Assert(!action.Enabled && !agreement.Enabled, "busy finish removal permits duplicate action");
                finish.Close(); Assert(!finish.IsDisposed, "busy finish removal abandoned worker");
                Idle(finish);
                Assert(Control<Label>(finish, "status").Text.Contains("Removed") && !action.Enabled && !agreement.Checked, "finish removal did not report verified absence");
                Assert(new[] {plan.Roots[0], plan.Roots[3], plan.Roots[4], plan.Roots[5]}.All(p => !Directory.Exists(p)), "finish removal left owned trees");
                Assert(DefaultSetupDiscovery.TestFind(plan) == null, "finished removal remains discoverable");
                Assert(Snapshot(root).Where(line => unrelated.Any(path => line.StartsWith(path + "|", StringComparison.Ordinal))).SequenceEqual(unrelatedBefore), "finish removal changed unrelated parent/settings/skill identities or bytes");
                finish.Close();
            }
            Console.WriteLine("PASS native consented finish-removal UI: original partial runtime survivors authenticated; unchecked/revoked consent and stale unknown content preserve all bytes/identities; fresh recheck, busy-close guard, removal and unrelated-file preservation; NOT arbitrary leftover adoption/crash recovery");
            Console.WriteLine("PASS native initial locked-runtime failure/reopen phase: plugin retired before IOException, runtime bytes/state retained, ordinary actions refused, reopened survivor inventory/identity/hashes unchanged, explicit closed-session/partway guidance; recovery tested separately");
            journeyFinished = true;
            Console.WriteLine("PASS native actual WinForms controls: unchecked/revoked consent zero writes, real approved default setup, busy close retained, authenticated reopen; explicit consented UI removal, stale unknown-state refusal, all four owned trees removed, shared parents/settings/unrelated skills retained; protection never claimed; NOT Windows11/visual/keyboard/Claude qualification");
        }
        finally
        {
            // A timed-out/failed UI may still have an active worker/helper. Do not
            // race it with recursive test cleanup or mask the original failure.
            if (journeyFinished) Directory.Delete(root, true);
            else Console.WriteLine("RETAINED failed window-test fixture; helper exit is unconfirmed: " + root);
        }
    }
}
