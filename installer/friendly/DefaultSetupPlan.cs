// Read-only default-profile path plan, not an ownership receipt or activation proof.
using System;

namespace Trojaino.Setup
{
    internal sealed class DefaultSetupPlan
    {
        readonly string[] roots;
        readonly string name;
        DefaultSetupPlan(string[] roots, string name) { this.roots = (string[])roots.Clone(); this.name = name; }
        internal string[] Roots { get { return (string[])roots.Clone(); } }
        internal string Name { get { return name; } }
        internal static DefaultSetupPlan Resolve()
        {
#if NETFRAMEWORK
            if (Environment.OSVersion.Platform != PlatformID.Win32NT)
                throw new PlatformNotSupportedException("Setup requires native Windows Framework");
            string config = Environment.GetEnvironmentVariable("CLAUDE_CONFIG_DIR");
            if (!string.IsNullOrEmpty(config)) throw new System.IO.InvalidDataException("Custom Claude configuration is not supported by default-profile setup");
            return Create(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), config, Guid.NewGuid().ToString("N"));
#else
            throw new PlatformNotSupportedException("Setup requires native Windows Framework");
#endif
        }
        static DefaultSetupPlan Create(string profile, string local, string config, string id)
        {
            if (!string.IsNullOrEmpty(config)) throw new System.IO.InvalidDataException("Custom Claude configuration is not supported by default-profile setup");
            WindowsPreflight.ValidateSpelling(profile, new string[0]);
            WindowsPreflight.ValidateSpelling(local, new string[0]);
            if (id == null || !System.Text.RegularExpressions.Regex.IsMatch(id, @"\A[a-f0-9]{32}\z"))
                throw new System.IO.InvalidDataException("Fresh exact setup identifier required");
            string name = "trojaino-local-" + id;
            string prefix = local + "\\trj-" + id;
            var roots = new[] {
                prefix + "-runtime", prefix + "-source", prefix + "-scratch",
                profile + "\\.claude\\skills\\" + name, prefix + "-runtime-state", prefix + "-plugin-state"
            };
            SetupLocations.ValidateLayout(roots, name);
            return new DefaultSetupPlan(roots, name);
        }
#if SETUP_PLAN_TESTS
        internal static DefaultSetupPlan TestCreate(string profile, string local, string config, string id)
        { return Create(profile, local, config, id); }
#endif
    }
}
