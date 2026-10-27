"""Node.js v26 as a reference oracle for culprit lines that use only Node-compatible APIs.

python3 -I oracle.py min_<cls>.jsonl oracle_<cls>.jsonl
For each culprit line not explained by explain.TRANSFORMS and not using Bun.* / await Blob, run it with node
(as .mjs, same cwd layout) and compare stdout with old (A) and new (N).
"""
import concurrent.futures as cf
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from explain import explain  # noqa: E402
from ops import op_of  # noqa: E402

W = os.path.dirname(os.path.abspath(__file__))
NODE = "/opt/homebrew/bin/node"


def node_out(line):
    d = f"{W}/runs/node-{abs(hash(line))}"
    os.makedirs(d, exist_ok=True)
    with open(f"{d}/s.mjs", "w", encoding="utf-8") as f:
        f.write("import { Buffer } from 'node:buffer'; import { createRequire } from 'node:module'; const require = createRequire(import.meta.url);\n" + line + "\n")
    p = subprocess.run([NODE, "s.mjs"], cwd=d, capture_output=True, timeout=30, env={"PATH": "/usr/bin:/bin", "TZ": "UTC", "NO_COLOR": "1"})
    shutil.rmtree(d, ignore_errors=True)
    return p.stdout.decode("utf-8", "backslashreplace")


def main():
    items = []
    for l in open(sys.argv[1], encoding="utf-8"):
        r = json.loads(l)
        for x in r["culprits"]:
            a = dict(zip(("code", "out", "err"), x["A"]))
            c = dict(zip(("code", "out", "err"), x["N"]))
            if explain(a, c, x["line"]) is not None or "Bun." in x["line"] or "new Blob" in x["line"]:
                continue
            items.append((r["id"], x["line"], a, c))
    with cf.ThreadPoolExecutor(8) as ex:
        outs = list(ex.map(lambda t: node_out(t[1]), items))
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        for (sid, line, a, c), n in zip(items, outs):
            v = ("new==node" if c["out"] == n and a["out"] != n else "old==node" if a["out"] == n and c["out"] != n
                 else "both==node(out)" if a["out"] == n == c["out"] else "neither")
            f.write(json.dumps({"id": sid, "op": op_of(line), "line": line, "verdict": v, "node": n, "A": a["out"], "N": c["out"]}, ensure_ascii=False) + "\n")
    print(len(items))


if __name__ == "__main__":
    main()
