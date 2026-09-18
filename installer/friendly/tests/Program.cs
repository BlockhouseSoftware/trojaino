using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;

internal static class Tests
{
    static string Hash(byte[] data) { using (var h = SHA256.Create()) return BitConverter.ToString(h.ComputeHash(data)).Replace("-", "").ToLowerInvariant(); }
    static void Assert(bool ok, string message) { if (!ok) throw new Exception("ASSERT: " + message); }
    static object Call(string method, params object[] args)
    {
        var type = Assembly.GetExecutingAssembly().GetType("Trojaino.Setup.Bootstrap");
        Assert(type != null, "native bootstrap behavior is missing");
        try { return type.GetMethod(method).Invoke(null, args); }
        catch (TargetInvocationException e) { throw e.InnerException; }
    }
    static byte[] Zip(Dictionary<string, byte[]> files, int attributes = 0x1800000)
    {
        using (var memory = new MemoryStream())
        {
            using (var zip = new ZipArchive(memory, ZipArchiveMode.Create, true))
                foreach (var file in files)
                {
                    var entry = zip.CreateEntry(file.Key);
                    entry.ExternalAttributes = attributes;
                    using (var output = entry.Open()) output.Write(file.Value, 0, file.Value.Length);
                }
            return memory.ToArray();
        }
    }
    static void FreshPinnedInstall()
    {
        var parent = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "trojaino-bootstrap-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(parent);
        try
        {
            var destination = Path.Combine(parent, "runtime");
            var files = new Dictionary<string, byte[]> {
                {"python.exe", Encoding.UTF8.GetBytes("not executable; must only be copied")},
                {"Lib/license.txt", Encoding.UTF8.GetBytes("vendor bytes")},
                {"python314._pth", Encoding.UTF8.GetBytes("python314.zip\n.\n")}
            };
            var data = Zip(files);
            var pins = files.ToDictionary(f => f.Key, f => Hash(f.Value));
            var tampered = (byte[])data.Clone(); tampered[0] ^= 1;
            try { Call("Install", tampered, Hash(data), pins, destination); throw new Exception("ASSERT: tampered archive accepted"); }
            catch (InvalidDataException) { }
            Assert(!Directory.Exists(destination), "digest rejection before writing");
            var receipt = Call("Install", data, Hash(data), pins, destination);
            Assert(receipt != null, "ownership receipt returned");
            Assert(Directory.GetFiles(destination, "*", SearchOption.AllDirectories).Length == files.Count, "exact installed inventory");
            foreach (var file in files) Assert(File.ReadAllBytes(Path.Combine(destination, file.Key)).SequenceEqual(file.Value), "vendor bytes preserved: " + file.Key);
            Assert(!File.Exists(Path.Combine(parent, "settings.json")), "no settings activation");
        }
        finally { Directory.Delete(parent, true); } // Only the test's own disposable tree.
    }
    static void OwnedRemoval()
    {
        var emptyMethod = typeof(Trojaino.Setup.Bootstrap).GetMethod("CreateEmpty");
        Assert(emptyMethod != null, "private empty scratch creation is missing");
        string scratchRoot = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "trojaino-empty-test-" + Guid.NewGuid().ToString("N"));
        var empty = Call("CreateEmpty", scratchRoot);
        Call("Verify", empty);
        try { Call("CreateEmpty", scratchRoot); throw new Exception("ASSERT: existing scratch reused"); }
        catch (System.ComponentModel.Win32Exception) { }
        File.WriteAllText(Path.Combine(scratchRoot, "unknown.dll"), "not executable");
        try { Call("Remove", empty); throw new Exception("ASSERT: unknown scratch content deleted"); }
        catch (InvalidDataException) { }
        Assert(File.ReadAllText(Path.Combine(scratchRoot, "unknown.dll")) == "not executable", "prior scratch bytes preserved");
        File.Delete(Path.Combine(scratchRoot, "unknown.dll"));
        Call("Remove", empty);
        Assert(!Directory.Exists(scratchRoot), "private empty scratch removed");
        var parent = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "trojaino-bootstrap-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(parent);
        try
        {
            var destination = Path.Combine(parent, "runtime");
            var files = new Dictionary<string, byte[]> { {"Lib/a.txt", new byte[] {1,2,3}}, {"b.txt", new byte[] {4}} };
            var data = Zip(files);
            var pins = files.ToDictionary(f => f.Key, f => Hash(f.Value));
            var receipt = Call("Install", data, Hash(data), pins, destination);
            Assert(receipt.GetType().Name == "Receipt", "install must return real ownership receipt");
            Call("Verify", receipt);
            File.WriteAllText(Path.Combine(destination, "unknown.txt"), "keep me");
            try { Call("Remove", receipt); throw new Exception("ASSERT: unknown content deleted"); } catch (InvalidDataException) { }
            Assert(File.Exists(Path.Combine(destination, "Lib/a.txt")), "refusal before any deletion");
            File.Delete(Path.Combine(destination, "unknown.txt"));
            var moved = destination + "-moved";
            Directory.Move(destination, moved);
            Directory.CreateDirectory(destination);
            Directory.CreateDirectory(Path.Combine(destination, "Lib"));
            foreach (var f in files) File.WriteAllBytes(Path.Combine(destination, f.Key), f.Value);
            try { Call("Remove", receipt); throw new Exception("ASSERT: substituted identical tree deleted"); } catch (InvalidDataException) { }
            Assert(File.Exists(Path.Combine(destination, "b.txt")), "substituted bytes preserved");
            Directory.Delete(destination, true);
            Directory.Move(moved, destination);
            Call("Remove", receipt);
            Assert(!Directory.Exists(destination), "verified owned tree removed");
        }
        finally { Directory.Delete(parent, true); }
    }
    static void RemainingOwnedRemoval()
    {
        var method = typeof(Trojaino.Setup.Bootstrap).GetMethod("Remaining", BindingFlags.Static | BindingFlags.NonPublic);
        Assert(method != null, "authenticated-receipt remaining-file verification is missing");
        Func<object, object> remaining = original => {
            try { return method.Invoke(null, new[] {original}); }
            catch (TargetInvocationException error) { throw error.InnerException; }
        };
        string parent = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "trojaino-remaining-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(parent);
        try
        {
            string destination = Path.Combine(parent, "runtime");
            var files = new Dictionary<string, byte[]> { {"Lib/a.txt", new byte[] {1, 2, 3}}, {"b.txt", new byte[] {4}}, {"Lib/gone.txt", new byte[] {5}} };
            byte[] data = Zip(files);
            var original = Call("Install", data, Hash(data), files.ToDictionary(f => f.Key, f => Hash(f.Value)), destination);
            File.Delete(Path.Combine(destination, "Lib", "gone.txt"));
            try { Call("Verify", original); throw new Exception("ASSERT: normal verification accepted missing member"); } catch (InvalidDataException) { }
            string unknown = Path.Combine(destination, "unknown.txt"); File.WriteAllBytes(unknown, new byte[] {255});
            try { remaining(original); throw new Exception("ASSERT: removal-only verification adopted unknown member"); } catch (InvalidDataException) { }
            Assert(File.ReadAllBytes(unknown).SequenceEqual(new byte[] {255}) && File.ReadAllBytes(Path.Combine(destination, "b.txt")).SequenceEqual(new byte[] {4}), "unknown refusal changed bytes");
            File.Delete(unknown);
            string replaced = Path.Combine(destination, "Lib", "a.txt"), held = Path.Combine(parent, "held.txt");
            File.Move(replaced, held); File.WriteAllBytes(replaced, files["Lib/a.txt"]);
            try { remaining(original); throw new Exception("ASSERT: removal-only verification trusted same-byte replacement"); } catch (InvalidDataException) { }
            Assert(File.Exists(held) && File.ReadAllBytes(replaced).SequenceEqual(files["Lib/a.txt"]), "replacement refusal changed bytes");
            File.Delete(replaced); File.Move(held, replaced);
            File.WriteAllBytes(replaced, new byte[] {9, 9, 9});
            try { remaining(original); throw new Exception("ASSERT: removal-only verification trusted changed bytes"); } catch (InvalidDataException) { }
            File.WriteAllBytes(replaced, files["Lib/a.txt"]);
            string library = Path.Combine(destination, "Lib"), heldLibrary = Path.Combine(parent, "held-library");
            Directory.Move(library, heldLibrary);
            try { remaining(original); throw new Exception("ASSERT: removal recovery accepted missing directory"); } catch (InvalidDataException) { }
            File.WriteAllBytes(library, new byte[] {6});
            try { remaining(original); throw new Exception("ASSERT: removal recovery accepted directory-to-file change"); } catch (InvalidDataException) { }
            Assert(File.ReadAllBytes(library).SequenceEqual(new byte[] {6}) && File.Exists(Path.Combine(destination, "b.txt")), "kind refusal deleted content");
            File.Delete(library); Directory.Move(heldLibrary, library);
            string heldRoot = Path.Combine(parent, "held-runtime");
            Directory.Move(destination, heldRoot); Directory.CreateDirectory(destination);
            try { remaining(original); throw new Exception("ASSERT: removal recovery accepted replaced root"); } catch (InvalidDataException) { }
            Assert(File.Exists(Path.Combine(heldRoot, "b.txt")), "root refusal changed original");
            Directory.Delete(destination); Directory.Move(heldRoot, destination);
            File.Move(replaced, held); Directory.CreateDirectory(replaced);
            try { remaining(original); throw new Exception("ASSERT: removal recovery accepted file-to-directory change"); } catch (InvalidDataException) { }
            Directory.Delete(replaced); File.Move(held, replaced);
            object subset = remaining(original);
            Call("Verify", subset);
            try { Call("Verify", original); throw new Exception("ASSERT: remaining verification mutated original receipt"); } catch (InvalidDataException) { }
            Call("Remove", subset); Assert(!Directory.Exists(destination), "verified survivors were not removed");
        }
        finally { Directory.Delete(parent, true); } // Inert test-only owned fixture, no helper started.
    }
    static void FailedWriteRollsBackOnlyOwnedTree()
    {
        var parent = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "trojaino-bootstrap-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(parent);
        try
        {
            File.WriteAllText(Path.Combine(parent, "unrelated.txt"), "keep");
            var destination = Path.Combine(parent, "runtime");
            var files = new Dictionary<string, byte[]> { {"a.txt", new byte[] {1,2,3}}, {"Lib/b.txt", new byte[] {4}} };
            var data = Zip(files); var pins = files.ToDictionary(f => f.Key, f => Hash(f.Value));
            Trojaino.Setup.Bootstrap.AfterWrite = path => { throw new IOException("injected disk failure"); };
            try { Call("Install", data, Hash(data), pins, destination); throw new Exception("ASSERT: fault not exercised"); }
            catch (IOException e) { Assert(e.Message == "injected disk failure", "original failure reported"); }
            Assert(!Directory.Exists(destination), "failed installation must rollback owned directory");
            Assert(File.ReadAllText(Path.Combine(parent, "unrelated.txt")) == "keep", "unrelated bytes preserved");
        }
        finally { Trojaino.Setup.Bootstrap.AfterWrite = null; Directory.Delete(parent, true); }
    }
    static void PartialWriteRollsBack()
    {
        var parent = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "trojaino-bootstrap-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(parent);
        try
        {
            var destination = Path.Combine(parent, "runtime");
            var files = new Dictionary<string, byte[]> { {"a.txt", new byte[] {1,2,3}} };
            var data = Zip(files); var pins = files.ToDictionary(f => f.Key, f => Hash(f.Value));
            bool fired = false;
            Trojaino.Setup.Bootstrap.DuringWrite = path => { fired = true; throw new IOException("partial disk failure"); };
            Exception failure = null;
            try { Call("Install", data, Hash(data), pins, destination); } catch (Exception e) { failure = e; }
            Assert(fired && failure != null, "partial write fault exercised");
            Assert(!Directory.Exists(destination), "partial file and owned directory must rollback");
            Assert(failure is IOException && failure.Message == "partial disk failure", "original failure preserved");
        }
        finally { Trojaino.Setup.Bootstrap.DuringWrite = null; Directory.Delete(parent, true); }
    }
    static void RejectSpecialMetadataBeforeWriting()
    {
        var parent = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "trojaino-bootstrap-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(parent);
        try
        {
            var files = new Dictionary<string, byte[]> { {"a.txt", new byte[] {1}} };
            foreach (int attributes in new int[] { 0x1800400, 0x1800010, 0x1800008, unchecked((int)0xa0000000) })
            {
                var destination = Path.Combine(parent, "runtime"); var data = Zip(files, attributes);
                var pins = files.ToDictionary(f => f.Key, f => Hash(f.Value));
                bool rejected = false;
                try { Call("Install", data, Hash(data), pins, destination); } catch (InvalidDataException) { rejected = true; }
                Assert(rejected && !Directory.Exists(destination), "special member metadata rejected before writing: " + attributes);
            }
        }
        finally { Directory.Delete(parent, true); }
    }
    static void RejectUnsafeArchives()
    {
        var parent = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "trojaino-bootstrap-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(parent);
        try
        {
            var cases = new List<Dictionary<string, byte[]>>();
            foreach (string name in new[] {"../escape", "a/../../escape", "C:/evil", "a:stream", "CON.txt", "a./b", "a\\b", "/abs", "a/", "a//b", "é.txt", new string('a', 121)})
                cases.Add(new Dictionary<string, byte[]> { {name, new byte[] {1}} });
            cases.Add(new Dictionary<string, byte[]> { {"Lib/a", new byte[] {1}}, {"lib/b", new byte[] {2}} });
            cases.Add(new Dictionary<string, byte[]> { {"a", new byte[] {1}}, {"a/b", new byte[] {2}} });
            cases.Add(new Dictionary<string, byte[]> { {"huge", new byte[32 * 1024 * 1024 + 1]} });
            foreach (var files in cases)
            {
                var destination = Path.Combine(parent, "runtime"); var data = Zip(files);
                bool denied = false;
                try { Call("Install", data, Hash(data), files.ToDictionary(f => f.Key, f => Hash(f.Value)), destination); }
                catch (InvalidDataException) { denied = true; }
                Assert(denied && !Directory.Exists(destination), "unsafe archive refused before write: " + files.First().Key);
            }
            Console.WriteLine("Negative archive fixtures: " + cases.Count);
        }
        finally { Directory.Delete(parent, true); }
    }
    static void ExistingAndLinkedDestinationsPreserved()
    {
        var parent = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "trojaino-bootstrap-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(parent);
        try
        {
            var destination = Path.Combine(parent, "runtime"); Directory.CreateDirectory(destination);
            File.WriteAllText(Path.Combine(destination, "keep.txt"), "original");
            var files = new Dictionary<string, byte[]> { {"a.txt", new byte[] {1}} }; var data = Zip(files);
            bool denied = false;
            try { Call("Install", data, Hash(data), files.ToDictionary(f => f.Key, f => Hash(f.Value)), destination); }
            catch (System.ComponentModel.Win32Exception) { denied = true; }
            Assert(denied && Directory.GetFiles(destination).Length == 1 && File.ReadAllText(Path.Combine(destination, "keep.txt")) == "original", "existing destination bytes preserved");
            var link = Path.Combine(parent, "link"); Directory.CreateSymbolicLink(link, destination);
            denied = false;
            try { Call("Install", data, Hash(data), files.ToDictionary(f => f.Key, f => Hash(f.Value)), Path.Combine(link, "new")); }
            catch (InvalidDataException) { denied = true; }
            Assert(denied && !Directory.Exists(Path.Combine(destination, "new")), "reparse ancestor refused");
            Directory.Delete(link);
        }
        finally { Directory.Delete(parent, true); }
    }
    static void ExerciseOfficialRuntime(string path)
    {
        // Developer test only. The exact approved archive pin authenticates its inventory first.
        const string expected = "d297e5ff019966817ad8502465176139f2d3d840fa4ed84b13bed399a6ab1f15";
        var data = File.ReadAllBytes(path); Assert(Hash(data) == expected, "official runtime pin before parsing");
        var files = new Dictionary<string, byte[]>();
        using (var memory = new MemoryStream(data))
        using (var zip = new ZipArchive(memory, ZipArchiveMode.Read))
            foreach (var entry in zip.Entries)
                using (var input = entry.Open())
                using (var output = new MemoryStream()) { input.CopyTo(output); files.Add(entry.FullName, output.ToArray()); }
        var destination = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "trojaino-bootstrap-real-" + Guid.NewGuid().ToString("N"));
        var receipt = Call("Install", data, expected, files.ToDictionary(f => f.Key, f => Hash(f.Value)), destination);
        foreach (var file in files) Assert(File.ReadAllBytes(Path.Combine(destination, file.Key)).SequenceEqual(file.Value), "real vendor file match " + file.Key);
        Call("Verify", receipt); Call("Remove", receipt);
        Assert(!Directory.Exists(destination), "real runtime owned removal");
        Console.WriteLine("PASS OfficialRuntime: sha256=" + expected + "; files=" + files.Count + "; all bytes verified; NOT EXECUTED; owned removal verified");
    }
    static void ChangedBytesAndRollbackIntruderPreserved()
    {
        var parent = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "trojaino-bootstrap-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(parent);
        try
        {
            var destination = Path.Combine(parent, "runtime");
            var files = new Dictionary<string, byte[]> { {"a.txt", new byte[] {1,2,3}} };
            var data = Zip(files); var pins = files.ToDictionary(f => f.Key, f => Hash(f.Value));
            var receipt = Call("Install", data, Hash(data), pins, destination);
            if (System.Runtime.InteropServices.RuntimeInformation.IsOSPlatform(System.Runtime.InteropServices.OSPlatform.OSX))
                Assert((File.GetUnixFileMode(destination) & (UnixFileMode.GroupRead | UnixFileMode.GroupWrite | UnixFileMode.GroupExecute | UnixFileMode.OtherRead | UnixFileMode.OtherWrite | UnixFileMode.OtherExecute)) == 0, "private macOS root permissions");
            File.WriteAllBytes(Path.Combine(destination, "a.txt"), new byte[] {4,5,6});
            bool denied = false;
            try { Call("Remove", receipt); } catch (InvalidDataException) { denied = true; }
            Assert(denied && File.ReadAllBytes(Path.Combine(destination, "a.txt")).SequenceEqual(new byte[] {4,5,6}), "same-length changed bytes not removed");
            File.WriteAllBytes(Path.Combine(destination, "a.txt"), files["a.txt"]);
            Call("Remove", receipt);
            Trojaino.Setup.Bootstrap.AfterWrite = path => { File.WriteAllText(Path.Combine(destination, "unknown.txt"), "preserve"); throw new IOException("injected failure plus unexpected content"); };
            AggregateException failure = null;
            try { Call("Install", data, Hash(data), pins, destination); } catch (AggregateException e) { failure = e; }
            Assert(failure != null && failure.InnerExceptions.Count == 2, "cleanup refusal and original failure both reported");
            Assert(File.ReadAllText(Path.Combine(destination, "unknown.txt")) == "preserve" && File.Exists(Path.Combine(destination, "a.txt")), "rollback refuses entire unknown tree before deleting owned bytes");
        }
        finally { Trojaino.Setup.Bootstrap.AfterWrite = null; Directory.Delete(parent, true); }
    }
    static void WindowsLiteralDestinations()
    {
        var type = Assembly.GetExecutingAssembly().GetType("Trojaino.Setup.WindowsPreflight");
        Assert(type != null, "Windows pre-write path eligibility behavior is missing");
        var method = type.GetMethod("ValidateSpelling", BindingFlags.NonPublic | BindingFlags.Static);
        Assert(method != null, "Windows literal path validator is missing");
        Action<string, string[]> validate = (path, members) => {
            try { method.Invoke(null, new object[] {path, members}); }
            catch (TargetInvocationException e) { throw e.InnerException; }
        };
        foreach (string path in new[] { @"C:\Users\Ada\Trojaino", @"D:\Users\Ada Hansen\Trojaino", @"C:\Users\Astrid Øst\Trojaino" })
            validate(path, new[] {"python.exe", "Lib/license.txt"});
        var rejected = new[] { "", @"C:\", @"C:relative", @"\rooted", @"\\server\share\new", @"\\?\C:\new", @"\\.\C:\new",
            "C:/Users/Ada/new", @"C:\Users\..\new", @"C:\Users\.\new", @"C:\Users\\new", @"C:\Users\new\",
            @"C:\Users\new.", @"C:\Users\new ", @"C:\Users\a:stream", @"C:\Users\CON.txt", @"C:\Users\LPT1.log",
            @"C:\Users\COM¹.log", @"C:\Users\CONIN$", @"C:\Users\CONOUT$", @"C:\Users\CON .txt", @"C:\Users\a?b", @"C:\Users\a*b", "C:\\Users\\bad\nname", "C:\\Users\\bad\0name",
            "C:\\" + new string('a', 246) };
        foreach (string path in rejected)
        {
            bool denied = false;
            try { validate(path, new[] {"a.txt"}); } catch (InvalidDataException) { denied = true; }
            Assert(denied, "nonliteral Windows path refused: " + path);
        }
        foreach (char control in new[] {'\n', '\0', '\t'})
        {
            string path = @"C:\Users\bad" + control + "name";
            Assert(path.Split('\\').Length == 3, "control fixture has exactly two separators");
            bool denied = false;
            try { validate(path, new[] {"a.txt"}); } catch (InvalidDataException) { denied = true; }
            Assert(denied, "control character independently refused");
        }
        bool nullDenied = false;
        try { validate(null, new[] {"a.txt"}); } catch (InvalidDataException) { nullDenied = true; }
        Assert(nullDenied, "null destination refused");
        validate(@"C:\" + new string('a', 242), new[] {"a"}); // 247 including member separator.
        bool exactBoundaryDenied = false;
        try { validate(@"C:\" + new string('a', 243), new[] {"a"}); } catch (InvalidDataException) { exactBoundaryDenied = true; }
        Assert(exactBoundaryDenied, "248-character expanded path refused");
        bool overBudget = false;
        try { validate(@"C:\Users\Ada\Trojaino", new[] {new string('a', 240)}); }
        catch (InvalidDataException) { overBudget = true; }
        Assert(overBudget, "final expanded member path refused before creating destination");
        Console.WriteLine("Windows lexical negative fixtures: " + rejected.Length + "; portable only");
    }
    static void WindowsNativeEligibility()
    {
        var type = Assembly.GetExecutingAssembly().GetType("Trojaino.Setup.WindowsPreflight");
        var method = type.GetMethod("ValidateEnvironment", BindingFlags.NonPublic | BindingFlags.Static);
        Assert(method != null, "Windows native environment eligibility behavior is missing");
        Action<ushort, DriveType, string> validate = (machine, drive, format) => {
            try { method.Invoke(null, new object[] {machine, drive, format}); }
            catch (TargetInvocationException e) { throw e.InnerException; }
        };
        validate(0x8664, DriveType.Fixed, "NTFS");
        foreach (ushort machine in new ushort[] {0, 0x014c, 0xaa64, 0x0200})
        {
            bool denied = false;
            try { validate(machine, DriveType.Fixed, "NTFS"); } catch (InvalidDataException) { denied = true; }
            Assert(denied, "unknown/non-x64 native machine refused, including emulated x64 on ARM64");
        }
        foreach (DriveType drive in Enum.GetValues(typeof(DriveType)))
        {
            if (drive == DriveType.Fixed) continue;
            bool denied = false;
            try { validate(0x8664, drive, "NTFS"); } catch (InvalidDataException) { denied = true; }
            Assert(denied, "non-fixed drive refused: " + drive);
        }
        foreach (string format in new[] {null, "", "FAT32", "exFAT", "ReFS"})
        {
            bool denied = false;
            try { validate(0x8664, DriveType.Fixed, format); } catch (InvalidDataException) { denied = true; }
            Assert(denied, "unknown/non-NTFS format refused");
        }
    }
    static void NativeProbePlatformBoundary()
    {
        var type = Assembly.GetExecutingAssembly().GetType("Trojaino.Setup.WindowsPreflight");
        var method = type.GetMethod("Check", BindingFlags.NonPublic | BindingFlags.Static);
        Assert(method != null, "Windows native pre-write probe is missing");
        if (Environment.OSVersion.Platform != PlatformID.Win32NT)
        {
            bool denied = false;
            try { method.Invoke(null, new object[] {@"C:\Users\Ada\Trojaino", new[] {"python.exe"}}); }
            catch (TargetInvocationException e) { denied = e.InnerException is PlatformNotSupportedException; }
            Assert(denied, "native probe must not emulate Windows success on another OS");
            Console.WriteLine("SKIP native Win32 execution: non-Windows host; only explicit refusal exercised");
        }
        else
        {
            var destination = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "trojaino-native-probe-" + Guid.NewGuid().ToString("N"));
            method.Invoke(null, new object[] {destination, new[] {"python.exe"}});
            Assert(!Directory.Exists(destination), "native preflight is read-only");
        }
    }
    static int Main(string[] args)
    {
        var tests = new Action[] { FreshPinnedInstall, OwnedRemoval, RemainingOwnedRemoval, FailedWriteRollsBackOnlyOwnedTree, PartialWriteRollsBack, RejectSpecialMetadataBeforeWriting, RejectUnsafeArchives, ExistingAndLinkedDestinationsPreserved, ChangedBytesAndRollbackIntruderPreserved, WindowsLiteralDestinations, WindowsNativeEligibility, NativeProbePlatformBoundary };
        int failed = 0;
        foreach (var test in tests)
            try { test(); Console.WriteLine("PASS " + test.Method.Name); }
            catch (Exception e) { failed++; Console.WriteLine("FAIL " + test.Method.Name + ": " + e); }
        if (args.Length == 1)
            try { ExerciseOfficialRuntime(args[0]); } catch (Exception e) { failed++; Console.WriteLine("FAIL OfficialRuntime: " + e); }
        else if (args.Length != 0) { failed++; Console.WriteLine("FAIL unexpected developer test arguments"); }
        Console.WriteLine("Tests: " + tests.Length + ", failed: " + failed);
        return failed == 0 ? 0 : 1;
    }
}
