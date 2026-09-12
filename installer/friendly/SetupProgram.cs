using System;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Threading;
using System.Windows.Forms;

namespace Trojaino.Setup
{
    // Coordination only: ownership receipts still authenticate every existing tree.
    internal static class SetupProgram
    {
        [STAThread]
        static int Main()
        {
            try
            {
                bool ran = RunGuarded(delegate {
                    Application.EnableVisualStyles();
                    Application.SetCompatibleTextRenderingDefault(false);
                    using (var window = new SetupWindow()) Application.Run(window);
                });
                if (!ran)
                    MessageBox.Show("Trojaino setup is already open for this Windows account. Return to that window and let it finish before opening another copy.", "Trojaino setup", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return ran ? 0 : 2;
            }
            catch (Exception)
            {
                MessageBox.Show("Trojaino setup could not open or finish safely. Close other setup windows and try again. If this continues, keep the existing setup folders unchanged and contact support. No protection has been confirmed.", "Trojaino setup", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }
        }

        static bool RunGuarded(Action body)
        {
            using (var identity = WindowsIdentity.GetCurrent())
            {
                var sid = identity.User;
                if (sid == null) throw new InvalidOperationException("Windows account identity unavailable.");
                var security = new MutexSecurity();
                security.SetAccessRuleProtection(true, false);
                security.SetOwner(sid);
                security.AddAccessRule(new MutexAccessRule(sid, MutexRights.FullControl, AccessControlType.Allow));
                bool created;
                using (var mutex = new Mutex(false, "Global\\Blockhouse.Trojaino.Setup." + sid.Value, out created, security))
                {
                    bool acquired = false;
                    try
                    {
                        try { acquired = mutex.WaitOne(0); }
                        catch (AbandonedMutexException) { acquired = true; }
                        if (!acquired) return false;
                        // Abandonment grants lock ownership, never ownership of leftover files.
                        // The normal window always begins with authenticated rediscovery.
                        body();
                        return true;
                    }
                    finally { if (acquired) mutex.ReleaseMutex(); }
                }
            }
        }
#if SETUP_LAUNCHER_TESTS
        internal static bool TestRun(Action body) { return RunGuarded(body); }
#endif
    }
}
