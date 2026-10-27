"""Per-class table: N, noise, excluded, k, Clopper-Pearson upper bound (delta/K), switch verdict.

uv run -q --with numpy --with scipy python -I analyze.py
"""
import collections
import json
import os
import re
import sys

W = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from parity import upper  # noqa: E402

CLASSES = ["runtime", "bundler", "transpiler", "testrunner", "utils"]
EPS, DELTA, K = 0.001, 0.05, 5
SURR = re.compile(r"\\u[dD][89abAB][0-9a-fA-F]{2}|\\u[dD][c-fC-F][0-9a-fA-F]{2}")


def w1(rec, new="C"):
    if not any(SURR.search(v) for v in rec["files"].values()):
        return False
    a, c = rec["outputs"]["A"], rec["outputs"][new]
    strip = lambda o: (o["code"], o["out"].replace("�", ""), o["err"].replace("�", ""))  # noqa: E731
    return strip(a) == strip(c)


def table(new="C"):
    vkey = "verdict" if new == "C" else "verdict_c2"
    rows = []
    for c in CLASSES:
        p = f"{W}/results_{c}.jsonl"
        if not os.path.exists(p):
            continue
        recs = [json.loads(l) for l in open(p, encoding="utf-8")]
        cnt = collections.Counter(r[vkey] for r in recs)
        div = [r for r in recs if r[vkey] == "divergence"]
        w1n = sum(w1(r, new) for r in div)
        k = len(div) - w1n
        n_eff = len(recs) - cnt["noise"] - cnt["excluded"]
        ub = upper(k, n_eff, DELTA / K)
        norm = collections.Counter()
        for r in recs:
            for role in ("A", "B", new):
                for nk, v in r["norm"][role].items():
                    norm[nk] += 1
        secs = sum(sum(r["sec"].values()) for r in recs)
        rows.append(dict(cls=c, N=len(recs), noise=cnt["noise"], excluded=cnt["excluded"], div_raw=len(div), w1=w1n, k=k,
                         n_eff=n_eff, ub=ub, switch=(k == 0 and ub <= EPS), norm=dict(norm), cpu_sec=round(secs)))
    return rows


if __name__ == "__main__":
    for new in ("C", "C2"):
        print(f"== new = {new}")
        for r in table(new):
            print(f"{r['cls']:11s} N={r['N']} noise={r['noise']} excl={r['excluded']} div={r['div_raw']} W1={r['w1']} k={r['k']} "
                  f"n_eff={r['n_eff']} UB={r['ub']:.4f} switch={'yes' if r['switch'] else 'no'} norm={r['norm']} run-sec={r['cpu_sec']}")
