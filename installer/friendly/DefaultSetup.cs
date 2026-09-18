// Default-plan composition only; GUI consent and effective activation remain separate.
using System;
using System.Threading;

namespace Trojaino.Setup
{
    internal static class DefaultSetup
    {
        internal static PairState.Record Install(DefaultSetupPlan plan, CancellationToken cancellation)
        {
#if NETFRAMEWORK
            if (Environment.OSVersion.Platform != PlatformID.Win32NT)
                throw new PlatformNotSupportedException("Setup requires native Windows Framework");
            cancellation.ThrowIfCancellationRequested();
            if (plan == null) throw new ArgumentNullException("plan");
            PairState.Record result = null;
            SharedParents.Run(plan, () => { result = SetupController.Install(plan.Roots, plan.Name, cancellation); });
            return result; // No post-publication failure that loses the returned receipt.
#else
            throw new PlatformNotSupportedException("Setup requires native Windows Framework");
#endif
        }
    }
}
