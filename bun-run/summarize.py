"""Final tables: pre-registered verdict + post-hoc buckets, with Clopper-Pearson bounds.

uv run -q --with numpy --with scipy python -I summarize.py  -> summary.json + printed tables
"""
import collections
import json
import os
import sys

W = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, W)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from parity import upper  # noqa: E402

import analyze  # noqa: E402
import classify  # noqa: E402

DELTA, K, EPS = 0.05, 5, 0.001
MANUAL = {"C/testrunner-01948": ["NEW-cosmetic: expect() diff shows the same lines in a different order / with different +/- markers (manual review)"],
          "C2/testrunner-03080": ["KNOWN-port-regression: Output::pretty rewrites '<...>' markers inside substituted text (#30693 family) (manual review)"]}

PRIO = ["UNEXPLAINED", "NEW", "KNOWN-port", "KNOWN-undoc", "FORMAT-undoc", "OLDBUG", "EQUIV", "DOC", "NOISE"]


def bucket(label):
    if label.startswith("UNEXPLAINED"):
        return "UNEXPLAINED"
    if label.startswith("NEW"):
        return "NEW"
    if label.startswith("KNOWN-port"):
        return "KNOWN-port"
    if label.startswith("KNOWN-undocumented"):
        return "KNOWN-undoc"
    if label.startswith(("X:T7", "X:T8", "X:T10", "X:T12")):
        return "FORMAT-undoc"
    if label.startswith(("OLDBUG", "X:T13")):
        return "OLDBUG"
    if label.startswith(("RENAME", "X:T11", "BEHAV-SAME")):
        return "EQUIV"
    if label.startswith("X:T0"):
        return "NOISE"
    return "DOC"  # X:T1 T2 T3 T4 T9, DOC:*, DOC/NODE


def main():
    summary = {}
    for new in ("C", "C2"):
        vkey = "verdict" if new == "C" else "verdict_c2"
        base = {r["cls"]: r for r in analyze.table(new)}
        print(f"\n######## new = {new}")
        for cls in classify.CLASSES:
            suffix = "" if new == "C" else "_c2"
            mins = {m["id"]: m["culprits"] for m in classify.load(f"{W}/min_{cls}{suffix}.jsonl")}
            recs = [r for r in classify.load(f"{W}/results_{cls}.jsonl") if r[vkey] == "divergence"]
            b = collections.Counter()
            for r in recs:
                labs = MANUAL.get(f"{new}/{r['id']}") or classify.session_labels(r, new, mins)
                bs = {bucket(l) for l in labs}
                b[min(bs, key=PRIO.index)] += 1
            t = base[cls]
            n_eff = t["n_eff"]
            # k after successive post-hoc explanation levels
            k_pre = t["k"]
            k_doc = sum(v for kk, v in b.items() if kk not in ("DOC", "NOISE"))  # remove documented + noise
            k_beh = sum(v for kk, v in b.items() if kk in ("UNEXPLAINED", "NEW", "KNOWN-port", "KNOWN-undoc", "FORMAT-undoc"))  # also old bugs fixed + equivalent text
            k_new = sum(v for kk, v in b.items() if kk in ("UNEXPLAINED", "NEW", "KNOWN-undoc"))
            k_reg = b.get("KNOWN-port", 0)
            row = dict(t, buckets=dict(b), k_pre=k_pre, ub_pre=upper(k_pre, n_eff, DELTA / K), k_doc=k_doc, ub_doc=upper(k_doc, n_eff, DELTA / K),
                       k_beh=k_beh, ub_beh=upper(k_beh, n_eff, DELTA / K), k_new=k_new, ub_new=upper(k_new, n_eff, DELTA / K), k_reg=k_reg)
            summary[f"{new}/{cls}"] = row
            print(f"{cls:11s} N={t['N']} noise(A!=B)={t['noise']} ({t['noise'] / t['N']:.2%}) excl={t['excluded']} n_eff={n_eff} | "
                  f"k_pre={k_pre} UB={row['ub_pre']:.4f} | k_doc={k_doc} UB={row['ub_doc']:.4f} | k_beh={k_beh} UB={row['ub_beh']:.4f} | "
                  f"k_new={k_new} UB={row['ub_new']:.4f} | port-regr={k_reg} | {dict(b)}")
    json.dump(summary, open(f"{W}/summary.json", "w"), ensure_ascii=False, indent=1, default=float)


if __name__ == "__main__":
    main()
