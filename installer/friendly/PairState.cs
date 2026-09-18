// Two-component persistent lifecycle only; not activation or crash recovery.
using System;
using System.IO;

namespace Trojaino.Setup
{
    internal static class PairState
    {
        internal sealed class Record
        {
            internal readonly StateStore.Record Runtime, Plugin;
            internal Record(StateStore.Record runtime, StateStore.Record plugin)
            { Runtime = runtime; Plugin = plugin; }
        }
        static void Locations(params string[] roots)
        {
            var comparison = Environment.OSVersion.Platform == PlatformID.Win32NT ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
            for (int i = 0; i < roots.Length; i++)
            {
                string root = roots[i];
                if (string.IsNullOrEmpty(root) || !Path.IsPathRooted(root) || Path.GetFullPath(root) != root
                    || root.EndsWith(Path.DirectorySeparatorChar.ToString(), StringComparison.Ordinal))
                    throw new InvalidDataException("Distinct literal nonoverlapping pair roots required");
                for (int j = 0; j < i; j++)
                    if (string.Equals(root, roots[j], comparison)
                        || root.StartsWith(roots[j] + Path.DirectorySeparatorChar, comparison)
                        || roots[j].StartsWith(root + Path.DirectorySeparatorChar, comparison))
                        throw new InvalidDataException("Distinct literal nonoverlapping pair roots required");
            }
        }
        internal static void Verify(Record record)
        {
            if (record == null) throw new ArgumentNullException("record");
            Locations(record.Runtime.Component.Root, record.Plugin.Component.Root, record.Runtime.State.Root, record.Plugin.State.Root);
            Bootstrap.Verify(record.Runtime.Component); Bootstrap.Verify(record.Runtime.State);
            Bootstrap.Verify(record.Plugin.Component); Bootstrap.Verify(record.Plugin.State);
        }
        internal static Record Save(Bootstrap.Receipt runtime, Bootstrap.Receipt plugin, string runtimeState, string pluginState)
        {
            if (runtime == null || plugin == null) throw new ArgumentNullException("component");
            Locations(runtime.Root, plugin.Root, runtimeState, pluginState);
            Bootstrap.Verify(runtime); Bootstrap.Verify(plugin);
            StateStore.Record r = null, p = null;
            try
            {
                r = StateStore.Store(runtime, runtimeState);
                p = StateStore.Store(plugin, pluginState);
                var record = new Record(r, p);
                Verify(record);
                return record;
            }
            catch (Exception failure)
            {
                var errors = new System.Collections.Generic.List<Exception> { failure };
                if (p != null) try { Bootstrap.Remove(p.State); } catch (Exception cleanup) { errors.Add(cleanup); }
                if (r != null) try { Bootstrap.Remove(r.State); } catch (Exception cleanup) { errors.Add(cleanup); }
                if (errors.Count > 1) throw new AggregateException("Pair state save failed; unverified state retained; components untouched", errors);
                throw;
            }
        }
        internal static Record Load(string runtime, string plugin, string runtimeState, string pluginState)
        {
            Locations(runtime, plugin, runtimeState, pluginState);
            var record = new Record(StateStore.Load(runtime, runtimeState), StateStore.Load(plugin, pluginState));
            Verify(record);
            return record;
        }
        internal static void Remove(Record record)
        {
            Verify(record);
            StateStore.Remove(record.Plugin);
            StateStore.Remove(record.Runtime);
        }
    }
}
