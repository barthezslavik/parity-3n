"""Line-level minimization of divergent runtime/utils sessions.

python3 -I minimize.py results_<cls>.jsonl <file-name> out.jsonl [new=C]
For every divergent session, each source line is run alone on A and on new (fresh dirs, same normalizations).
Lines that diverge alone are the culprits. Output: {"id", "culprits": [line, ...]} per session.
"""
import concurrent.futures as cf
import json
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import run as R  # noqa: E402

CACHE = {}


def line_diverges(argv, fname, line, new):
    key = (fname, line, new)
    if key in CACHE:
        return CACHE[key]
    sess = {"id": "min-" + str(abs(hash(key))), "argv": argv, "files": {fname: line + "\n"}}
    a = R.run_one(sess, "A")
    c = R.run_one(dict(sess, id=sess["id"] + "c"), new)
    import shutil
    shutil.rmtree(f"{R.RUNS}/{sess['id']}", ignore_errors=True)
    shutil.rmtree(f"{R.RUNS}/{sess['id']}c", ignore_errors=True)
    res = R.key(a) != R.key(c)
    CACHE[key] = (res, a, c)
    return CACHE[key]


def main():
    src, fname, dst = sys.argv[1], sys.argv[2], sys.argv[3]
    new = sys.argv[4] if len(sys.argv) > 4 else "C"
    vkey = "verdict" if new == "C" else "verdict_c2"
    recs = [json.loads(l) for l in open(src, encoding="utf-8")]
    recs = [r for r in recs if r[vkey] == "divergence" and fname in r["files"]]
    jobs = []
    for r in recs:
        for line in r["files"][fname].split("\n"):
            if line.strip():
                jobs.append((r["id"], r["argv"], line))
    uniq = {(argv_t, line) for _, argv_t, line in ((i, tuple(a), l) for i, a, l in jobs)}
    with cf.ThreadPoolExecutor(8) as ex:
        list(ex.map(lambda t: line_diverges(list(t[0]), fname, t[1], new), uniq))
    with open(dst, "w", encoding="utf-8") as f:
        for r in recs:
            cul = []
            for line in r["files"][fname].split("\n"):
                if line.strip():
                    d, a, c = CACHE[(fname, line, new)]
                    if d:
                        cul.append({"line": line, "A": [a["code"], a["out"][:20000], a["err"][:20000]], "N": [c["code"], c["out"][:20000], c["err"][:20000]]})
            f.write(json.dumps({"id": r["id"], "culprits": cul}, ensure_ascii=False) + "\n")
    print("sessions", len(recs), "unique lines", len(uniq))


if __name__ == "__main__":
    main()
