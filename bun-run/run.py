"""Differential runner: A=old, B=old, C=new, C2=canary per session.

python3 -I run.py sessions.jsonl results.jsonl [workers]
Writes one JSON line per session: verdicts, normalization counts, and raw (normalized) outputs whenever
not all four runs are identical.
"""
import concurrent.futures as cf
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

W = os.path.dirname(os.path.abspath(__file__))
BINS = {
    "A": f"{W}/dl/old/bun-darwin-aarch64/bun",
    "B": f"{W}/dl/old/bun-darwin-aarch64/bun",
    "C": f"{W}/dl/new/bun-darwin-aarch64/bun",
    "C2": f"{W}/dl/canary/package/bin/bun",
}
ORDER = ["A", "C", "B", "C2"]
RUNS = f"{W}/runs"
TIMEOUT = 30

# --- registered normalizations
VER = r"(?:1\.3\.14-canary\.1|1\.3\.14|1\.4\.0)"
N2_RE = [
    (re.compile(r"(?i)(\bbun(?: test| build| run)? v)" + VER + r"(?:\+[0-9a-f]{7,12})?"), r"\1<VER>"),
    (re.compile(r"\((?:0d9b296af?|34cbb9a40?|19d8ade2c?)\)"), "(<REV>)"),
    (re.compile(r"bun\.report/" + VER + r"/[A-Za-z0-9_+/=-]+"), "bun.report/<VER>/<TRACE>"),
]
N3_RE = [
    re.compile(r"\[\d+(?:\.\d+)?(?:ms|s|µs|ns)\]"),
    re.compile(r"\bin \d+(?:\.\d+)?(?:ms|s)\b"),
]


def normalize(text, rundir, counts):
    out = text
    for d in sorted({rundir, os.path.realpath(rundir), rundir.replace("/private/tmp/", "/tmp/")}, key=len, reverse=True):
        if d in out:
            counts["N1"] = counts.get("N1", 0) + 1
            out = out.replace(d, "<DIR>")
    for rx, rep in N2_RE:
        out2 = rx.sub(rep, out)
        if out2 != out:
            counts["N2"] = counts.get("N2", 0) + 1
            out = out2
    for rx in N3_RE:
        out2 = rx.sub("<T>", out)
        if out2 != out:
            counts["N3"] = counts.get("N3", 0) + 1
            out = out2
    return out


def env_for(role):
    home = f"{W}/home/{role}"
    os.makedirs(f"{home}/tmp", exist_ok=True)
    return {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": home, "TMPDIR": f"{home}/tmp/", "BUN_INSTALL": f"{home}/.bun",
        "BUN_INSTALL_CACHE_DIR": f"{home}/cache", "XDG_CACHE_HOME": f"{home}/xdg",
        "NO_COLOR": "1", "FORCE_COLOR": "0", "DO_NOT_TRACK": "1", "BUN_RUNTIME_TRANSPILER_CACHE_PATH": "0",
        "TZ": "UTC", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "CI": "", "TERM": "dumb",
    }


ENVS = {r: env_for(r) for r in BINS}


def write_files(d, files):
    for name, content in files.items():
        p = os.path.join(d, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", errors="surrogatepass") as f:
            f.write(content)


def run_one(sess, role):
    d = f"{RUNS}/{sess["id"]}/{role}/w"
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    write_files(d, sess["files"])
    argv = [BINS[role] if a == "{BUN}" else a for a in sess["argv"]]
    t0 = time.time()
    counts = {}
    try:
        p = subprocess.run(argv, cwd=d, env=ENVS[role], capture_output=True, timeout=TIMEOUT, stdin=subprocess.DEVNULL)
        res = {"code": p.returncode,
               "out": normalize(p.stdout.decode("utf-8", "backslashreplace"), d, counts),
               "err": normalize(p.stderr.decode("utf-8", "backslashreplace"), d, counts)}
    except subprocess.TimeoutExpired:
        res = {"code": "TIMEOUT", "out": "", "err": ""}
    except OSError as e:
        res = {"code": "OSERROR", "out": "", "err": str(e)}
    res["sec"] = round(time.time() - t0, 3)
    res["norm"] = counts
    return res


def key(r):
    return hashlib.sha256(json.dumps([r["code"], r["out"], r["err"]], ensure_ascii=False).encode()).hexdigest()


def do_session(sess):
    res = {role: run_one(sess, role) for role in ORDER}
    shutil.rmtree(f"{RUNS}/{sess['id']}", ignore_errors=True)
    k = {role: key(r) for role, r in res.items()}
    bad = lambda r: r["code"] in ("TIMEOUT", "OSERROR")  # noqa: E731
    if bad(res["A"]) or bad(res["B"]) or bad(res["C"]):
        verdict = "excluded"
    elif k["A"] != k["B"]:
        verdict = "noise"
    elif k["C"] != k["A"]:
        verdict = "divergence"
    else:
        verdict = "same"
    if bad(res["A"]) or bad(res["B"]) or bad(res["C2"]):
        v2 = "excluded"
    elif k["A"] != k["B"]:
        v2 = "noise"
    elif k["C2"] != k["A"]:
        v2 = "divergence"
    else:
        v2 = "same"
    rec = {"id": sess["id"], "cls": sess["cls"], "fp": sess["fp"], "verdict": verdict, "verdict_c2": v2,
           "sec": {r: res[r]["sec"] for r in res}, "norm": {r: res[r]["norm"] for r in res},
           "codes": {r: res[r]["code"] for r in res}}
    if len(set(k.values())) > 1:
        rec["argv"] = sess["argv"]
        rec["files"] = sess["files"]
        rec["outputs"] = {r: {"code": res[r]["code"], "out": res[r]["out"][:20000], "err": res[r]["err"][:20000]} for r in res}
    return rec


def main():
    src, dst = sys.argv[1], sys.argv[2]
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    sessions = [json.loads(l) for l in open(src, encoding="utf-8")]
    done = set()
    if os.path.exists(dst):
        done = {json.loads(l)["id"] for l in open(dst, encoding="utf-8")}
    todo = [s for s in sessions if s["id"] not in done]
    t0 = time.time()
    with open(dst, "a", encoding="utf-8") as f, cf.ThreadPoolExecutor(workers) as ex:
        for i, rec in enumerate(ex.map(do_session, todo)):
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            if i % 250 == 0:
                print(f"{src}: {i}/{len(todo)} {time.time() - t0:.0f}s", flush=True)
    print(f"{src}: done {len(todo)} in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
