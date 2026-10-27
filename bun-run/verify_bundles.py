"""Behavioural check of divergent bundles: run the bundle produced by old (A) and by new (C) with the SAME
runtime (old bun 1.3.14) and compare normalized output. Also try the textual explanation T6 (sorted
namespace export map + first-appearance canonicalisation of short minified identifiers).

python3 -I verify_bundles.py results_bundler.jsonl verify_bundler.jsonl [new=C]
"""
import concurrent.futures as cf
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run as R  # noqa: E402

JS_KW = set("as do if in of to var let for new try case else enum eval null this true void with break catch class const false super throw while yield async await delete export import return static switch typeof default extends finally package private continue debugger function arguments interface protected implements instanceof get set".split())


def t6(text):
    # sort entries of export maps: non-minified multi-line form
    lines, out, buf = text.split("\n"), [], []
    entry = re.compile(r"^\s+[\w$\"]+: \(\) => [\w$]+,?$")
    for ln in lines + [None]:
        if ln is not None and entry.match(ln):
            buf.append(ln.rstrip(","))
            continue
        if buf:
            out.extend(sorted(buf))
            buf = []
        if ln is not None:
            out.append(ln)
    text = "\n".join(out)
    # minified form {a:()=>b,c:()=>d}
    text = re.sub(r"\{((?:[\w$]+:\(\)=>[\w$]+,?)+)\}", lambda m: "{" + ",".join(sorted(m.group(1).split(","))) + "}", text)
    # canonicalise short identifiers by first appearance
    names = {}

    def rep(m):
        w = m.group(0)
        if w in JS_KW or len(w) > 2:
            return w
        names.setdefault(w, f"$${len(names)}")
        return names[w]
    return re.sub(r"(?<![\w$.])[A-Za-z_$][\w$]?(?![\w$])", rep, text)


def ext_for(argv):
    fmt = next((a.split("=")[1] for a in argv if a.startswith("--format=")), "esm")
    return {"esm": "mjs", "cjs": "cjs", "iife": "js"}[fmt]


def exec_bundle(sid, tag, code, ext, files):
    d = f"{R.RUNS}/vb-{sid}-{tag}/w"
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    R.write_files(d, files)  # original sources present too (some bundles keep external refs)
    with open(f"{d}/bundle.{ext}", "w", encoding="utf-8", errors="surrogatepass") as f:
        f.write(code)
    counts = {}
    try:
        p = subprocess.run([R.BINS["A"], f"bundle.{ext}"], cwd=d, env=R.ENVS["A"], capture_output=True, timeout=30)
        res = (p.returncode, R.normalize(p.stdout.decode("utf-8", "backslashreplace"), d, counts),
               re.sub(r"bundle\.\w+:\d+:\d+", "bundle:L:C", R.normalize(p.stderr.decode("utf-8", "backslashreplace"), d, counts)))
    except subprocess.TimeoutExpired:
        res = ("TIMEOUT", "", "")
    shutil.rmtree(os.path.dirname(d), ignore_errors=True)
    return res


def check(r, new):
    a, c = r["outputs"]["A"], r["outputs"][new]
    rec = {"id": r["id"], "argv": r["argv"], "t6": t6(a["out"]) == t6(c["out"]) and a["err"] == c["err"] and a["code"] == c["code"]}
    if a["code"] == 0 and c["code"] == 0:
        ext = ext_for(r["argv"])
        ra = exec_bundle(r["id"], "a", a["out"], ext, r["files"])
        rc = exec_bundle(r["id"], "c", c["out"], ext, r["files"])
        rec["exec_same"] = ra == rc
        if not rec["exec_same"]:
            rec["exec"] = {"A": ra, "C": rc}
    return rec


def main():
    new = sys.argv[3] if len(sys.argv) > 3 else "C"
    vkey = "verdict" if new == "C" else "verdict_c2"
    recs = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8")]
    recs = [r for r in recs if r[vkey] == "divergence"]
    with cf.ThreadPoolExecutor(8) as ex:
        out = list(ex.map(lambda r: check(r, new), recs))
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        for o in out:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
    import collections
    print(collections.Counter((o["t6"], o.get("exec_same")) for o in out))


if __name__ == "__main__":
    main()
