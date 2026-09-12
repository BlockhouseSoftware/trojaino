using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Text;
using Trojaino.Setup;

internal static class ReceiptTests
{
    static void Assert(bool ok, string why) { if (!ok) throw new Exception("ASSERT: " + why); }
    static object Call(string method, params object[] args)
    {
        Type type = typeof(Bootstrap).Assembly.GetType("Trojaino.Setup.ReceiptCodec");
        Assert(type != null, "missing ownership receipt codec");
        MethodInfo entry = type.GetMethod(method, BindingFlags.Static | BindingFlags.NonPublic);
        Assert(entry != null, "missing codec entry " + method);
        try { return entry.Invoke(null, args); }
        catch (TargetInvocationException e) { throw e.InnerException; }
    }
    static Bootstrap.Receipt Fixture(string root)
    {
        byte[] data = Encoding.UTF8.GetBytes("inert owned bytes");
        byte[] archive;
        using (var stream = new MemoryStream())
        {
            using (var zip = new ZipArchive(stream, ZipArchiveMode.Create, true))
            using (var file = zip.CreateEntry("nested/file.txt").Open()) file.Write(data, 0, data.Length);
            archive = stream.ToArray();
        }
        return Bootstrap.Install(archive, Bootstrap.Hash(archive), new Dictionary<string,string> { {"nested/file.txt", Bootstrap.Hash(data)} }, root);
    }
    static byte[] Raw(Bootstrap.Receipt receipt, string state, bool reverse)
    {
        using (var memory = new MemoryStream())
        using (var writer = new BinaryWriter(memory))
        {
            Action<string> text = value => { byte[] bytes = Encoding.UTF8.GetBytes(value); writer.Write(bytes.Length); writer.Write(bytes); };
            writer.Write(1); text(receipt.Root); text(state); writer.Write(receipt.Identities.Count);
            var paths = receipt.Identities.Keys.OrderBy(p => p, StringComparer.Ordinal).ToArray();
            if (reverse) Array.Reverse(paths);
            foreach (string path in paths)
            {
                text(path); text(receipt.Identities[path]);
                bool file = receipt.Hashes.ContainsKey(path); writer.Write((byte)(file ? 1 : 0));
                if (file) { writer.Write(receipt.Lengths[path]); text(receipt.Hashes[path]); }
            }
            writer.Flush(); return memory.ToArray();
        }
    }
    static Bootstrap.Receipt Clone(Bootstrap.Receipt receipt)
    {
        var copy = new Bootstrap.Receipt(receipt.Root);
        foreach (var pair in receipt.Identities) copy.Identities.Add(pair.Key, pair.Value);
        foreach (var pair in receipt.Hashes) copy.Hashes.Add(pair.Key, pair.Value);
        foreach (var pair in receipt.Lengths) copy.Lengths.Add(pair.Key, pair.Value);
        return copy;
    }
    static void NegativeSchema(Bootstrap.Receipt receipt, string state, byte[] encoded)
    {
        string root = receipt.Root, file = receipt.Hashes.Keys.Single();
        Action<Action<Bootstrap.Receipt>,string> mutation = (change, why) => {
            var copy = Clone(receipt); change(copy);
            Refuse(() => Call("TestDecode", Raw(copy, state, false), root, state), why);
        };
        mutation(r => r.Identities.Add(root + "-outside", "1:2:3:4"), "foreign root prefix");
        mutation(r => r.Identities.Add(Path.Combine(root, "..", "outside"), "1:2:3:4"), "dot traversal");
        mutation(r => r.Identities.Add(Path.Combine(root, "NESTED"), "1:2:3:4"), "case alias");
        mutation(r => r.Identities.Remove(Path.GetDirectoryName(file)), "missing parent");
        mutation(r => r.Identities[root] = "bogus", "invalid identity");
        mutation(r => r.Hashes[file] = new string('g',64), "invalid digest");
        mutation(r => r.Lengths[file] = -1, "negative length");
        mutation(r => r.Lengths[file] = 32L*1024*1024+1, "large file length");
        mutation(r => { r.Hashes.Add(root, new string('0',64)); r.Lengths.Add(root,0); }, "file root");
        mutation(r => { string p=Path.Combine(root,"CON.txt"); r.Identities.Add(p,"1:2:3:4"); }, "reserved member");
        mutation(r => {
            string p = Path.GetDirectoryName(file); r.Hashes.Add(p,new string('0',64)); r.Lengths.Add(p,0);
        }, "file as parent");
        mutation(r => {
            for(int i=0;i<5;i++) { string p=Path.Combine(root,"budget"+i); r.Identities.Add(p,"1:2:3:4"); r.Hashes.Add(p,new string('0',64)); r.Lengths.Add(p,32L*1024*1024); }
        }, "aggregate length cap");
        mutation(r => r.Identities.Add(Path.Combine(root,new string('a',121)),"1:2:3:4"), "component length cap");
        mutation(r => {
            string p=root;
            for(int i=0;i<13;i++) { p=Path.Combine(p,"a"); r.Identities.Add(p,"1:2:3:4"); }
        }, "component depth cap with valid ancestors");
        int countOffset, firstEntry, firstKind, firstEnd;
        using(var memory=new MemoryStream(encoded,false))
        using(var reader=new BinaryReader(memory))
        {
            reader.ReadInt32();
            int length=reader.ReadInt32(); reader.ReadBytes(length);
            length=reader.ReadInt32(); reader.ReadBytes(length);
            countOffset=(int)memory.Position; reader.ReadInt32(); firstEntry=(int)memory.Position;
            length=reader.ReadInt32(); reader.ReadBytes(length);
            length=reader.ReadInt32(); reader.ReadBytes(length);
            firstKind=(int)memory.Position;
            Assert(reader.ReadByte()==0,"first entry is root directory"); firstEnd=(int)memory.Position;
        }
        foreach(int count in new[]{0,4097})
        {
            byte[] changed=(byte[])encoded.Clone(); Array.Copy(BitConverter.GetBytes(count),0,changed,countOffset,4);
            Refuse(()=>Call("TestDecode",changed,root,state),"entry count "+count);
        }
        byte[] wrongKind=(byte[])encoded.Clone(); wrongKind[firstKind]=2;
        Refuse(()=>Call("TestDecode",wrongKind,root,state),"invalid directory kind tag");
        byte[] duplicate=encoded.Take(firstEnd).Concat(encoded.Skip(firstEntry).Take(firstEnd-firstEntry)).Concat(encoded.Skip(firstEnd)).ToArray();
        Array.Copy(BitConverter.GetBytes(receipt.Identities.Count+1),0,duplicate,countOffset,4);
        Refuse(()=>Call("TestDecode",duplicate,root,state),"adjacent duplicate root entry");
        Refuse(() => Call("TestDecode", encoded, root + "-moved", state), "moved root binding");
        Refuse(() => Call("TestDecode", encoded, root, state + "-moved"), "moved state binding");
        Refuse(() => Call("TestDecode", encoded.Concat(new byte[] {0}).ToArray(), root, state), "trailing bytes");
        Refuse(() => Call("TestDecode", new byte[1024*1024+1], root, state), "plaintext cap");
        var bad = (byte[])encoded.Clone(); bad[0] = 2;
        Refuse(() => Call("TestDecode", bad, root, state), "unknown version");
        bad = (byte[])encoded.Clone(); Array.Copy(BitConverter.GetBytes(int.MaxValue),0,bad,4,4);
        Refuse(() => Call("TestDecode", bad, root, state), "string allocation cap");
        bad = (byte[])encoded.Clone(); bad[8] = 0xff;
        Refuse(() => Call("TestDecode", bad, root, state), "invalid UTF8");
        for (int i=0; i<encoded.Length; i++)
        {
            byte[] truncated = encoded.Take(i).ToArray();
            Refuse(() => Call("TestDecode", truncated, root, state), "truncation at " + i);
        }
        string unknown = Path.Combine(root,"unknown.txt"); File.WriteAllText(unknown,"retain");
        Refuse(() => Call("TestDecode", encoded, root, state), "unknown installed file");
        Assert(File.ReadAllText(unknown)=="retain", "unknown bytes retained"); File.Delete(unknown);
        byte[] original = File.ReadAllBytes(file); File.WriteAllText(file,"changed");
        Refuse(() => Call("TestDecode", encoded, root, state), "changed installed file");
        File.WriteAllBytes(file,original);
        string held=Path.Combine(Path.GetDirectoryName(root), "held.txt"); File.Move(file,held); File.WriteAllBytes(file,original);
        Refuse(() => Call("TestDecode", encoded, root, state), "same-byte replacement identity");
        File.Delete(file); File.Move(held,file);
        Console.WriteLine("PASS malformed schema/bounds, every truncation, location binding, unknown/changed/replaced tree refusal; bytes retained");
    }
    static void Refuse(Action action, string why)
    {
        try { action(); }
        catch (InvalidDataException) { return; }
        catch (EndOfStreamException) { return; }
        catch (DecoderFallbackException) { return; }
        throw new Exception("ASSERT: accepted " + why);
    }
    static int Main()
    {
        string parent = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "trojaino-receipt-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(parent);
        try
        {
            string root = Path.Combine(parent, "owned"), state = Path.Combine(parent, "state.bin");
            var receipt = Fixture(root);
            receipt.Lengths.Add(Path.Combine(root, "unowned"), 5);
            Refuse(() => Call("TestEncode", receipt, state), "unowned length metadata");
            receipt.Lengths.Remove(Path.Combine(root, "unowned"));
            Refuse(() => Call("TestEncode", receipt, Path.Combine(root, "state.bin")), "state file inside owned tree");
            Refuse(() => Call("TestEncode", receipt, root), "state file equals owned tree");
            Refuse(() => Call("TestEncode", receipt, parent), "state file is owned ancestor");
            Refuse(() => Call("TestEncode", receipt, "relative.bin"), "relative state file");
            Refuse(() => Call("TestEncode", receipt, Path.Combine(parent, ".", "state.bin")), "normalized state alias");
            byte[] encoded = (byte[])Call("TestEncode", receipt, state);
            Refuse(() => Call("TestDecode", Raw(receipt, state, true), root, state), "noncanonical receipt entry order");
            NegativeSchema(receipt, state, encoded);
            var restored = (Bootstrap.Receipt)Call("TestDecode", encoded, root, state);
            Bootstrap.Verify(restored);
            Assert(File.ReadAllText(Path.Combine(root, "nested", "file.txt")) == "inert owned bytes", "roundtrip retains bytes");
            Bootstrap.Remove(restored);
            Assert(!Directory.Exists(root) && !File.Exists(state), "recovered receipt removes only owned tree; no state file write");
            Console.WriteLine("PASS receipt codec nested owned roundtrip Verify/Remove; no persistence or DPAPI evidence");
            return 0;
        }
        catch (Exception e) { Console.WriteLine("FAIL " + e); return 1; }
        finally { Directory.Delete(parent, true); } // Disposable fixture only.
    }
}
