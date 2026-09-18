// Ownership snapshot codec. No state-file I/O, activation or tree adoption.
using System;
using System.Collections.Generic;
using System.IO;
using System.Text.RegularExpressions;
using System.Linq;
using System.Text;

namespace Trojaino.Setup
{
    internal static class ReceiptCodec
    {
        const int MaxPlain = 1024 * 1024;
        static readonly UTF8Encoding Utf8 = new UTF8Encoding(false, true);
        static void Require(bool ok, string why) { if (!ok) throw new InvalidDataException(why); }
        static void Text(BinaryWriter writer, string value)
        {
            byte[] bytes = Utf8.GetBytes(value);
            Require(bytes.Length > 0 && bytes.Length <= 4096, "Receipt string budget exceeded");
            writer.Write(bytes.Length); writer.Write(bytes);
        }
        static string Text(BinaryReader reader)
        {
            int length = reader.ReadInt32();
            Require(length > 0 && length <= 4096, "Receipt string budget exceeded");
            byte[] bytes = reader.ReadBytes(length);
            Require(bytes.Length == length, "Truncated receipt string");
            return Utf8.GetString(bytes);
        }
        static void Literal(string path)
        {
            Require(!string.IsNullOrEmpty(path) && Path.IsPathRooted(path) && Path.GetFullPath(path) == path
                && !path.EndsWith(Path.DirectorySeparatorChar.ToString(), StringComparison.Ordinal)
                && !path.Any(char.IsControl), "Literal absolute receipt path required");
        }
        static void Locations(string root, string state)
        {
            Literal(root); Literal(state);
            Require(!string.Equals(root, state, StringComparison.OrdinalIgnoreCase)
                && !state.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)
                && !root.StartsWith(state + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase), "Receipt state location overlaps owned tree");
        }
        static void Schema(Bootstrap.Receipt receipt)
        {
            Require(receipt.Identities.Count > 0 && receipt.Identities.Count <= 4096
                && receipt.Identities.ContainsKey(receipt.Root) && !receipt.Hashes.ContainsKey(receipt.Root), "Invalid receipt root or count");
            Require(new HashSet<string>(receipt.Hashes.Keys, StringComparer.Ordinal).SetEquals(receipt.Lengths.Keys)
                && receipt.Hashes.Keys.All(receipt.Identities.ContainsKey), "Unowned receipt metadata");
            var aliases = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            long total = 0;
            foreach (var pair in receipt.Identities)
            {
                Literal(pair.Key);
                Require(aliases.Add(pair.Key), "Case alias in receipt");
                Require(Regex.IsMatch(pair.Value, @"\A-?[0-9]+(?::-?[0-9]+){3,4}\z"), "Invalid receipt identity");
                if (pair.Key != receipt.Root)
                {
                    Require(pair.Key.StartsWith(receipt.Root + Path.DirectorySeparatorChar, StringComparison.Ordinal), "Receipt path outside bound root");
                    string relative = pair.Key.Substring(receipt.Root.Length + 1);
                    var parts = relative.Split(Path.DirectorySeparatorChar);
                    Require(relative.Length <= 200 && parts.Length <= 12, "Receipt path budget exceeded");
                    foreach (string part in parts)
                        Require(Regex.IsMatch(part, @"\A[A-Za-z0-9_.-]{1,120}\z") && part != "." && part != ".."
                            && !part.EndsWith(".", StringComparison.Ordinal)
                            && !Regex.IsMatch(part.Split('.')[0], @"\A(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])\z", RegexOptions.IgnoreCase), "Unsafe receipt component");
                    string parent = Path.GetDirectoryName(pair.Key);
                    Require(receipt.Identities.ContainsKey(parent) && !receipt.Hashes.ContainsKey(parent), "Missing or file receipt parent");
                }
                if (receipt.Hashes.ContainsKey(pair.Key))
                {
                    long length = receipt.Lengths[pair.Key];
                    Require(length >= 0 && length <= 32 * 1024 * 1024 && (total += length) <= 128 * 1024 * 1024, "Receipt file budget exceeded");
                    Require(Regex.IsMatch(receipt.Hashes[pair.Key], @"\A[0-9a-f]{64}\z"), "Invalid receipt digest");
                }
            }
        }
        static byte[] Encode(Bootstrap.Receipt receipt, string state)
        {
            if (receipt == null) throw new ArgumentNullException("receipt");
            Locations(receipt.Root, state);
            Schema(receipt);
            Bootstrap.Verify(receipt);
            using (var memory = new MemoryStream())
            using (var writer = new BinaryWriter(memory, Utf8))
            {
                writer.Write(1); Text(writer, receipt.Root); Text(writer, state);
                writer.Write(receipt.Identities.Count);
                foreach (var pair in receipt.Identities.OrderBy(p => p.Key, StringComparer.Ordinal))
                {
                    Text(writer, pair.Key); Text(writer, pair.Value);
                    bool file = receipt.Hashes.ContainsKey(pair.Key);
                    writer.Write((byte)(file ? 1 : 0));
                    if (file) { writer.Write(receipt.Lengths[pair.Key]); Text(writer, receipt.Hashes[pair.Key]); }
                }
                writer.Flush();
                Require(memory.Length <= MaxPlain, "Receipt plaintext budget exceeded");
                return memory.ToArray();
            }
        }
        static Bootstrap.Receipt Decode(byte[] bytes, string root, string state)
        {
            Bootstrap.Receipt receipt = Parse(bytes, root, state);
            Bootstrap.Verify(receipt);
            return receipt;
        }
        static Bootstrap.Receipt DecodeRemaining(byte[] bytes, string root, string state)
        { return Bootstrap.Remaining(Parse(bytes, root, state)); }
        // Private schema parser; unchecked ownership never leaves this codec.
        static Bootstrap.Receipt Parse(byte[] bytes, string root, string state)
        {
            Locations(root, state);
            Require(bytes != null && bytes.Length > 0 && bytes.Length <= MaxPlain, "Receipt plaintext budget exceeded");
            using (var memory = new MemoryStream(bytes, false))
            using (var reader = new BinaryReader(memory, Utf8))
            {
                Require(reader.ReadInt32() == 1, "Unsupported receipt version");
                Require(Text(reader) == root && Text(reader) == state, "Receipt location binding mismatch");
                var receipt = new Bootstrap.Receipt(root);
                int count = reader.ReadInt32();
                Require(count > 0 && count <= 4096, "Receipt entry budget exceeded");
                string previous = null;
                for (int i = 0; i < count; i++)
                {
                    string path = Text(reader), identity = Text(reader);
                    Require(previous == null || StringComparer.Ordinal.Compare(previous, path) < 0, "Noncanonical or duplicate receipt path");
                    previous = path;
                    byte kind = reader.ReadByte();
                    Require(kind <= 1, "Invalid receipt object kind");
                    receipt.Identities.Add(path, identity);
                    if (kind == 1) { receipt.Lengths.Add(path, reader.ReadInt64()); receipt.Hashes.Add(path, Text(reader)); }
                }
                Require(memory.Position == memory.Length, "Trailing receipt data");
                Schema(receipt);
                return receipt;
            }
        }
        internal static byte[] Seal(Bootstrap.Receipt receipt, string state)
        {
#if NETFRAMEWORK
            if (Environment.OSVersion.Platform != PlatformID.Win32NT) throw new PlatformNotSupportedException("Receipt protection requires native Windows Framework");
            byte[] plain = Encode(receipt, state);
            try
            {
                byte[] sealedBytes = System.Security.Cryptography.ProtectedData.Protect(plain, Utf8.GetBytes("Trojaino.Setup.OwnershipReceipt.v1"), System.Security.Cryptography.DataProtectionScope.CurrentUser);
                Require(sealedBytes.Length > 0 && sealedBytes.Length <= 2 * MaxPlain, "Protected receipt budget exceeded");
                return sealedBytes;
            }
            finally { Array.Clear(plain, 0, plain.Length); }
#else
            throw new PlatformNotSupportedException("Receipt protection requires native Windows Framework");
#endif
        }
        internal static Bootstrap.Receipt Open(byte[] sealedBytes, string root, string state)
        {
#if NETFRAMEWORK
            if (Environment.OSVersion.Platform != PlatformID.Win32NT) throw new PlatformNotSupportedException("Receipt protection requires native Windows Framework");
            Require(sealedBytes != null && sealedBytes.Length > 0 && sealedBytes.Length <= 2 * MaxPlain, "Protected receipt budget exceeded");
            // No schema parsing or filesystem verification before OS authentication.
            byte[] plain = System.Security.Cryptography.ProtectedData.Unprotect(sealedBytes, Utf8.GetBytes("Trojaino.Setup.OwnershipReceipt.v1"), System.Security.Cryptography.DataProtectionScope.CurrentUser);
            try { return Decode(plain, root, state); }
            finally { Array.Clear(plain, 0, plain.Length); }
#else
            throw new PlatformNotSupportedException("Receipt protection requires native Windows Framework");
#endif
        }
        internal static Bootstrap.Receipt OpenRemaining(byte[] sealedBytes, string root, string state)
        {
#if NETFRAMEWORK
            if (Environment.OSVersion.Platform != PlatformID.Win32NT) throw new PlatformNotSupportedException("Receipt protection requires native Windows Framework");
            Require(sealedBytes != null && sealedBytes.Length > 0 && sealedBytes.Length <= 2 * MaxPlain, "Protected receipt budget exceeded");
            byte[] plain = System.Security.Cryptography.ProtectedData.Unprotect(sealedBytes, Utf8.GetBytes("Trojaino.Setup.OwnershipReceipt.v1"), System.Security.Cryptography.DataProtectionScope.CurrentUser);
            try { return DecodeRemaining(plain, root, state); }
            finally { Array.Clear(plain, 0, plain.Length); }
#else
            throw new PlatformNotSupportedException("Receipt protection requires native Windows Framework");
#endif
        }
#if RECEIPT_TESTS
        internal static byte[] TestEncode(Bootstrap.Receipt receipt, string state) { return Encode(receipt, state); }
        internal static Bootstrap.Receipt TestDecodeRemaining(byte[] bytes, string root, string state) { return DecodeRemaining(bytes, root, state); }
        internal static Bootstrap.Receipt TestDecode(byte[] bytes, string root, string state) { return Decode(bytes, root, state); }
#endif
    }
}
