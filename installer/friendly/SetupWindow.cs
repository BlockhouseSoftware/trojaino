// Native consent and setup UI. File verification is not Claude activation evidence.
using System;
using System.ComponentModel;
using System.Drawing;
using System.Threading;
using System.Windows.Forms;

namespace Trojaino.Setup
{
    internal sealed class SetupWindow : Form
    {
        readonly CheckBox consent = new CheckBox();
        readonly Button install = new Button();
        readonly Button refresh = new Button();
        readonly Button close = new Button();
        readonly Label status = new Label();
        readonly TextBox details = new TextBox();
        readonly BackgroundWorker worker = new BackgroundWorker();
        bool busy;
        bool absent;
#if SETUP_WINDOW_TESTS
        DefaultSetupPlan fixture;
        internal static SetupWindow TestCreate(DefaultSetupPlan plan)
        {
            if (plan == null) throw new ArgumentNullException("plan");
            var window = new SetupWindow(); window.fixture = plan; return window;
        }
#endif
        internal SetupWindow()
        {
            Text = "Trojaino setup — development preview";
            StartPosition = FormStartPosition.CenterScreen;
            AutoScaleMode = AutoScaleMode.Dpi;
            ClientSize = new Size(720, 650); MinimumSize = new Size(660, 600);
            var layout = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(20), ColumnCount = 1, RowCount = 7 };
            layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            for (int i = 0; i < 5; i++) layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            layout.Controls.Add(new Label { Text = "Set up Trojaino for this Windows account", AutoSize = true, Margin = new Padding(0, 0, 0, 12) }, 0, 0);
            var explanation = new Label {
                Text = "This installs a separate local Claude Code plugin and its bundled, pinned Python runtime for your account. You do not need to install Python or choose any paths. Setup runs only the reviewed preparation helper; it does not run code you want to scan.\r\n\r\nThe local plugin starts disabled by default. The marketplace copy stays inert: removing it does not disable or remove this separate local plugin. Trojaino is not an operating-system sandbox.\r\n\r\nDevelopment preview: Claude activation, disable and removal controls are not available in this window yet. Do not treat file installation as protection.",
                AutoSize = true, MaximumSize = new Size(610, 0), Margin = new Padding(0, 0, 0, 14)
            };
            layout.Controls.Add(explanation, 0, 1);
            consent.Name = "consent"; consent.Text = "I agree to install the bundled runtime and separate local plugin for this account.";
            consent.AutoSize = true; consent.MaximumSize = new Size(610, 0); consent.Checked = false; consent.Enabled = false; consent.TabIndex = 0;
            consent.CheckedChanged += delegate { install.Enabled = !busy && absent && consent.Checked; };
            layout.Controls.Add(consent, 0, 2);
            status.Name = "status"; status.Text = "Checking for an existing installation…";
            status.AutoSize = true; status.MaximumSize = new Size(610, 0); status.Margin = new Padding(0, 14, 0, 14);
            layout.Controls.Add(status, 0, 3);
            layout.Controls.Add(new Label { Text = "Details (read-only; no passwords are requested)", AutoSize = true }, 0, 4);
            details.Name = "details"; details.ReadOnly = true; details.Multiline = true; details.ScrollBars = ScrollBars.Both;
            details.WordWrap = true; details.Dock = DockStyle.Fill; details.TabIndex = 1;
            layout.Controls.Add(details, 0, 5);
            var buttons = new FlowLayoutPanel { AutoSize = true, Dock = DockStyle.Fill, Margin = new Padding(0, 14, 0, 0) };
            install.Name = "install"; install.Text = "&Install disabled"; install.AutoSize = true; install.Enabled = false; install.TabIndex = 0;
            refresh.Name = "refresh"; refresh.Text = "&Recheck files"; refresh.AutoSize = true; refresh.Enabled = false; refresh.TabIndex = 1;
            close.Name = "close"; close.Text = "&Close"; close.AutoSize = true; close.TabIndex = 2;
            buttons.Controls.Add(install); buttons.Controls.Add(refresh); buttons.Controls.Add(close); layout.Controls.Add(buttons, 0, 6);
            Controls.Add(layout);
            install.Click += delegate { if (!busy && absent && consent.Checked) Begin(true); };
            refresh.Click += delegate { if (!busy) Begin(false); };
            close.Click += delegate { Close(); };
            Shown += delegate { Begin(false); };
            FormClosing += delegate(object sender, FormClosingEventArgs e) {
                if (busy) { e.Cancel = true; status.Text = "Please wait for setup to finish before closing. Do not shut down Windows during setup."; }
            };
            worker.DoWork += Work;
            worker.RunWorkerCompleted += Finished;
        }
        PairState.Record Find()
        {
#if SETUP_WINDOW_TESTS
            if (fixture != null) return DefaultSetupDiscovery.TestFind(fixture);
#endif
            return DefaultSetupDiscovery.Find();
        }
        DefaultSetupPlan Plan()
        {
#if SETUP_WINDOW_TESTS
            if (fixture != null) return fixture;
#endif
            return DefaultSetupPlan.Resolve();
        }
        void Begin(bool installing)
        {
            if (busy) return;
            busy = true; absent = false;
            install.Enabled = false; consent.Enabled = false; refresh.Enabled = false; close.Enabled = false;
            status.Text = installing ? "Installing disabled files. Please wait; do not close setup or shut down Windows." : "Checking installation files. This does not check Claude protection.";
            details.Clear();
            try { worker.RunWorkerAsync(installing); }
            catch (Exception error) { ShowFailure(error); EndBusy(); }
        }
        void Work(object sender, DoWorkEventArgs e)
        {
            // Always recheck: an old absent display grants no authority to install.
            PairState.Record found = Find();
            if ((bool)e.Argument && found == null)
                found = DefaultSetup.Install(Plan(), CancellationToken.None);
            e.Result = found;
        }
        void Finished(object sender, RunWorkerCompletedEventArgs e)
        {
            if (e.Error != null) ShowFailure(e.Error);
            else if (e.Cancelled) ShowFailure(new OperationCanceledException("Setup did not return a verified result."));
            else
            {
                absent = e.Result == null;
                status.Text = absent ? "No existing installation was found. Review the consent above to install disabled files." : "Installation files verified. Claude activation has not been checked.";
                details.Text = absent ? "No setup files were written by this check. Close this window to leave setup unchanged." : "The local installation matched its authenticated ownership records. This is a file check only, not proof that Claude is using Trojaino. Enablement and effective protection need separate verification.";
            }
            consent.Checked = false;
            EndBusy();
        }
        void ShowFailure(Exception error)
        {
            absent = false;
            status.Text = "Setup could not finish safely. Existing or incomplete files may remain. No protection has been confirmed.";
            details.Text = "Do not delete or move setup folders to retry. Close and reopen setup, or use Recheck files. If the problem remains, keep these details for support; another copy will not be installed over unknown files.\r\n\r\n" + error.ToString();
        }
        void EndBusy()
        {
            busy = false; refresh.Enabled = true; close.Enabled = true;
            consent.Enabled = absent; install.Enabled = absent && consent.Checked;
        }
        protected override void Dispose(bool disposing)
        {
            if (disposing) worker.Dispose();
            base.Dispose(disposing);
        }
    }
}
