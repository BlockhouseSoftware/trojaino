using System;
using System.Linq;
using System.Reflection;
using System.Windows.Forms;

internal static class WindowProductionTests
{
    static void Assert(bool ok, string why) { if (!ok) throw new Exception("ASSERT: " + why); }
    [STAThread]
    static int Main()
    {
        var assembly = Assembly.GetExecutingAssembly();
        var type = assembly.GetType("Trojaino.Setup.SetupWindow");
        Assert(type != null, "production window missing");
        Assert(type.GetMethod("TestCreate", BindingFlags.Static | BindingFlags.NonPublic) == null, "fixture factory leaked into production");
        Assert(type.GetField("fixture", BindingFlags.Instance | BindingFlags.NonPublic) == null, "fixture roots leaked into production");
        Assert(type.GetConstructors(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic).All(c => c.GetParameters().Length == 0), "production constructor accepts paths");
        foreach (string name in new[] {"DefaultSetupPlan", "DefaultSetupDiscovery", "SharedParents", "SetupController", "TrustedPreparation"})
        {
            var target = assembly.GetType("Trojaino.Setup." + name);
            Assert(target != null && !target.GetMethods(BindingFlags.Static | BindingFlags.NonPublic | BindingFlags.Public).Any(m => m.Name.StartsWith("Test", StringComparison.Ordinal)), "test seam in " + name);
        }
        using (var form = (Form)Activator.CreateInstance(type, true))
        {
            Assert(!((CheckBox)form.Controls.Find("consent", true).Single()).Checked, "production consent prechecked");
            Assert(!form.Controls.Find("install", true).Single().Enabled, "production install enabled before discovery");
            Assert(form.Controls.Find("remove", true).Length == 1 && form.Controls.Find("removalConsent", true).Length == 1, "production removal controls missing");
            Assert(!form.Controls.Find("remove", true).Single().Enabled && !form.Controls.Find("removalConsent", true).Single().Enabled && !((CheckBox)form.Controls.Find("removalConsent", true).Single()).Checked, "production removal enabled before discovery/consent");
            Assert(form.Controls.Find("finishRemoval", true).Length == 1 && form.Controls.Find("finishRemovalConsent", true).Length == 1, "production recovery controls missing");
            Assert(!form.Controls.Find("finishRemoval", true).Single().Enabled && !form.Controls.Find("finishRemovalConsent", true).Single().Enabled && !((CheckBox)form.Controls.Find("finishRemovalConsent", true).Single()).Checked, "production recovery enabled before authentication/consent");
            // Do not Show: this build has real OS-folder authority, not fixture roots.
        }
        Console.WriteLine("PASS native production-symbol window construction: no fixture/raw operation seams, unchecked consent and install disabled before discovery; normal profile NOT queried or changed; not user journey");
        return 0;
    }
}
