// Internal transaction only: trusted roots supplied by future consent resolver.
// No activation, settings mutation, crash recovery or arbitrary execution adapter.
using System;
using System.IO;
using System.Threading;

namespace Trojaino.Setup
{
    internal static class SetupController
    {
        internal static PairState.Record Install(string[] roots, string name, CancellationToken cancellation)
        {
            // Platform-first gate also rejects null before any writes on unsupported hosts.
            // Snapshot once: validate and use the same immutable caller-input copy.
            var snapshot = roots == null ? null : (string[])roots.Clone();
            SetupLocations.Check(snapshot, name);
            return Core(snapshot, name, cancellation
#if SETUP_CONTROLLER_TESTS
                , null, null
#endif
            );
        }
        static void RequireAbsent(string path)
        {
            try { File.GetAttributes(path); }
            catch (FileNotFoundException) { return; }
            catch (DirectoryNotFoundException) { return; }
            throw new InvalidDataException("Unreturned plugin remains; bound runtime retained");
        }
        static PairState.Record Core(string[] roots, string name, CancellationToken cancellation
#if SETUP_CONTROLLER_TESTS
            , Func<StagedPayload, string, string, Bootstrap.Receipt, CancellationToken, Bootstrap.Receipt> prepare,
            Action<string> phase
#endif
        )
        {
            cancellation.ThrowIfCancellationRequested();
            StagedPayload staged = null;
            Bootstrap.Receipt runtime = null, scratch = null, plugin = null;
            PairState.Record pair = null;
            bool released = true, sourceRetired = false, scratchRetired = false;
            try
            {
                staged = StagedPayload.Install(roots[0], roots[1]);
                runtime = StagedPayload.CaptureRuntime(staged);
#if SETUP_CONTROLLER_TESTS
                if (phase != null) phase("staged");
#endif
                scratch = Bootstrap.CreateEmpty(roots[2]);
#if SETUP_CONTROLLER_TESTS
                if (phase != null) phase("scratch");
#endif
                cancellation.ThrowIfCancellationRequested();
                released = false;
                try
                {
#if SETUP_CONTROLLER_TESTS
                    plugin = prepare == null ? TrustedPreparation.Install(staged, roots[3], name, scratch, cancellation)
                        : prepare(staged, roots[3], name, scratch, cancellation);
#else
                    plugin = TrustedPreparation.Install(staged, roots[3], name, scratch, cancellation);
#endif
                    released = true;
                }
                catch (TrustedPreparation.ProcessFailureException failure)
                { released = failure.InputsReleased; throw; }
#if SETUP_CONTROLLER_TESTS
                if (phase != null) phase("prepared");
#endif
                pair = PairState.Save(runtime, plugin, roots[4], roots[5]);
#if SETUP_CONTROLLER_TESTS
                if (phase != null) phase("saved");
#endif
                StagedPayload.RemoveSource(staged); sourceRetired = true;
#if SETUP_CONTROLLER_TESTS
                if (phase != null) phase("source-retired");
#endif
                Bootstrap.Remove(scratch); scratchRetired = true;
#if SETUP_CONTROLLER_TESTS
                if (phase != null) phase("scratch-retired");
#endif
                PairState.Verify(pair);
                return pair;
            }
            catch (Exception failure)
            {
                if (!released) throw; // Unknown helper lifetime: never delete execution inputs.
                var errors = new System.Collections.Generic.List<Exception> { failure };
                if (staged != null && !sourceRetired)
                    try { StagedPayload.RemoveSource(staged); } catch (Exception cleanup) { errors.Add(cleanup); }
                if (scratch != null && !scratchRetired)
                    try { Bootstrap.Remove(scratch); } catch (Exception cleanup) { errors.Add(cleanup); }
                if (pair != null)
                {
                    // Pair prevalidates all four trees; failed plugin removal stops runtime removal.
                    try { PairState.Remove(pair); } catch (Exception cleanup) { errors.Add(cleanup); }
                }
                else
                {
                    bool pluginGone = false;
                    if (plugin != null)
                        try { Bootstrap.Remove(plugin); pluginGone = true; } catch (Exception cleanup) { errors.Add(cleanup); }
                    else
                        try { RequireAbsent(roots[3]); pluginGone = true; } catch (Exception cleanup) { errors.Add(cleanup); }
                    if (runtime != null && pluginGone)
                        try { Bootstrap.Remove(runtime); } catch (Exception cleanup) { errors.Add(cleanup); }
                }
                if (errors.Count > 1) throw new AggregateException("Setup failed; unknown or unremovable content retained", errors);
                throw;
            }
        }
#if SETUP_CONTROLLER_TESTS
        // Bypasses native preflight only in the separate inert composition harness.
        internal static PairState.Record TestInstall(string[] roots, string name, CancellationToken cancellation,
            Func<StagedPayload, string, string, Bootstrap.Receipt, CancellationToken, Bootstrap.Receipt> prepare,
            Action<string> phase)
        { return Core((string[])roots.Clone(), name, cancellation, prepare, phase); }
#endif
    }
}
