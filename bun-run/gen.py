"""Deterministic session generators for the Bun parity run.

python3 -I gen.py <class> <N> <out.jsonl>
Each line: {"id", "cls", "argv": [...] with "{BUN}" placeholder, "files": {name: content}, "fp": sha256}.
"""
import hashlib
import os
import json
import random
import sys

SEEDS = {"runtime": 101, "bundler": 202, "transpiler": 303, "testrunner": 404, "utils": 505}

# ---------------------------------------------------------------- shared literal generators
ASCII = "abcxyzABC019 _-.,:;!?/"
CYR = "приветЁё"
CJK = "漢字日本語"
EMOJI = ["😀", "👍🏽", "🇺🇦", "👨‍👩‍👧", "𐀀", "𝔘"]
COMB = ["e\u0301", "a\u0308", "\u0915\u094d\u0937"]
CTRL = ["\\n", "\\t", "\\0", "\\x1b", "\\r", "\\u2028", "\\u00a0", "\\u200b", "\\ufeff"]
SURR = ["\\uD800", "\\uDBFF", "\\uDC00", "\\uDFFF", "\\uD83D"]
QUOTE = ["\\\"", "'", "\\\\", "`", "${", "<", ">", "&"]


def js_str(r, maxlen=8):
    parts = []
    for _ in range(r.randint(0, maxlen)):
        k = r.random()
        if k < 0.35:
            parts.append(r.choice(ASCII))
        elif k < 0.45:
            parts.append(r.choice(CYR))
        elif k < 0.52:
            parts.append(r.choice(CJK))
        elif k < 0.62:
            parts.append(r.choice(EMOJI))
        elif k < 0.68:
            parts.append(r.choice(COMB))
        elif k < 0.78:
            parts.append(r.choice(CTRL))
        elif k < 0.88:
            parts.append(r.choice(SURR))
        else:
            parts.append(r.choice(QUOTE))
    return '"' + "".join(parts) + '"'


def js_num(r):
    return r.choice([
        str(r.randint(-1000, 1000)), str(r.randint(0, 2**53)), "2**31", "2**31-1", "-(2**31)", "2**32",
        "2**53", "2**53+1", "-0", "NaN", "Infinity", "-Infinity", "0.1+0.2", "1e21", "1e-7", "5e-324",
        "1.7976931348623157e308", repr(round(r.uniform(-1e6, 1e6), r.randint(0, 12))), "1751241600000",
        "0x7fffffff", "0b1011", "1_000_000", ".5", "123.456e10", repr(r.random()),
    ])


def js_val(r, d=0):
    k = r.randint(0, 22 if d < 2 else 8)
    if k <= 2:
        return js_str(r)
    if k <= 4:
        return js_num(r)
    if k == 5:
        return r.choice(["true", "false", "null", "undefined", f"{r.randint(-10**20, 10**20)}n", "0n"])
    if k == 6:
        return r.choice(['Symbol("s")', "Symbol()", "Symbol.iterator", 'Symbol.for("k")'])
    if k == 7:
        return r.choice(["/a+b/gi", "/[\\u{1F600}]/u", "new RegExp(\"x\", \"y\")", "/(?<n>\\d)/"])
    if k == 8:
        return f"new Date({r.choice([0, 1751241600000, -1, 8.64e15, r.randint(0, 2**41)])})"
    if k <= 11:
        return "[" + ", ".join(js_val(r, d + 1) for _ in range(r.randint(0, 5))) + "]"
    if k <= 14:
        keys = [r.choice(["a", "b", "x_y", '"key with space"', "1", "0", '"ключ"', '"😀"', "__proto__x",
                          "[Symbol(\"sk\")]", '"-1"', "constructor", "length"]) for _ in range(r.randint(0, 5))]
        return "{" + ", ".join(f"{kk}: {js_val(r, d + 1)}" for kk in keys) + "}"
    if k == 15:
        return "new Map([" + ", ".join(f"[{js_val(r, d + 1)}, {js_val(r, d + 1)}]" for _ in range(r.randint(0, 3))) + "])"
    if k == 16:
        return "new Set([" + ", ".join(js_val(r, d + 1) for _ in range(r.randint(0, 4))) + "])"
    if k == 17:
        t = r.choice(["Uint8Array", "Int16Array", "Float64Array", "Float32Array", "BigInt64Array", "Uint8ClampedArray"])
        if t == "BigInt64Array":
            return f"new BigInt64Array([{r.randint(-99, 99)}n, {r.randint(0, 2**62)}n])"
        return f"new {t}([" + ", ".join(str(r.choice([r.randint(-300, 300), round(r.uniform(-5, 5), 3)])) for _ in range(r.randint(0, 6))) + "])"
    if k == 18:
        return r.choice(["new Error(\"boom\")", "new TypeError(" + js_str(r) + ")", "new RangeError(\"r\", {cause: 1})",
                         "Object.assign(new Error(\"e\"), {code: \"E1\"})", "new AggregateError([new Error(\"a\")], \"agg\")"])
    if k == 19:
        return r.choice(["class Foo { constructor(){ this.a = 1 } }", "new (class Bar { x = 2; #p = 3 })()",
                         "function named(a, b) {}", "(a) => a", "async function* g() {}", "Math", "globalThis.JSON"])
    if k == 20:
        return r.choice(["Object.create(null)", "new ArrayBuffer(4)", "new WeakMap()", "Promise.resolve(1)",
                         "new Proxy({a: 1}, {})", "[1, , 3]", "Array(3)", "Object.freeze([1])"])
    if k == 21:
        return f"Buffer.from({bytes_lit(r)})"
    return f"new DataView(new ArrayBuffer({r.randint(0, 8)}))"


def bytes_lit(r, n=None):
    n = r.randint(0, 9) if n is None else n
    pool = [0x00, 0x41, 0x7f, 0x80, 0xc3, 0xa9, 0xe2, 0x82, 0xac, 0xf0, 0x9f, 0x98, 0x80, 0xff, 0xfe, 0xef, 0xbb, 0xbf, 0xed, 0xa0]
    b = [r.choice(pool) if r.random() < 0.8 else r.randint(0, 255) for _ in range(n)]
    if r.random() < 0.15:
        b = [0xff, 0xfe] + b
    elif r.random() < 0.1:
        b = [0xef, 0xbb, 0xbf] + b
    return "[" + ", ".join(map(str, b)) + "]"


# ---------------------------------------------------------------- class 1: runtime
def stmt_runtime(r):
    v = lambda: js_val(r)  # noqa: E731
    s = lambda: js_str(r, 10)  # noqa: E731
    enc = lambda: r.choice(["utf8", "hex", "base64", "base64url", "latin1", "ascii", "utf16le", "binary", "ucs2"])  # noqa: E731
    k = r.randint(0, 30)
    if k <= 4:
        return "console.log(" + ", ".join(v() for _ in range(r.randint(1, 3))) + ");"
    if k == 5:
        return f"console.log(JSON.stringify({v()}, null, {r.choice([0, 2, '\"\\t\"', 4])}));"
    if k == 6:
        return f"console.log(JSON.parse(JSON.stringify({v()}) ?? \"null\"));"
    if k == 7:
        return f"console.log(JSON.parse({js_str(r) if r.random() < 0.5 else repr(r.choice(['1', '[1,2]', '{\"a\":1}', '\"\\\\ud800\"', '1e400', '-0', '{\"__proto__\":1}', '[', '01']))}));"
    if k == 8:
        return f"console.log(Bun.inspect({v()}, {{depth: {r.randint(0, 3)}}}));"
    if k <= 11:
        op = r.choice(["length", "toUpperCase()", "toLowerCase()", "normalize(\"NFC\")", "normalize(\"NFD\")", "normalize(\"NFKC\")",
                       "split(\"\")", "isWellFormed()", "toWellFormed()", "at(-1)", "codePointAt(0)", "charCodeAt(1)",
                       "padStart(12, \"*\")", "repeat(2)", "trim()", "localeCompare(\"b\")", "replaceAll(\"a\", \"$&$&\")",
                       "slice(1, -1)", "split(/(?:)/u)", "search(/\\p{L}/u)", "match(/./gu)"])
        return f"console.log(({s()}).{op});"
    if k == 12:
        return f"console.log([...{s()}], Array.from({s()}).length);"
    if k == 13:
        return f"console.log(Buffer.from({bytes_lit(r)}).toString(\"{enc()}\"));"
    if k == 14:
        return f"console.log(Buffer.from({s()}, \"{enc()}\").toString(\"{enc()}\"), Buffer.byteLength({s()}, \"{enc()}\"));"
    if k == 15:
        e = r.choice(["utf-8", "utf-16le", "utf-16be", "latin1", "windows-1252", "iso-8859-2", "ascii"])
        return (f"console.log(new TextDecoder(\"{e}\", {{fatal: {r.choice(['true', 'false'])}, ignoreBOM: {r.choice(['true', 'false'])}}})"
                f".decode(new Uint8Array({bytes_lit(r)})));")
    if k == 16:
        return f"console.log(new TextEncoder().encode({s()}), new TextEncoder().encodeInto({s()}, new Uint8Array({r.randint(0, 6)})));"
    if k == 17:
        u = r.choice(["https://", "http://", "file://", "ws://", "mailto:", "data:", "blob:", "", "//", "ftp://"]) + \
            r.choice(["example.com", "ПРИМЕР.рф", "xn--e1afmkfd.xn--p1ai", "user:pa ss@h", "[::1]", "127.0.0.1:99999", "a..b", "%41.com", "😀.ws"]) + \
            r.choice(["", "/", "/a/../b/./c", "/%2e%2E/x", "/пусть", "/a b", "\\\\x"]) + r.choice(["", "?q=1&q=2", "?a=%zz", "?ü=ö"]) + r.choice(["", "#frag", "#😀"])
        prop = r.choice(["href", "host", "hostname", "pathname", "search", "hash", "origin", "port", "toString()"])
        return f"console.log(new URL({json.dumps(u)}).{prop});"
    if k == 18:
        return f"console.log([...new URLSearchParams({s()})], new URLSearchParams({{a: {s()}, b: \"1 2\"}}).toString());"
    if k == 19:
        alg = r.choice(["md5", "sha1", "sha256", "sha512", "sha384", "sha224", "sha512-256", "ripemd160", "blake2b512", "sha3-256"])
        return f"console.log(require(\"node:crypto\").createHash(\"{alg}\").update({s()}).digest(\"{r.choice(['hex', 'base64', 'latin1', 'base64url'])}\"));"
    if k == 20:
        f = r.choice(["Bun.hash", "Bun.hash.wyhash", "Bun.hash.crc32", "Bun.hash.adler32", "Bun.hash.cityHash32", "Bun.hash.cityHash64",
                      "Bun.hash.xxHash32", "Bun.hash.xxHash64", "Bun.hash.xxHash3", "Bun.hash.murmur32v3", "Bun.hash.murmur64v2", "Bun.hash.rapidhash"])
        return f"console.log({f}({s()}), {f}(new Uint8Array({bytes_lit(r)})));"
    if k == 21:
        alg = r.choice(["sha256", "sha1", "md5", "blake2b256", "sha512"])
        return f"console.log(new Bun.CryptoHasher(\"{alg}\").update({s()}).digest(\"hex\"));"
    if k == 22:
        return f"console.log(btoa({s()}));" if r.random() < 0.5 else f"console.log(atob({json.dumps(r.choice(['QUJD', 'QUJD=', 'QU JD', '====', 'YQ', '8J+YgA==', '@@']))}));"
    if k == 23:
        return f"console.log(structuredClone({v()}));"
    if k == 24:
        return f"console.log(Bun.escapeHTML({s()}), Bun.stringWidth({s()}));"
    if k == 25:
        n = js_num(r)
        op = r.choice([f"toFixed({r.randint(0, 20)})", f"toPrecision({r.randint(1, 21)})", f"toString({r.randint(2, 36)})",
                       f"toExponential({r.randint(0, 20)})", "toString()", "toLocaleString()"])
        return f"console.log(({n}).{op});"
    if k == 26:
        return f"console.log(parseFloat({s()}), Number({json.dumps(r.choice(['0x10', ' 12 ', '1e', '١٢', '-0', '0b11', 'Infinity', '1_0', '.e1']))}), parseInt({json.dumps(r.choice(['08', '0x1f', '  -3z', '9'*25]))}));"
    if k == 27:
        return f"console.log(await new Blob([new Uint8Array({bytes_lit(r)})]).text());"
    if k == 28:
        return f"{{ const m = new Map(); const st = new Set(); for (const x of [{js_num(r)}, {js_num(r)}, {js_num(r)}]) {{ m.set(x, String(x)); st.add(x); }} console.log([...m.keys()], [...st], m.size); }}"
    if k == 29:
        return f"console.log(encodeURIComponent({s()}), encodeURI({s()}), escape({s()}));"
    return f"console.error({v()}); console.warn({s()});"


def gen_runtime(r):
    body = []
    for _ in range(r.randint(1, 6)):
        st = stmt_runtime(r)
        body.append(st if r.random() < 0.15 else f"try {{ {st} }} catch (e) {{ console.log(\"ERR\", e?.name, e?.code, e?.message); }}")
    if r.random() < 0.05:
        body.append(f"throw {js_val(r)};")
    return ["{BUN}", "run", "s.ts"], {"s.ts": "\n".join(body) + "\n"}


# ---------------------------------------------------------------- class 2: bundler
def ident(r, pre="v"):
    return pre + str(r.randint(0, 99))


def gen_module(r, i, n, next_has_default=False):
    lines = []
    exports = []
    if i + 1 < n and r.random() < 0.8:
        imp = r.choice(["named", "ns", "default", "star"] if next_has_default else ["named", "ns", "star"])
        if imp == "named":
            lines.append(f"import {{ c{i + 1} as cc }} from \"./m{i + 1}\";")
            lines.append("export const fromNext = cc;")
        elif imp == "ns":
            lines.append(f"import * as ns from \"./m{i + 1}\";")
            lines.append("export const fromNext = ns.c" + str(i + 1) + ";")
        elif imp == "default":
            lines.append(f"import d from \"./m{i + 1}\";")
            lines.append("export const fromNext = d;")
        else:
            lines.append(f"export * from \"./m{i + 1}\";")
    if r.random() < 0.3:
        lines.append("import data from \"./d.json\";")
        lines.append("export const fromJson = data.k;")
    lines.append(f"export const c{i} = {r.choice([js_num(r), js_str(r, 5), '`t${1+2}`', '\"a\" + \"b\"', '1 + 2 * 3', '[1,2,3].length', '{a: 1}.a', 'typeof window'])};")
    for _ in range(r.randint(0, 3)):
        kind = r.randint(0, 7)
        nm = ident(r, "f")
        if kind == 0:
            lines.append(f"export function {nm}(a{i}, b = {js_num(r)}) {{ return a{i} * {r.randint(1, 9)} + b; }}")
        elif kind == 1:
            lines.append(f"export class K{nm} {{ static s = {js_num(r)}; #p = 1; get p() {{ return this.#p; }} m() {{ return {js_str(r, 4)}; }} }}")
        elif kind == 2:
            lines.append(f"if ({r.choice(['false', 'process.env.NODE_ENV === \"production\"', '0', 'import.meta.main'])}) {{ console.log(\"dead {nm}\"); }}")
        elif kind == 3:
            lines.append(f"const {nm} = {r.choice(['() => 1', 'async () => await 1', 'function* () { yield 1 }'])}; export {{ {nm} }};")
        elif kind == 4:
            lines.append(f"export enum E{nm} {{ A = {r.randint(0, 5)}, B, C = \"c\" }}")
        elif kind == 5:
            lines.append(f"export const {nm} = /* @__PURE__ */ (() => ({js_val(r)}))();")
        elif kind == 6:
            lines.append(f"export let {nm} = {r.randint(0, 9)}; {nm}++;")
        else:
            lines.append(f"const unused_{nm} = {js_val(r)};")
    has_default = r.random() < 0.6
    if has_default:
        lines.append(f"export default {r.choice([js_num(r), js_str(r, 4), 'function () { return 1 }', 'class {}', '{ k: 1 }'])};")
    exports.append(f"c{i}")
    return "\n".join(lines) + "\n", has_default


def gen_bundler(r):
    n = r.randint(1, 4)
    files, nd = {}, False
    for i in reversed(range(n)):
        files[f"m{i}.ts"], nd = gen_module(r, i, n, nd)
    files["d.json"] = json.dumps({"k": r.randint(0, 99), "s": "x"})
    if nd:
        entry = "import * as m0 from \"./m0\";\nimport def0 from \"./m0\";\nconsole.log(m0.c0, def0, Object.keys(m0).sort());\n"
    else:
        entry = "import * as m0 from \"./m0\";\nconsole.log(m0.c0, Object.keys(m0).sort());\n"
    if r.random() < 0.3:
        entry += "const lazy = await import(\"./m0\");\nconsole.log(lazy.c0);\n"
    files["entry.ts"] = entry
    argv = ["{BUN}", "build", "entry.ts"]
    if r.random() < 0.5:
        argv.append("--minify")
    elif r.random() < 0.3:
        argv.append(r.choice(["--minify-syntax", "--minify-whitespace", "--minify-identifiers"]))
    if r.random() < 0.6:
        argv.append("--format=" + r.choice(["esm", "cjs", "iife"]))
    if r.random() < 0.6:
        argv.append("--target=" + r.choice(["bun", "node", "browser"]))
    if r.random() < 0.15:
        argv.append("--sourcemap=inline")
    if r.random() < 0.15:
        argv += ["--define", r.choice(["X=1", "process.env.NODE_ENV=\"production\"", "W=\"./src/w.ts\""])]
    if r.random() < 0.1:
        argv.append("--splitting")
    return argv, files


# ---------------------------------------------------------------- class 3: transpiler
def ts_snippet(r, jsx):
    k = r.randint(0, 24 if jsx else 19)
    nm = ident(r, "x")
    if k == 0:
        return f"interface I{nm}<T> {{ a: T; b?: string; readonly c: number[] }}\nexport type T{nm} = I{nm}<number> | null;"
    if k == 1:
        return f"export function {nm}<T extends object = {{}}>(p: T, ...rest: number[]): T {{ return p as unknown as T; }}"
    if k == 2:
        return f"{r.choice(['', 'const ', 'export ', 'declare '])}enum E{nm} {{ A = {r.randint(0, 9)}, B, C = \"c\", D = A | 2 }}\nconsole.log(typeof E{nm});"
    if k == 3:
        return f"namespace N{nm} {{ export const v = {js_num(r)}; export namespace Inner {{ export let w = v; }} }}"
    if k == 4:
        return f"abstract class A{nm} {{ constructor(private readonly p: number, public q?: string) {{}} abstract m(): void; protected static s = 1; declare d: number; }}"
    if k == 5:
        return f"const {nm} = (globalThis as any)?.foo?.bar ?? {js_num(r)}!; let y{nm} = {nm} satisfies number;"
    if k == 6:
        return f"const {nm} = `a${{{js_num(r)}}}b${{`nested ${{1}}`}}\\u{{1F600}}`;"
    if k == 7:
        return f"const {nm} = [{', '.join(r.choice(['0x1F', '0o17', '0b101', '1_000', '1e3', '.5', '5.', '0.0000001', '123n', '0xFFn', '1e+21', '00', '09.5']) for _ in range(4))}];"
    if k == 8:
        return f"const {nm} = /{r.choice(['a+', '[/]', '\\\\d{2,}', '(?<g>x)\\\\k<g>', '\\\\p{L}+'])}/{r.choice(['', 'g', 'u', 'gimsuy', 'v'])};"
    if k == 9:
        return f"lbl{nm}: for (const [a, {{b = 1, ...c}}] of []) {{ continue lbl{nm}; }}"
    if k == 10:
        return f"export default {r.choice(['function () {}', 'class {}', 'async function () {}', 'function* () {}', '(x: number) => x', js_num(r)])};"
    if k == 11:
        return f"const o{nm} = {{ get g() {{ return 1 }}, set s(v) {{}}, async *[Symbol.iterator]() {{}}, 'quoted-key': 1, 2: 3, {nm}: 0 }};"
    if k == 12:
        return f"async function {nm}() {{ for await (const x of []) {{}} try {{ await 0 }} catch {{ }} finally {{ }} }}"
    if k == 13:
        return f"let {nm}: Array<[string, number?]> = []; let z{nm} = <any>{nm}; let w{nm} = {nm}!.length;"
    if k == 14:
        return f"import type {{ Foo }} from \"./types\";\nimport {{ type Bar, baz }} from \"./mod{r.randint(0, 3)}\";\nexport {{ baz as {nm} }};"
    if k == 15:
        return f"export * as ns{nm} from \"./ns\";\nexport {{ default as d{nm} }} from \"./d\";"
    if k == 16:
        return f"const {nm} = {js_str(r, 8)};"
    if k == 17:
        return f"class C{nm}<T> implements Iterable<T> {{ #priv = 1; static {{ console.log(1) }} accessor? ; [Symbol.iterator](): Iterator<T> {{ return [][Symbol.iterator]() }} }}".replace("accessor? ;", "")
    if k == 18:
        return f"function f{nm}(this: Window, a?: number, b: string = \"d\"): asserts a is number {{}}"
    if k == 19:
        return f"if ({r.choice(['false', 'true', '1 === 1', 'process.env.X'])}) {{ console.log({js_num(r)}) }} else {{ debugger; }}"
    # JSX
    tag = r.choice(["div", "span", "Foo", "Foo.Bar", "a-b", "svg:rect", "my-element"])
    attrs = " ".join(r.choice([f"id=\"{r.randint(0, 9)}\"", "{...props}", "disabled", f"data-x={{{js_num(r)}}}", "className={cls}",
                               "key=\"k\"", "style={{ color: 'red' }}", "aria-label=\"&amp; &quot;\"", "onClick={() => {}}"]) for _ in range(r.randint(0, 3)))
    text = r.choice(["hello", "&nbsp;&amp;&#123;&#x1F600;", "  spaced\n   text  ", "{\"{\"}", "Привет 😀", "{1 + 2}", "{cond && <b />}", "{list.map(i => <i key={i}>{i}</i>)}", ""])
    if k == 20:
        return f"export const {nm} = <{tag} {attrs}>{text}</{tag}>;"
    if k == 21:
        return f"export const {nm} = <>{text}<{tag} {attrs} /></>;"
    if k == 22:
        return f"export function {nm.capitalize()}({{ a, ...rest }}: {{ a: number }}) {{ return <section {{...rest}}>{{a}}{text}</section>; }}"
    if k == 23:
        return f"const {nm} = <{tag} {attrs}>{{/* comment */}}{text}</{tag}>;"
    return f"const {nm} = cond ? <{tag} /> : <span>{text}</span>;"


def gen_transpiler(r):
    ext = r.choice(["ts", "tsx", "jsx", "ts", "tsx"])
    jsx = ext != "ts"
    src = "\n".join(ts_snippet(r, jsx) for _ in range(r.randint(1, 5)))
    if ext == "jsx":
        # strip obvious TS-only syntax: just use JSX-only snippets
        src = "\n".join(ts_snippet(r, True) if r.random() < 0.0 else s for s in [ts_snippet_jsx_only(r) for _ in range(r.randint(1, 4))])
    name = r.choice(["f", "f", "f", "1", "0abc", "my-file", "файл", "index"]) + "." + ext
    files = {name: src + "\n"}
    mode = r.random()
    if mode < 0.6:
        argv = ["{BUN}", "build", "--no-bundle", name]
        if r.random() < 0.3:
            argv.append(r.choice(["--minify", "--minify-syntax", "--minify-whitespace", "--minify-identifiers"]))
        if r.random() < 0.2:
            argv.append("--target=" + r.choice(["bun", "node", "browser"]))
    else:
        loader = ext
        opts = r.choice(["{}", "{ trimUnusedImports: true }", "{ minifyWhitespace: true }", "{ deadCodeElimination: false }",
                         "{ define: { \"process.env.X\": \"1\" } }", "{ target: \"browser\" }"])
        files["t.js"] = (f"const src = await Bun.file({json.dumps(name)}).text();\n"
                         f"const tr = new Bun.Transpiler({{ loader: \"{loader}\", ...{opts} }});\n"
                         "try { console.log(tr.transformSync(src)); } catch (e) { console.log(\"ERR\", String(e)); }\n"
                         "try { console.log(JSON.stringify(tr.scan(src))); } catch (e) { console.log(\"ERR\", String(e)); }\n")
        argv = ["{BUN}", "run", "t.js"]
    return argv, files


def ts_snippet_jsx_only(r):
    k = r.choice([6, 7, 8, 9, 10, 11, 12, 15, 16, 19, 20, 21, 23, 24])
    s = ts_snippet(r, True) if k >= 20 else None
    if s is None:
        rr = random.Random(r.random())
        while True:
            s = ts_snippet(rr, False)
            if not any(t in s for t in (": ", "interface", "enum", "namespace", " as ", "<T", "satisfies", "abstract", "type ", "!")):
                break
    return s


# ---------------------------------------------------------------- class 4: test runner
def gen_test(r):
    out = ["import { test, expect, describe } from \"bun:test\";"]
    for t in range(r.randint(1, 6)):
        kind = r.randint(0, 14)
        a, b = js_val(r), js_val(r)
        name = json.dumps(r.choice(["adds", "тест", "😀 emoji", "has \"quotes\"", "a > b", f"t{t}", "", "%s %d", "with\nnewline"]))
        body = {
            0: f"expect({a}).toBe({a});",
            1: f"expect({a}).toBe({b});",
            2: f"expect({a}).toEqual({b});",
            3: f"expect({a}).toStrictEqual({a});",
            4: f"expect(() => {{ throw new Error({js_str(r, 4)}) }}).toThrow({js_str(r, 2)});",
            5: f"expect([{a}, 1]).toContain({b});",
            6: f"expect({{a: {a}, b: 2}}).toMatchObject({{a: {b}}});",
            7: f"expect({js_num(r)}).toBeCloseTo({js_num(r)}, {r.randint(0, 5)});",
            8: f"expect({a}).not.toBeNull(); expect({a}).toBeDefined();",
            9: f"expect(String({a})).toMatch(/{r.choice(['a', '^$', '\\\\d', '.'])}/);",
            10: f"expect({a}).toHaveLength({r.randint(0, 5)});",
            11: f"expect({a}).toBeTruthy();",
            12: f"await expect(Promise.reject(new Error(\"x\"))).rejects.toThrow(\"x\");",
            13: f"expect({js_num(r)}).toBeGreaterThan({js_num(r)});",
            14: f"expect({a}).toBeInstanceOf(Object);",
        }[kind]
        mod = r.choice(["test", "test", "test", "test.skip", "test.todo", "test.failing", "test.if(true)"])
        if mod == "test.todo" and r.random() < 0.5:
            out.append(f"test.todo({name});")
            continue
        if r.random() < 0.15:
            out.append(f"test.each([[1, 2], [3, 4]])({json.dumps('each %p %p')}, async (x, y) => {{ {body} }});")
        else:
            out.append(f"{mod}({name}, async () => {{ {body} }});")
    src = "\n".join(out)
    if r.random() < 0.3:
        src = f"describe({json.dumps(r.choice(['suite', 'набор', 'nested']))}, () => {{\n{src.split(chr(10), 1)[1] if chr(10) in src else ''}\n}});"
        src = "import { test, expect, describe } from \"bun:test\";\n" + src
    argv = ["{BUN}", "test"]
    if r.random() < 0.2:
        argv.append(r.choice(["--bail", "--only", "--todo", "--rerun-each=2"]))
    return argv, {"x.test.ts": src + "\n"}


# ---------------------------------------------------------------- class 5: utils
def ver(r):
    v = ".".join(str(r.choice([0, 1, 2, 10, 99, r.randint(0, 20)])) for _ in range(r.choice([1, 2, 3, 3, 3, 4])))
    if r.random() < 0.3:
        v += "-" + r.choice(["alpha", "beta.1", "rc.10", "0", "alpha.beta", "x-y", "1.2"])
    if r.random() < 0.1:
        v += "+build." + str(r.randint(0, 9))
    if r.random() < 0.1:
        v = r.choice(["v", "=", " ", "V"]) + v
    return v


def rng_(r):
    k = r.randint(0, 9)
    if k == 0:
        return "^" + ver(r)
    if k == 1:
        return "~" + ver(r)
    if k == 2:
        return f">={ver(r)} <{ver(r)}"
    if k == 3:
        return f"{ver(r)} - {ver(r)}"
    if k == 4:
        return r.choice(["*", "x", "1.x", "1.2.x", "", "latest", ">1", "<=0.0.0", "1 || 2", "^0.0.1", "~1", "=1.2.3"])
    if k == 5:
        return f"{rng_(r)} || {rng_(r)}"
    if k == 6:
        return r.choice([">", "<", ">=", "<=", "="]) + ver(r)
    return ver(r)


GLOB_SEG = ["*", "**", "?", "a", "b*", "[abc]", "[!a]", "{x,y}", "{a,b,}", "\\*", ".hidden", "*.ts", "file.[jt]s", "**/", "!", "ü", "[a-c]"]
PATH_SEG = ["a", "b", "x", "y", "c", ".hidden", "file.ts", "file.js", "ü", "*", "a b", "z.test.ts", "", ".."]


def gen_utils(r):
    if r.random() < 0.25:
        scripts = {}
        for _ in range(r.randint(1, 4)):
            nm = r.choice(["build", "test", "dev", "pre" + "build", "post" + "build", "a:b", "x", "с"])
            scripts[nm] = r.choice(["", "echo hi", "echo $npm_lifecycle_event", "echo \"a  b\"", "exit 3", "echo 1 && echo 2",
                                    "echo ok; false", "true", "echo пр", "printf '%s\\n' x", "echo $npm_package_name"])
        pkg = {"name": r.choice(["p", "@s/p", "UPPER", ""]), "version": ver(r), "scripts": scripts}
        target = r.choice(list(scripts) + ["missing"])
        argv = ["{BUN}", "run", target] + (["--silent"] if r.random() < 0.2 else [])
        return argv, {"package.json": json.dumps(pkg, ensure_ascii=False, indent=2)}
    body = []
    for _ in range(r.randint(1, 8)):
        k = r.randint(0, 5)
        if k <= 1:
            body.append(f"console.log(Bun.semver.satisfies({json.dumps(ver(r))}, {json.dumps(rng_(r))}));")
        elif k == 2:
            body.append(f"console.log(Bun.semver.order({json.dumps(ver(r))}, {json.dumps(ver(r))}));")
        elif k <= 4:
            pat = "/".join(r.choice(GLOB_SEG) for _ in range(r.randint(1, 4)))
            pth = "/".join(r.choice(PATH_SEG) for _ in range(r.randint(1, 4)))
            body.append(f"console.log(new Bun.Glob({json.dumps(pat)}).match({json.dumps(pth)}));")
        else:
            toml = []
            for _ in range(r.randint(1, 4)):
                kk = r.choice(["a", "b.c", "\"q k\"", "d-e", "1"])
                vv = r.choice([str(r.randint(-9, 9)), "3.14", "-0.0", "inf", "nan", "true", "\"s\\u00e9\"", "'lit'", "[1, 2]",
                               "{x = 1}", "1979-05-27T07:32:00Z", "0x1F", "1_000", "\"\"\"ml\"\"\"", "[[1], [\"a\"]]", "\"\\uD800\""])
                toml.append(f"{kk} = {vv}")
            if r.random() < 0.3:
                toml.insert(0, r.choice(["[t]", "[[arr]]", "[a.\"b\"]"]))
            body.append(f"console.log(JSON.stringify(Bun.TOML.parse({json.dumps(chr(10).join(toml))})));")
    body = [f"try {{ {b} }} catch (e) {{ console.log(\"ERR\", e?.name, e?.message); }}" for b in body]
    return ["{BUN}", "run", "u.ts"], {"u.ts": "\n".join(body) + "\n"}


GENS = {"runtime": gen_runtime, "bundler": gen_bundler, "transpiler": gen_transpiler, "testrunner": gen_test, "utils": gen_utils}


def generate(cls, n):
    r = random.Random(SEEDS[cls] + int(os.environ.get("PILOT_SEED_OFFSET", "0")))
    seen, out, draws = set(), [], 0
    while len(out) < n:
        draws += 1
        argv, files = GENS[cls](r)
        fp = hashlib.sha256(json.dumps([argv, sorted(files.items())], ensure_ascii=False).encode("utf-8", "surrogatepass")).hexdigest()
        if fp in seen:
            continue
        seen.add(fp)
        out.append({"id": f"{cls}-{len(out):05d}", "cls": cls, "argv": argv, "files": files, "fp": fp})
    return out, draws


if __name__ == "__main__":
    cls, n, path = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    sessions, draws = generate(cls, n)
    with open(path, "w", encoding="utf-8") as f:
        for s in sessions:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(cls, len(sessions), "unique of", draws, "draws")
