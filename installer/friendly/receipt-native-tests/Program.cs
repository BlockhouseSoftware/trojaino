// Production-symbol test: native Framework DPAPI, no plaintext test entry points.
using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using Trojaino.Setup;

internal static class NativeReceiptTests
{
    static void Assert(bool ok, string why) { if (!ok) throw new Exception("ASSERT: " + why); }
    static object Call(string method, params object[] args)
    {
        Type type = typeof(Bootstrap).Assembly.GetType("Trojaino.Setup.ReceiptCodec");
        Assert(type != null, "missing ownership receipt codec");
        MethodInfo entry = type.GetMethod(method, BindingFlags.Static | BindingFlags.NonPublic);
        Assert(entry != null, "missing production codec entry " + method);
        try { return entry.Invoke(null, args); }
        catch (TargetInvocationException e) { throw e.InnerException; }
    }
    static void Refuse(Action action, string why)
    {
        try { action(); }
        catch (InvalidDataException) { return; }
        catch (CryptographicException) { return; }
        throw new Exception("ASSERT: accepted " + why);
    }
    static Bootstrap.Receipt Fixture(string root)
    {
        byte[] data=Encoding.UTF8.GetBytes("inert owned bytes"), archive;
        using(var memory=new MemoryStream())
        {
            using(var zip=new ZipArchive(memory,ZipArchiveMode.Create,true))
            using(var output=zip.CreateEntry("nested/file.txt").Open()) output.Write(data,0,data.Length);
            archive=memory.ToArray();
        }
        return Bootstrap.Install(archive,Bootstrap.Hash(archive),new Dictionary<string,string>{{"nested/file.txt",Bootstrap.Hash(data)}},root);
    }
    static int Main()
    {
        Type codec = typeof(Bootstrap).Assembly.GetType("Trojaino.Setup.ReceiptCodec");
        Assert(codec != null, "missing receipt codec");
        Assert(codec.GetMethod("TestEncode", BindingFlags.NonPublic | BindingFlags.Static) == null
            && codec.GetMethod("TestDecode", BindingFlags.NonPublic | BindingFlags.Static) == null, "no plaintext injection in production on any platform");
        if (Environment.OSVersion.Platform != PlatformID.Win32NT)
        {
            try { Call("Seal", null, null); throw new Exception("non-Windows Seal did not refuse"); }
            catch (PlatformNotSupportedException) { }
            try { Call("Open", new byte[]{1}, "/absent", "/state"); throw new Exception("non-Windows Open did not refuse"); }
            catch (PlatformNotSupportedException) { }
            Console.WriteLine("PASS non-Windows production Seal/Open refuse; SKIP actual Framework DPAPI (requires Windows)");
            return 0;
        }
        string parent=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),"trojaino-native-receipt-"+Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(parent);
        try
        {
            string root=Path.Combine(parent,"owned"), state=Path.Combine(parent,"state.bin");
            var receipt=Fixture(root);
            byte[] sealedBytes=(byte[])Call("Seal",receipt,state);
            Assert(sealedBytes.Length>0 && !File.Exists(state),"protected output exists without state write");
            var reopened=(Bootstrap.Receipt)Call("Open",sealedBytes,root,state);
            Bootstrap.Verify(reopened);
            Refuse(()=>Call("Open",sealedBytes,root+"-moved",state),"moved root binding");
            Refuse(()=>Call("Open",sealedBytes,root,state+"-moved"),"moved state binding");
            byte[] changed=(byte[])sealedBytes.Clone(); changed[changed.Length-1]^=1;
            Refuse(()=>Call("Open",changed,root,state),"corrupt protected blob");
            Refuse(()=>Call("Open",new byte[2*1024*1024+1],root,state),"ciphertext budget");
            Refuse(()=>Call("Open",new byte[]{1,2,3},root,state),"plaintext fallback");
            string file=Path.Combine(root,"nested","file.txt"), unknown=Path.Combine(root,"unknown.txt");
            File.WriteAllText(unknown,"retain");
            Refuse(()=>Call("Open",sealedBytes,root,state),"unknown installed bytes");
            Assert(File.ReadAllText(unknown)=="retain","unknown bytes preserved"); File.Delete(unknown);
            byte[] original=File.ReadAllBytes(file); File.WriteAllText(file,"changed");
            Refuse(()=>Call("Open",sealedBytes,root,state),"changed installed bytes");
            Refuse(()=>Call("Seal",receipt,state),"seal changed tree"); File.WriteAllBytes(file,original);
            string held=Path.Combine(parent,"held.txt"); File.Move(file,held); File.WriteAllBytes(file,original);
            Refuse(()=>Call("Open",sealedBytes,root,state),"same-byte replacement identity");
            File.Delete(file); File.Move(held,file);
            reopened=(Bootstrap.Receipt)Call("Open",sealedBytes,root,state);
            Bootstrap.Verify(reopened); Bootstrap.Remove(reopened);
            Assert(!Directory.Exists(root) && !File.Exists(state),"owned removal only; no state persistence");
            Console.WriteLine("PASS actual Framework DPAPI CurrentUser Seal/Open, tamper/plaintext/cap/binding/stale/replaced/unknown refusal, Verify/Remove; no persisted uninstaller or GUI");
            return 0;
        }
        catch(Exception e) { Console.WriteLine("FAIL "+e); return 1; }
        finally { Directory.Delete(parent,true); } // Disposable fixture only.
    }
}
