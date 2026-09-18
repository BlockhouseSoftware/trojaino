// Single-component persistent ownership. Not activation or crash recovery.
using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Security.Cryptography;

namespace Trojaino.Setup
{
    internal static class StateStore
    {
        const int MaxCipher = 3 * 1024 * 1024;
#if STATE_STORE_TESTS
        internal static Action<string, string> Fault = null;
#endif
        const int MaxInner = 2 * 1024 * 1024;
        static readonly UTF8Encoding Utf8 = new UTF8Encoding(false, true);
        internal sealed class Record
        {
            internal readonly Bootstrap.Receipt Component, State;
            internal Record(Bootstrap.Receipt component, Bootstrap.Receipt state)
            { Component = component; State = state; }
        }
        static void Require(bool ok, string why) { if (!ok) throw new InvalidDataException(why); }
        static void CheckWindowsSpelling(string state)
        { WindowsPreflight.ValidateSpelling(state, new[] { "receipt.bin" }); }
        static string Location(string state)
        {
            Require(!string.IsNullOrEmpty(state) && Path.IsPathRooted(state) && Path.GetFullPath(state) == state
                && !state.EndsWith(Path.DirectorySeparatorChar.ToString(), StringComparison.Ordinal)
                && !state.Any(char.IsControl), "Literal state directory required");
            if (Environment.OSVersion.Platform == PlatformID.Win32NT)
            {
                CheckWindowsSpelling(state); // Includes the file, before any creation/read.
                WindowsPreflight.Check(state, new[] { "receipt.bin" });
            }
            return Path.Combine(state, "receipt.bin");
        }
        static void Text(BinaryWriter writer, string text)
        {
            byte[] bytes = Utf8.GetBytes(text);
            Require(bytes.Length > 0 && bytes.Length <= 4096, "State string budget exceeded");
            writer.Write(bytes.Length); writer.Write(bytes);
        }
        static string Text(BinaryReader reader)
        {
            int size = reader.ReadInt32();
            Require(size > 0 && size <= 4096, "State string budget exceeded");
            byte[] bytes = reader.ReadBytes(size);
            Require(bytes.Length == size, "Truncated state string");
            return Utf8.GetString(bytes);
        }
        static void Platform()
        {
#if !STATE_STORE_TESTS
#if NETFRAMEWORK
            if (Environment.OSVersion.Platform != PlatformID.Win32NT) throw new PlatformNotSupportedException("State requires native Windows Framework");
#else
            throw new PlatformNotSupportedException("State requires native Windows Framework");
#endif
#endif
        }
        static byte[] Protect(byte[] plain)
        {
#if STATE_STORE_TESTS
            return (byte[])plain.Clone(); // Only explicitly separate test build, never runtime configuration.
#elif NETFRAMEWORK
            return ProtectedData.Protect(plain, Utf8.GetBytes("Trojaino.Setup.StateContainer.v1"), DataProtectionScope.CurrentUser);
#else
            throw new PlatformNotSupportedException();
#endif
        }
        static byte[] Unprotect(byte[] bytes)
        {
#if STATE_STORE_TESTS
            return (byte[])bytes.Clone();
#elif NETFRAMEWORK
            return ProtectedData.Unprotect(bytes, Utf8.GetBytes("Trojaino.Setup.StateContainer.v1"), DataProtectionScope.CurrentUser);
#else
            throw new PlatformNotSupportedException();
#endif
        }
        static byte[] SealComponent(Bootstrap.Receipt component, string path)
        {
#if STATE_STORE_TESTS
            return ReceiptCodec.TestEncode(component, path);
#else
            return ReceiptCodec.Seal(component, path);
#endif
        }
        static Bootstrap.Receipt OpenComponent(byte[] bytes, string root, string path)
        {
#if STATE_STORE_TESTS
            return ReceiptCodec.TestDecode(bytes, root, path);
#else
            return ReceiptCodec.Open(bytes, root, path);
#endif
        }
        internal static Record Store(Bootstrap.Receipt component, string state)
        {
            Platform();
            string path = Location(state);
            byte[] inner = SealComponent(component, path); // Verify/bind before creating state.
            Require(inner.Length > 0 && inner.Length <= MaxInner, "Inner receipt budget exceeded");
            var owned = Bootstrap.CreateEmpty(state);
            try
            {
                var file = new FileStream(path, FileMode.CreateNew, FileAccess.ReadWrite, FileShare.None);
                Exception operationFailure = null;
                try
                {
                    owned.Identities.Add(path, Bootstrap.Identity(path));
                    Exception writeFailure = null;
                    try
                    {
                        byte[] plain;
                        using (var memory = new MemoryStream())
                        using (var writer = new BinaryWriter(memory, Utf8))
                        {
                            writer.Write(1); Text(writer, state);
                            Text(writer, owned.Identities[state]); Text(writer, owned.Identities[path]);
                            writer.Write(inner.Length); writer.Write(inner); writer.Flush();
                            plain = memory.ToArray();
                        }
                        byte[] cipher;
                        try { cipher = Protect(plain); }
                        finally { Array.Clear(plain, 0, plain.Length); }
                        Require(cipher.Length > 0 && cipher.Length <= MaxCipher, "State ciphertext budget exceeded");
#if STATE_STORE_TESTS
                        if (Fault != null)
                        {
                            Fault("before", path);
                            file.WriteByte(cipher[0]); file.Flush(); Fault("partial", path); file.Position = 0;
                        }
#endif
                        file.Write(cipher, 0, cipher.Length); file.Flush(true);
                    }
                    catch (Exception failure) { writeFailure = failure; }
                    try
                    {
                        // Owned handle is the sole partial-byte source; failure retains unknown content.
#if STATE_STORE_TESTS
                        if (Fault != null) Fault("snapshot", path);
#endif
                        file.Flush(); file.Position = 0;
                        using (var hash = SHA256.Create())
                            owned.Hashes.Add(path, BitConverter.ToString(hash.ComputeHash(file)).Replace("-", "").ToLowerInvariant());
                        owned.Lengths.Add(path, file.Length);
                    }
                    catch (Exception snapshot)
                    {
                        if (writeFailure != null) throw new AggregateException("State write and ownership snapshot failed", writeFailure, snapshot);
                        throw;
                    }
                    if (writeFailure != null) throw writeFailure;
                }
                catch (Exception failure) { operationFailure = failure; }
                finally
                {
                    try
                    {
                        file.Dispose();
#if STATE_STORE_TESTS
                        if (Fault != null) Fault("dispose", path);
#endif
                    }
                    catch (Exception disposal)
                    {
                        operationFailure = operationFailure == null ? disposal
                            : new AggregateException("State operation and stream disposal failed", operationFailure, disposal);
                    }
                }
                if (operationFailure != null) throw operationFailure;
#if STATE_STORE_TESTS
                if (Fault != null) Fault("after", path);
#endif
                Bootstrap.Verify(owned);
                return Load(component.Root, state); // Real bounded readback and both tree checks.
            }
            catch (Exception failure)
            {
                try { Bootstrap.Remove(owned); }
                catch (Exception cleanup) { throw new AggregateException("State save failed; unverified state retained; component untouched", failure, cleanup); }
                throw;
            }
        }
        // This wrapper grants removal only, never installed-pair/activation authority.
        internal sealed class Removal
        {
            readonly Record record;
            internal Removal(Record record) { this.record = record; }
            internal string Root { get { return record.Component.Root; } }
            internal string StateRoot { get { return record.State.Root; } }
            internal void Remove() { StateStore.Remove(record); }
        }
        static Bootstrap.Receipt OpenRemainingComponent(byte[] bytes, string root, string path)
        {
#if STATE_STORE_TESTS
            return ReceiptCodec.TestDecodeRemaining(bytes, root, path);
#else
            return ReceiptCodec.OpenRemaining(bytes, root, path);
#endif
        }
        internal static Removal LoadRemaining(string root, string state)
        { return new Removal(LoadCore(root, state, OpenRemainingComponent)); }
        internal static Record Load(string root, string state)
        { return LoadCore(root, state, OpenComponent); }
        static Record LoadCore(string root, string state, Func<byte[], string, string, Bootstrap.Receipt> openComponent)
        {
            Platform();
            string path = Location(state);
            Bootstrap.PlainAncestors(state);
            Bootstrap.Identity(path); // Refuse reparse/hardlink reads; not ownership authority.
            byte[] cipher;
            using (var input = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
            {
                Require(input.Length > 0 && input.Length <= MaxCipher, "State ciphertext budget exceeded");
                cipher = new byte[(int)input.Length];
                int offset = 0, read;
                while (offset < cipher.Length && (read = input.Read(cipher, offset, cipher.Length - offset)) > 0) offset += read;
                Require(offset == cipher.Length && input.ReadByte() == -1, "State read length mismatch");
            }
            byte[] plain = Unprotect(cipher); // Authentication BEFORE any schema/identity parsing.
            try
            {
                Require(plain.Length > 0 && plain.Length <= MaxInner + 16384, "State plaintext budget exceeded");
                using (var memory = new MemoryStream(plain, false))
                using (var reader = new BinaryReader(memory, Utf8))
                {
                    Require(reader.ReadInt32() == 1, "Unsupported state version");
                    Require(Text(reader) == state, "State location binding mismatch");
                    string directoryIdentity = Text(reader), fileIdentity = Text(reader);
                    int length = reader.ReadInt32();
                    Require(length > 0 && length <= MaxInner, "Inner receipt budget exceeded");
                    byte[] inner = reader.ReadBytes(length);
                    Require(inner.Length == length && memory.Position == memory.Length, "Truncated or trailing state data");
                    var component = openComponent(inner, root, path);
                    // This is authenticated object ownership, not an adopted disk inventory.
                    var owned = new Bootstrap.Receipt(state);
                    owned.Identities.Add(state, directoryIdentity); owned.Identities.Add(path, fileIdentity);
                    owned.Hashes.Add(path, Bootstrap.Hash(cipher)); owned.Lengths.Add(path, cipher.Length);
                    Bootstrap.Verify(owned);
                    return new Record(component, owned);
                }
            }
            finally { Array.Clear(plain, 0, plain.Length); }
        }
        internal static void Remove(Record record)
        {
            Platform();
            if (record == null) throw new ArgumentNullException("record");
            Bootstrap.Verify(record.Component); Bootstrap.Verify(record.State);
            Bootstrap.Remove(record.Component);
            Bootstrap.Remove(record.State); // Not atomic; retain state on component failure.
        }
    }
}
