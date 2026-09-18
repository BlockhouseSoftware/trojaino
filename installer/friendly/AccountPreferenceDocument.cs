// Pure bounded document edit. This confers no file-write or plugin identity authority.
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;

namespace Trojaino.Setup
{
    internal static class AccountPreferenceDocument
    {
        const int MaxBytes = 1024 * 1024;
        static readonly UTF8Encoding Utf8 = new UTF8Encoding(false, true);
        internal static byte[] Edit(byte[] input, string identity, bool enabled)
        {
            Require(input != null && input.Length <= MaxBytes, "Account settings byte budget exceeded or missing document");
            Require(identity != null && Regex.IsMatch(identity, @"\Atrojaino-local-[a-f0-9]{32}@skills-dir\z"), "Exact setup plugin identity required");
            string text;
            try { text = Utf8.GetString(input); }
            catch (DecoderFallbackException) { throw new InvalidDataException("Account settings must be strict UTF8"); }
            var parser = new Parser(text);
            Node root = parser.Document();
            Require(root.Kind == '{', "Account settings must be an object");
            Node plugins, selected;
            string value = enabled ? "true" : "false";
            int start, length; string replacement;
            if (!root.Members.TryGetValue("enabledPlugins", out plugins))
            {
                start = root.End - 1; length = 0;
                replacement = (root.Members.Count == 0 ? "" : ",") + "\"enabledPlugins\":{\"" + identity + "\":" + value + "}";
            }
            else
            {
                Require(plugins.Kind == '{', "enabledPlugins must be an object");
                foreach (Node entry in plugins.Members.Values)
                    Require(entry.Kind == 't' || entry.Kind == 'f', "enabledPlugins entries must be Boolean");
                if (plugins.Members.TryGetValue(identity, out selected))
                {
                    start = selected.Start; length = selected.End - selected.Start; replacement = value;
                }
                else
                {
                    start = plugins.End - 1; length = 0;
                    replacement = (plugins.Members.Count == 0 ? "" : ",") + "\"" + identity + "\":" + value;
                }
            }
            string result = text.Substring(0, start) + replacement + text.Substring(start + length);
            Require(Utf8.GetByteCount(result) <= MaxBytes, "Edited account settings exceed byte budget");
            new Parser(result).Document(); // Insertions must also fit the output depth/value budget.
            return Utf8.GetBytes(result);
        }
        static void Require(bool ok, string message) { if (!ok) throw new InvalidDataException(message); }
        sealed class Node
        {
            internal int Start, End;
            internal char Kind;
            internal Dictionary<string, Node> Members;
        }
        sealed class Parser
        {
            readonly string text;
            int position, nodes;
            internal Parser(string text) { this.text = text; }
            void Space() { while (position < text.Length && (text[position] == ' ' || text[position] == '\r' || text[position] == '\n' || text[position] == '\t')) position++; }
            bool Take(char c) { if (position < text.Length && text[position] == c) { position++; return true; } return false; }
            void Need(char c) { Require(Take(c), "Invalid account settings JSON syntax"); }
            internal Node Document()
            {
                Space(); Node root = Value(0); Space(); Require(position == text.Length, "Trailing account settings JSON content"); return root;
            }
            Node Value(int depth)
            {
                Require(depth <= 32 && ++nodes <= 16384, "Account settings depth or value budget exceeded");
                Space(); Require(position < text.Length, "Incomplete account settings JSON");
                var node = new Node { Start = position, Kind = text[position] };
                if (Take('{'))
                {
                    node.Members = new Dictionary<string, Node>(StringComparer.Ordinal); Space();
                    if (!Take('}'))
                    {
                        do
                        {
                            Space(); string key = String(); Space(); Need(':');
                            Require(!node.Members.ContainsKey(key), "Duplicate account settings key");
                            node.Members.Add(key, Value(depth + 1)); Space();
                        } while (Take(','));
                        Need('}');
                    }
                }
                else if (Take('['))
                {
                    Space();
                    if (!Take(']')) { do { Value(depth + 1); Space(); } while (Take(',')); Need(']'); }
                }
                else if (node.Kind == '"') String();
                else if (node.Kind == 't') Literal("true");
                else if (node.Kind == 'f') Literal("false");
                else if (node.Kind == 'n') Literal("null");
                else Number();
                node.End = position; return node;
            }
            void Literal(string token)
            {
                Require(position + token.Length <= text.Length && string.CompareOrdinal(text, position, token, 0, token.Length) == 0, "Invalid account settings literal");
                position += token.Length;
            }
            static bool Digit(char c) { return c >= '0' && c <= '9'; }
            void Digits()
            {
                int start = position; while (position < text.Length && Digit(text[position])) position++;
                Require(position > start, "Invalid account settings number");
            }
            void Number()
            {
                Take('-');
                if (!Take('0')) Digits();
                if (Take('.')) Digits();
                if (Take('e') || Take('E')) { if (!Take('+')) Take('-'); Digits(); }
            }
            char Hex()
            {
                Require(position + 4 <= text.Length, "Incomplete JSON Unicode escape");
                int value = 0;
                for (int i = 0; i < 4; i++)
                {
                    char c = text[position++];
                    int digit = c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1;
                    Require(digit >= 0, "Invalid JSON Unicode escape"); value = value * 16 + digit;
                }
                return (char)value;
            }
            string String()
            {
                Need('"'); var result = new StringBuilder(); bool ended = false;
                while (position < text.Length)
                {
                    char c = text[position++];
                    if (c == '"') { ended = true; break; }
                    Require(c >= 32, "Control character in JSON string");
                    if (c == '\\')
                    {
                        Require(position < text.Length, "Incomplete JSON escape"); c = text[position++];
                        switch (c)
                        {
                            case '"': case '\\': case '/': break;
                            case 'b': c = '\b'; break; case 'f': c = '\f'; break;
                            case 'n': c = '\n'; break; case 'r': c = '\r'; break; case 't': c = '\t'; break;
                            case 'u': c = Hex(); break;
                            default: throw new InvalidDataException("Invalid JSON escape");
                        }
                    }
                    result.Append(c);
                }
                Require(ended, "Unterminated JSON string");
                string value = result.ToString();
                for (int i = 0; i < value.Length; i++)
                {
                    if (char.IsHighSurrogate(value[i])) { Require(i + 1 < value.Length && char.IsLowSurrogate(value[i + 1]), "Unpaired JSON surrogate"); i++; }
                    else Require(!char.IsLowSurrogate(value[i]), "Unpaired JSON surrogate");
                }
                return value;
            }
        }
    }
}
