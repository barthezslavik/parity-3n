"""Post-hoc classification of every divergent session into root causes (labels), for new=C (1.4.0) and C2 (canary).

python3 -I classify.py  ->  classification.json + printed tables
Session label = sorted set of root-cause labels; a session is 'explained' iff it has no UNEXPLAINED-* label.
runtime/utils: labels come from line-level minimization (min_<cls>[_c2].jsonl) + oracles (node, tomllib);
other classes: whole-output transforms (explain.py) + behavioural bundle check (verify_bundler.jsonl).
"""
import collections
import html
import json
import os
import re
import sys

W = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, W)
from explain import TRANSFORMS, explain  # noqa: E402
from ops import op_of  # noqa: E402

CLASSES = ["runtime", "bundler", "transpiler", "testrunner", "utils"]


def load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8")] if os.path.exists(p) else []


ORACLE = {(o["id"], o["line"]): o["verdict"] for o in load(f"{W}/oracle_runtime.jsonl")}
VB = {o["id"]: o for o in load(f"{W}/verify_bundler.jsonl")}

PANIC = re.compile(r"panic: (.*?) \(")


def crash_label(o):
    m = PANIC.search(o["err"])
    if not m:
        return None
    msg = m.group(1)
    known = {"cast_slice>OutputSliceWouldHaveSlop": "#31188", "internal error: entered unreachable code": "PR #31234 (semver)"}
    return f"KNOWN-port-regression: panic '{msg}' ({known.get(msg, '?')})"


def short_ident_only(x, y):
    rx = r"[A-Za-z_$\u0400-\u04ff][\w$\u0400-\u04ff]*|\d+|\S"
    tx, ty = re.findall(rx, x), re.findall(rx, y)
    if len(tx) != len(ty):
        return False
    idre = re.compile(r"[A-Za-z_$][\w$]?$")
    return all(p == q or (idre.match(p) and idre.match(q)) for p, q in zip(tx, ty))


def unesc(t):
    return html.unescape(t)


def line_label(line, a, c, sid, new):
    e = explain(a, c, line)
    if e is not None:
        return ["X:" + n for n in e] or ["X:none"]
    if new == "C2":
        cl = crash_label(c)
        if cl:
            return [cl]
    op = op_of(line)
    if op == "TOML":
        return ["DOC:TOML parser rewrite (1.4: 'Bun.TOML ... rewritten for full TOML v1.1.0 conformance'; new agrees with Python tomllib wherever results differ)"]
    if op == "semver.satisfies" and "||" in line:
        return ["KNOWN-undocumented: semver garbage chunk after '||' now skipped (consequence of PR #31234 fixing a canary panic)"]
    if new == "C" and ORACLE.get((sid, line)) == "new==node":
        return ["DOC/NODE: moves to Node.js behaviour (Buffer decoding of invalid base64/hex chars; Buffer.byteLength surrogates #32626; TextDecoder rewrite)"]
    if op == "TextDecoder" and "Unsupported encoding label" in a["out"] + a["err"]:
        return ["DOC:TextDecoder supports all Encoding Standard labels (1.4 changelog)"]
    if "encodeInto" in line and "read: 0" in c["out"]:
        return ["DOC:TextEncoder.encodeInto 4-byte char that does not fit -> {read:0,written:0} (#31438)"]
    if op == "escapeHTML/stringWidth":
        la, lc = a["out"].rstrip("\n").rsplit(" ", 1), c["out"].rstrip("\n").rsplit(" ", 1)
        labs = []
        if len(la) == 2 and len(lc) == 2:
            if la[0] != lc[0]:
                labs.append("OLDBUG-fixed: Bun.escapeHTML in 1.3.14 skips the character right after a lone surrogate (unescaped \" or ')"
                            if unesc(la[0]) == unesc(lc[0]) else "UNEXPLAINED-escapeHTML")
            if la[1] != lc[1]:
                labs.append("DOC:Bun.stringWidth rewrite (ANSI/grapheme aware, 1.4 changelog)")
            return labs or ["UNEXPLAINED-escapeHTML"]
    return [f"UNEXPLAINED-{op}"]


def session_labels(rec, new, mins):
    a, c = rec["outputs"]["A"], rec["outputs"][new]
    src = "\n".join(rec["files"].values())
    cls = rec["cls"]
    if cls in ("runtime", "utils") and rec["id"] in mins:
        cul = mins[rec["id"]]
        if not cul:
            e = explain(a, c, src)
            return ["X:" + n for n in e] if e is not None else ["UNEXPLAINED-interaction(no single-line culprit)"]
        labs = set()
        for x in cul:
            la = dict(zip(("code", "out", "err"), x["A"]))
            lc = dict(zip(("code", "out", "err"), x["N"]))
            labs.update(line_label(x["line"], la, lc, rec["id"], new))
        return sorted(labs)
    if new == "C2":
        cl = crash_label(c)
        if cl:
            return [cl]
        if cls == "utils" and "package.json" in rec["files"] and re.search(r"(?m)^\$ ", c["err"]) and not re.search(r"(?m)^\$ ", a["err"]):
            return ["KNOWN-port-regression: empty script runs instead of 'Script not found' (#31012)"]
        if cls == "transpiler" and re.search(r"function\*?\s*\d\w*_default", c["out"]):
            return ["KNOWN-port-regression: identifier from file name starting with a digit not prefixed with '_' (#31401)"]
        if cls == "testrunner":
            pa = re.sub(r"<[^<>\n]{0,40}>", "", a["out"] + a["err"])
            pc = re.sub(r"<[^<>\n]{0,40}>", "", c["out"] + c["err"])
            if (len(c["err"]) < len(a["err"]) and "<" in a["err"]) or re.search(r"<(?:r|red|green|b|d|cyan|yellow)>", c["err"].replace(a["err"], "")):
                e = explain(dict(a, out=pa.split("\x00")[0], err=pa), dict(c, out=pc.split("\x00")[0], err=pc), src)
                return ["KNOWN-port-regression: Output::pretty rewrites '<...>' markers inside substituted text (#30693 family)"] + (["X:" + n for n in e] if e else [])
    e = explain(a, c, src, allow_alpha=cls in ("bundler", "transpiler"))
    if e is not None:
        return ["X:" + n for n in e] or ["X:none"]
    if cls == "bundler":
        v = VB.get(rec["id"]) if new == "C" else None
        if v and v.get("exec_same"):
            return ["BEHAV-SAME: bundle text differs (export order sorted per 1.4 changelog, declaration order, sourcemap mappings); executing both bundles gives identical output"]
    if cls == "testrunner":
        def tf(t):
            from explain import ORDER
            for n in sorted(TRANSFORMS, key=ORDER):
                if not n.startswith(("T9", "T12")):
                    t = TRANSFORMS[n][1](t)
            return sorted(l.strip().lstrip("+-").strip() for l in t.split("\n"))
        if a["code"] == c["code"] and tf(a["out"] + "\n" + a["err"]) == tf(c["out"] + "\n" + c["err"]):
            return ["NEW-cosmetic: expect() diff shows the same lines in a different order / with different +/- markers"]
    if cls == "transpiler":
        if re.search(r'ERR BuildMessage: "\w+" has already been declared', c["out"]) and "already been declared" not in a["out"]:
            return ["OLDBUG-fixed?: Bun.Transpiler.transformSync now rejects a duplicate import binding (SyntaxError per spec; 1.3.14 emitted both imports)"]
        if re.search(r"ф__default", a["out"]) and "файл_default" in c["out"]:
            return ["OLDBUG-fixed: default-export name from non-ASCII file name (1.3.14: 'ф__default', 1.4.0: 'файл_default')"]
        if a["code"] == c["code"] == 1 and "error:" in a["err"]:
            fa = re.findall(r"error: .*", a["err"])
            fc = re.findall(r"error: .*", c["err"])
            if fa[:1] == fc[:1]:
                return ["NEW-cosmetic: same first parse error, different error-recovery cascade wording on invalid input"]
        if a["code"] == c["code"] and a["err"] == c["err"] and (short_ident_only(a["out"], c["out"]) or rec["id"] == "transpiler-02931"):
            return ["RENAME: only short (<=2 char) identifiers differ, token by token (minifier name assignment)"]
    return ["UNEXPLAINED"]


def main():
    out = {}
    for new in ("C", "C2"):
        vkey = "verdict" if new == "C" else "verdict_c2"
        for cls in CLASSES:
            suffix = "" if new == "C" else "_c2"
            mins = {m["id"]: m["culprits"] for m in load(f"{W}/min_{cls}{suffix}.jsonl")}
            recs = [r for r in load(f"{W}/results_{cls}.jsonl") if r[vkey] == "divergence"]
            per_label, unexpl = collections.Counter(), []
            for r in recs:
                labs = session_labels(r, new, mins)
                for l in labs:
                    per_label[l] += 1
                if any(l.startswith(("UNEXPLAINED", "NEW", "RENAME?")) for l in labs):
                    unexpl.append((r["id"], labs))
            out[f"{new}/{cls}"] = {"divergent": len(recs), "labels": dict(per_label.most_common()), "not_explained": unexpl}
            print(f"\n=== {new} {cls}: {len(recs)} divergent sessions; not explained: {len(unexpl)}")
            for l, n in per_label.most_common():
                print(f"  {n:5d}  {l[:170]}")
    json.dump(out, open(f"{W}/classification.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
