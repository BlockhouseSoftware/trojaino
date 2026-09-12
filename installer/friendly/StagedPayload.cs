// Compiled approved payload staging only. No execution, activation or durable receipt.
using System;
using System.Collections.Generic;
using System.IO;

namespace Trojaino.Setup
{
    internal sealed class StagedPayload
    {
        readonly Bootstrap.Receipt runtime;
        readonly Bootstrap.Receipt source;
        internal string RuntimeRoot { get { return runtime.Root; } }
        internal string SourceRoot { get { return source.Root; } }
        StagedPayload(Bootstrap.Receipt runtime, Bootstrap.Receipt source)
        {
            this.runtime = runtime;
            this.source = source;
        }
        internal static void Verify(StagedPayload receipt)
        {
            if (receipt == null) throw new ArgumentNullException("receipt");
            Bootstrap.Verify(receipt.runtime);
            Bootstrap.Verify(receipt.source);
        }
        // Controller must establish helper input release before any deletion.
        // Capture before retiring source; never reconstruct a receipt from disk.
        internal static Bootstrap.Receipt CaptureRuntime(StagedPayload receipt)
        {
            Verify(receipt);
            return receipt.runtime;
        }
        internal static void RemoveSource(StagedPayload receipt)
        {
            Verify(receipt);
            Bootstrap.Remove(receipt.source);
        }
        internal static void Remove(StagedPayload receipt)
        {
            Verify(receipt); // BOTH trees checked before the first deletion.
            Bootstrap.Remove(receipt.source);
            Bootstrap.Remove(receipt.runtime);
        }
        internal static StagedPayload Install(string runtimeDestination, string sourceDestination)
        {
            if (string.IsNullOrEmpty(runtimeDestination) || string.IsNullOrEmpty(sourceDestination)
                || !Path.IsPathRooted(runtimeDestination) || !Path.IsPathRooted(sourceDestination)
                || Path.GetFullPath(runtimeDestination) != runtimeDestination || Path.GetFullPath(sourceDestination) != sourceDestination
                || string.Equals(runtimeDestination, sourceDestination, StringComparison.OrdinalIgnoreCase)
                || Path.GetDirectoryName(runtimeDestination) != Path.GetDirectoryName(sourceDestination))
                throw new InvalidDataException("Distinct literal sibling staging destinations required");
            var runtime = ApprovedPayload.StageRuntime(runtimeDestination);
            Bootstrap.Receipt source = null;
            try
            {
                source = ApprovedPayload.StageSource(sourceDestination);
                var receipt = new StagedPayload(runtime, source);
                Verify(receipt);
                return receipt;
            }
            catch (Exception failure)
            {
                // Each completed stage owns an independent tree. Try both cleanups;
                // do not lose the original error or delete an unverified stage.
                var errors = new List<Exception> { failure };
                if (source != null)
                    try { Bootstrap.Remove(source); } catch (Exception cleanup) { errors.Add(cleanup); }
                try { Bootstrap.Remove(runtime); } catch (Exception cleanup) { errors.Add(cleanup); }
                if (errors.Count > 1)
                    throw new AggregateException("Payload staging failed; unverified content retained, never activated", errors);
                throw;
            }
        }
    }
}
