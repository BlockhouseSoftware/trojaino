using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Xml;

internal static class ExecutableTests
{
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern IntPtr LoadLibraryExW(string file, IntPtr reserved, uint flags);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern IntPtr FindResourceW(IntPtr module, IntPtr name, IntPtr type);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern IntPtr LoadResource(IntPtr module, IntPtr resource);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern IntPtr LockResource(IntPtr resource);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern uint SizeofResource(IntPtr module, IntPtr resource);
    [DllImport("kernel32.dll")]
    static extern bool FreeLibrary(IntPtr module);
    static void Assert(bool ok, string why) { if (!ok) throw new Exception("ASSERT: " + why); }
    static int Main(string[] args)
    {
        Assert(args.Length == 4, "test requires build artifact, approved payload and Framework references");
        Assert(File.Exists(args[0]), "production WinExe build artifact is missing");
        using (var stream = File.OpenRead(args[0]))
        using (var reader = new BinaryReader(stream))
        {
            Assert(reader.ReadUInt16() == 0x5a4d, "DOS header");
            stream.Position = 0x3c; int pe = reader.ReadInt32();
            Assert(pe > 0 && pe < stream.Length - 100, "PE offset");
            stream.Position = pe; Assert(reader.ReadUInt32() == 0x4550, "PE signature");
            Assert(reader.ReadUInt16() == 0x8664, "artifact must be x64");
            stream.Position = pe + 24; Assert(reader.ReadUInt16() == 0x20b, "PE32+ required");
            stream.Position = pe + 24 + 68; Assert(reader.ReadUInt16() == 2, "artifact must use GUI subsystem, not console");
        }
        // Metadata-only load: never invoke Main or query normal user folders.
        // Resolve only the Framework reference files already selected by native CI,
        // not adjacent target DLLs or assemblies discovered through runtime probing.
        AppDomain.CurrentDomain.ReflectionOnlyAssemblyResolve += delegate(object sender, ResolveEventArgs e) {
            var name = new AssemblyName(e.Name);
            var allowed = new[] { "mscorlib", "System", "System.Core", "System.Drawing", "System.Windows.Forms", "System.Security", "System.Xml", "System.IO.Compression", "System.Runtime.InteropServices.RuntimeInformation" };
            Assert(allowed.Contains(name.Name), "unexpected metadata dependency " + name.Name);
            string path = name.Name == "System.Runtime.InteropServices.RuntimeInformation" ? args[3] : Path.Combine(args[2], name.Name + ".dll");
            var dependency = Assembly.ReflectionOnlyLoadFrom(path);
            Assert(dependency.FullName == e.Name, "Framework dependency identity mismatch");
            return dependency;
        };
        var assembly = Assembly.ReflectionOnlyLoadFrom(Path.GetFullPath(args[0]));
        var entry = assembly.EntryPoint;
        Assert(entry != null && entry.DeclaringType.FullName == "Trojaino.Setup.SetupProgram" && entry.GetParameters().Length == 0, "production entry identity");
        Assert(CustomAttributeData.GetCustomAttributes(entry).Any(a => a.AttributeType.FullName == "System.STAThreadAttribute"), "production entry STA");
        foreach (var type in assembly.GetTypes())
            Assert(!type.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance).Any(m => m.Name.StartsWith("Test", StringComparison.Ordinal)), "test seam compiled into " + type.FullName);
        var resourceInfo = assembly.GetManifestResourceInfo("Trojaino.Setup.Payload");
        var embedded = ResourceLocation.Embedded | ResourceLocation.ContainedInManifestFile;
        Assert(resourceInfo != null && (resourceInfo.ResourceLocation & embedded) == embedded && resourceInfo.FileName == null && resourceInfo.ReferencedAssembly == null, "payload must be embedded, not linked");
        using (var actual = assembly.GetManifestResourceStream("Trojaino.Setup.Payload"))
        using (var expected = File.OpenRead(args[1]))
        using (var hash = SHA256.Create())
        {
            Assert(actual != null && actual.Length == expected.Length, "embedded payload length");
            Assert(hash.ComputeHash(actual).SequenceEqual(hash.ComputeHash(expected)), "embedded payload bytes differ");
        }
        // LOAD_LIBRARY_AS_DATAFILE: read the manifest without running executable code.
        var module = LoadLibraryExW(Path.GetFullPath(args[0]), IntPtr.Zero, 2);
        Assert(module != IntPtr.Zero, "read embedded manifest");
        try
        {
            var resource = FindResourceW(module, new IntPtr(1), new IntPtr(24));
            Assert(resource != IntPtr.Zero, "manifest resource missing");
            uint size = SizeofResource(module, resource); Assert(size > 0 && size < 65536, "manifest size");
            var ptr = LockResource(LoadResource(module, resource)); Assert(ptr != IntPtr.Zero, "manifest bytes missing");
            var bytes = new byte[(int)size]; Marshal.Copy(ptr, bytes, 0, bytes.Length);
            var document = new XmlDocument { XmlResolver = null };
            using (var data = new MemoryStream(bytes))
            using (var xml = XmlReader.Create(data, new XmlReaderSettings { DtdProcessing = DtdProcessing.Prohibit, XmlResolver = null })) document.Load(xml);
            var ns = new XmlNamespaceManager(document.NameTable); ns.AddNamespace("v1", "urn:schemas-microsoft-com:asm.v1"); ns.AddNamespace("v3", "urn:schemas-microsoft-com:asm.v3");
            var levels = document.SelectNodes("/v1:assembly/v3:trustInfo/v3:security/v3:requestedPrivileges/v3:requestedExecutionLevel", ns);
            Assert(levels.Count == 1 && levels[0].Attributes["level"] != null && levels[0].Attributes["uiAccess"] != null && levels[0].Attributes["level"].Value == "asInvoker" && levels[0].Attributes["uiAccess"].Value == "false", "manifest must not request elevation/UI bypass");
        }
        finally { Assert(FreeLibrary(module), "manifest module release"); }
        Console.WriteLine("PASS actual production x64 GUI WinExe: zero-argument STA entry, no test methods, exact embedded payload, embedded asInvoker/uiAccess=false manifest; metadata only, no normal-profile invocation; not Windows11/download/visual/Claude evidence");
        return 0;
    }
}
