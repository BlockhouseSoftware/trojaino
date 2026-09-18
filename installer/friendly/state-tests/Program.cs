using System;
using System.IO;
using System.Linq;
using System.Reflection;
using Trojaino.Setup;
class Program
{
    static void Check(bool value, string why) { if (!value) throw new Exception(why); }
    static void Refuse(Action action, string reason = null)
    {
        try { action(); }
        catch (Exception e)
        {
            if (!(e is IOException || e is InvalidDataException || e is System.ComponentModel.Win32Exception || e is AggregateException)) throw;
            if (reason != null) Check(e.Message.Contains(reason), "Wrong refusal: " + e);
            return;
        }
        throw new Exception("Unsafe state operation accepted");
    }
    static object Call(string method, params object[] args)
    {
        var type = typeof(Bootstrap).Assembly.GetType("Trojaino.Setup.StateStore");
        Check(type != null, "Missing persistent state store");
        var entry = type.GetMethod(method, BindingFlags.Static | BindingFlags.NonPublic);
        Check(entry != null, "Missing state " + method);
        try { return entry.Invoke(null, args); }
        catch (TargetInvocationException e) { throw e.InnerException; }
    }
    static void Main()
    {
        string temp = Path.Combine(Environment.OSVersion.Platform == PlatformID.Win32NT ? Path.GetTempPath() : "/private/tmp", "trojaino-state-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(temp);
        try
        {
            string maximumState = @"C:\x".PadRight(247 - 1 - "receipt.bin".Length, 'a');
            Call("CheckWindowsSpelling", maximumState);
            Refuse(() => Call("CheckWindowsSpelling", maximumState + "a"), "Installed member exceeds");
            string root = Path.Combine(temp, "component"), state = Path.Combine(temp, "state");
            var owned = Bootstrap.CreateEmpty(root);
            Call("Store", owned, state);
            string file = Path.Combine(state, "receipt.bin");
            Check(File.Exists(file), "State not persisted");
            byte[] saved = File.ReadAllBytes(file);
            Refuse(() => Call("Store", owned, state));
            Check(File.ReadAllBytes(file).SequenceEqual(saved), "Existing state overwritten");
            var loaded = Call("Load", root, state); // No original in-memory state receipt.
            File.WriteAllText(Path.Combine(state, "unknown"), "retain");
            Refuse(() => Call("Load", root, state), "Unknown installed content");
            Refuse(() => Call("Remove", loaded), "Unknown installed content");
            Check(Directory.Exists(root) && File.ReadAllBytes(file).SequenceEqual(saved), "Predelete refusal altered known bytes");
            File.Delete(Path.Combine(state, "unknown"));
            File.WriteAllText(Path.Combine(root, "unknown"), "retain");
            Refuse(() => Call("Load", root, state), "Unknown installed content");
            File.Delete(Path.Combine(root, "unknown"));
            string held = Path.Combine(temp, "held.bin");
            File.Move(file, held); File.WriteAllBytes(file, saved);
            Refuse(() => Call("Load", root, state), "Installed object replaced");
            File.Delete(file); File.Move(held, file);
            string heldDir = Path.Combine(temp, "held-state");
            Directory.Move(state, heldDir); Directory.CreateDirectory(state);
            File.Move(Path.Combine(heldDir, "receipt.bin"), file);
            Refuse(() => Call("Load", root, state), "Installed object replaced");
            File.Move(file, Path.Combine(heldDir, "receipt.bin")); Directory.Delete(state); Directory.Move(heldDir, state);
            string moved = Path.Combine(temp, "moved-state"); Directory.Move(state, moved);
            Refuse(() => Call("Load", root, moved), "State location binding mismatch"); Directory.Move(moved, state);
            Refuse(() => Call("Load", root + "-other", state), "Receipt location binding mismatch");
            byte[] broken = (byte[])saved.Clone(); broken[0] = 99; File.WriteAllBytes(file, broken);
            Refuse(() => Call("Load", root, state), "Unsupported state version");
            File.WriteAllBytes(file, saved.Concat(new byte[] { 0 }).ToArray());
            Refuse(() => Call("Load", root, state), "Truncated or trailing state data");
            using (var stream = new FileStream(file, FileMode.Open, FileAccess.Write)) stream.SetLength(3 * 1024 * 1024 + 1);
            Refuse(() => Call("Load", root, state), "State ciphertext budget exceeded");
            File.WriteAllBytes(file, saved);
            Call("Remove", Call("Load", root, state));
            Check(!Directory.Exists(root) && !Directory.Exists(state), "Persistent removal did not finish");
            Console.WriteLine("PASS persistent reload/remove, overwrite/tamper/bounds/root/location/replaced state file+directory/unknown inventory predelete refusal; test-only codec NOT DPAPI");
            var fault = typeof(StateStore).GetField("Fault", BindingFlags.Static | BindingFlags.NonPublic);
            Check(fault != null, "Missing state write fault harness");
            foreach (string phase in new[] { "before", "partial", "after" })
            {
                owned = Bootstrap.CreateEmpty(root);
                Action<string, string> inject = (stage, target) => { if (stage == phase) throw new IOException("injected " + phase); };
                fault.SetValue(null, inject);
                try { Refuse(() => Call("Store", owned, state), "injected " + phase); }
                finally { fault.SetValue(null, null); }
                Bootstrap.Verify(owned);
                Check(!Directory.Exists(state), "Owned partial state not rolled back at " + phase);
                Bootstrap.Remove(owned);
            }
            owned = Bootstrap.CreateEmpty(root);
            Action<string, string> doubleFailure = (stage, target) => {
                if (stage == "partial") throw new IOException("original-write-failure");
                if (stage == "snapshot") throw new IOException("snapshot-failure");
                if (stage == "dispose") throw new IOException("dispose-failure");
            };
            fault.SetValue(null, doubleFailure);
            bool combined = false;
            try { Call("Store", owned, state); }
            catch (AggregateException e) {
                var messages = e.Flatten().InnerExceptions.Select(x => x.Message).ToArray();
                combined = messages.Contains("original-write-failure") && messages.Contains("snapshot-failure") && messages.Contains("dispose-failure")
                    && e.InnerExceptions.Count == 2; // Outer save error contains operation aggregate plus cleanup refusal.
            }
            catch (IOException) { /* Actual RED: missing snapshot hook/combined failure. */ }
            finally { fault.SetValue(null, null); }
            Check(combined, "Original write plus snapshot failures not both retained");
            Check(Directory.Exists(state), "Unverified partial state must be retained");
            Bootstrap.Verify(owned);
            Directory.Delete(state, true); Bootstrap.Remove(owned); // Owned disposable test cleanup only.
            owned = Bootstrap.CreateEmpty(root);
            Action<string, string> unknown = (stage, target) => {
                if (stage == "after") { File.WriteAllText(Path.Combine(state, "unknown"), "retain"); throw new IOException("injected unknown"); }
            };
            fault.SetValue(null, unknown);
            try { Refuse(() => Call("Store", owned, state), "unverified state retained"); }
            finally { fault.SetValue(null, null); }
            Bootstrap.Verify(owned);
            Check(File.ReadAllText(Path.Combine(state, "unknown")) == "retain", "Unknown state erased");
            Console.WriteLine("PASS before/partial/after write owned rollback, unknown state retention, component untouched");
        }
        finally { Directory.Delete(temp, true); } // Disposable harness only.
    }
}
