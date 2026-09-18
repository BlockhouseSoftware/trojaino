using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;

internal static class PreferenceTests
{
    const string Identity = "trojaino-local-0123456789abcdef0123456789abcdef@skills-dir";
    static readonly UTF8Encoding Utf8 = new UTF8Encoding(false, true);
    static MethodInfo edit;
    static void Assert(bool ok, string why) { if (!ok) throw new Exception("ASSERT: " + why); }
    static byte[] Edit(byte[] input, string identity, bool enabled)
    {
        try { return (byte[])edit.Invoke(null, new object[] { input, identity, enabled }); }
        catch (TargetInvocationException e) { throw e.InnerException; }
    }
    static string Edit(string input, bool enabled) { return Utf8.GetString(Edit(Utf8.GetBytes(input), Identity, enabled)); }
    static void Refuse(byte[] input, string identity)
    {
        byte[] original = input == null ? null : (byte[])input.Clone();
        bool refused = false;
        try { Edit(input, identity, true); } catch (InvalidDataException) { refused = true; }
        Assert(refused, "unsafe document or identity accepted");
        Assert(input == null || input.SequenceEqual(original), "refusal changed input bytes");
        Assert(Edit("{}", true) == "{\"enabledPlugins\":{\"" + Identity + "\":true}}", "valid document failed after refusal");
    }
    static int Main()
    {
        try
        {
            var type = typeof(PreferenceTests).Assembly.GetType("Trojaino.Setup.AccountPreferenceDocument");
            Assert(type != null, "lossless account preference document editor is missing");
            edit = type.GetMethod("Edit", BindingFlags.Static | BindingFlags.NonPublic);
            Assert(edit != null, "bounded document edit entry is missing");
            string empty = "{\"enabledPlugins\":{\"" + Identity + "\":true}}";
            Assert(Edit("{}", true) == empty, "empty settings edit");
            string unrelated = "{\r\n \"other\": [1e9999,-0,123456789012345678901234567890,\"é\\u0061\",{\"x\":true}], \"enabledPlugins\": {\"other@source\":false} \r\n}";
            string expected = unrelated.Replace("\"other@source\":false}", "\"other@source\":false,\"" + Identity + "\":true}");
            Assert(Edit(unrelated, true) == expected, "unrelated bytes changed on insertion");
            string original = "{ \"enabledPlugins\": { \"" + Identity + "\" : false },\"else\":1e99999 }\r\n";
            string enabled = original.Replace(" : false", " : true");
            Assert(Edit(original, true) == enabled && Edit(enabled, false) == original, "only selected boolean must change");
            Assert(Edit(enabled, true) == enabled, "already true must be byte-identical");
            string escaped = "{\"enabled\\u0050lugins\":{\"trojaino\\u002dlocal-0123456789abcdef0123456789abcdef@skills-dir\":false}}";
            Assert(Edit(escaped, true) == escaped.Replace(":false", ":true"), "escaped selected keys not recognized losslessly");
            Console.WriteLine("PASS lossless lexical account preference insertion/replacement; exact unrelated UTF8, escapes and numeric lexemes; reversible Boolean; no IO");
            string[] invalid = { "", "[]", "null", "{}{}", "{\"x\":1,}", "{\"x\":01}", "{\"x\":NaN}", "{\"x\":1.}", "{\"x\":1e+}", "{\"x\":+1}", "{\"x\":truex}", "{\"x\":\"\\x00\"}", "{\"x\":\"\n\"}", "{\"x\":\"\\uD800\"}", "{\"x\":\"\\uDC00\"}", "{\"x\":1,\"\\u0078\":2}", "{\"x\":[{\"a\":0,\"a\":1}]}", "{\"enabledPlugins\":null}", "{\"enabledPlugins\":[]}", "{\"enabledPlugins\":{\"other\":1}}", "{\"enabledPlugins\":{\"" + Identity + "\":\"false\"}}", "\uFEFF{}", "{ /*comment*/ }" };
            foreach (string text in invalid) Refuse(Utf8.GetBytes(text), Identity);
            Refuse(null, Identity); Refuse(new byte[] {123, 34, 0xff, 34, 58, 48, 125}, Identity);
            Refuse(Utf8.GetBytes("{}"), "other@skills-dir"); Refuse(Utf8.GetBytes("{}"), Identity.ToUpperInvariant()); Refuse(Utf8.GetBytes("{}"), Identity + "\n");
            Refuse(Utf8.GetBytes("{\"x\":\"" + new string('a', 1048576) + "\"}"), Identity);
            Refuse(Utf8.GetBytes("{\"x\":" + new string('[', 33) + "0" + new string(']', 33) + "}"), Identity);
            string already = "{\"enabledPlugins\":{\"" + Identity + "\":true},\"padding\":\"";
            string exact = already + new string('a', 1048576 - already.Length - 2) + "\"}";
            Assert(Edit(exact, true) == exact, "exact byte budget must allow no-op");
            Refuse(Utf8.GetBytes(exact), Identity.Substring(0, Identity.Length - 11) + "@skills-dir-invalid");
            string fullAbsent = "{\"padding\":\"" + new string('a', 1048576 - 14) + "\"}";
            Refuse(Utf8.GetBytes(fullAbsent), Identity); // input fits; insertion does not.
            string nodesAtLimit = "{\"x\":[" + string.Join(",", Enumerable.Repeat("0", 16382)) + "]}";
            Refuse(Utf8.GetBytes(nodesAtLimit), Identity); // insertion must respect output node budget too.
            string existingNodes = "{\"enabledPlugins\":{\"" + Identity + "\":false},\"x\":[" + string.Join(",", Enumerable.Repeat("0", 16380)) + "]}";
            Assert(Edit(existingNodes, true) == existingNodes.Replace(":false", ":true"), "exact output node budget refused");
            Refuse(Utf8.GetBytes("{\"x\":[" + string.Join(",", Enumerable.Repeat("0", 16383)) + "]}"), Identity);
            string depthAtLimit = "{\"x\":" + new string('[', 31) + "0" + new string(']', 31) + "}";
            Assert(Edit(depthAtLimit, true).Contains(new string('[', 31)), "exact input depth refused");
            Refuse(Utf8.GetBytes("{\"x\":" + new string('[', 32) + "0" + new string(']', 32) + "}"), Identity);
            Assert(Edit("{\"x\":\"\\uD83D\\uDE00\"}", true).Contains("\\uD83D\\uDE00"), "valid surrogate pair changed");
            Console.WriteLine("PASS duplicate decoded keys at every object, strict UTF8/JSON/types, malformed numeric/string/surrogate syntax, identity/byte/depth limits; refusal leaves input unchanged");
            return 0;
        }
        catch (Exception e) { Console.Error.WriteLine(e); return 1; }
    }
}
