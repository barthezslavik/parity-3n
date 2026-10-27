"""Python tomllib (TOML 1.0) as oracle for TOML culprit lines in utils. python3 -I toml_oracle.py min_utils.jsonl"""
import json, re, sys, tomllib, datetime, math, collections
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from ops import op_of
def js(v):
    if isinstance(v, float) and (math.isinf(v) or math.isnan(v)): return None
    if isinstance(v, dict): return {k: js(x) for k, x in v.items()}
    if isinstance(v, list): return [js(x) for x in v]
    if isinstance(v, (datetime.datetime,)): return v.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return v
def fmt_num(o):
    s = json.dumps(o, ensure_ascii=False, separators=(",", ":"))
    return re.sub(r"(?<=[:\[,])-?0\.0(?=[,\]}])", "0", s)
cnt = collections.Counter(); ex = collections.defaultdict(list)
for l in open(sys.argv[1]):
    r = json.loads(l)
    for x in r["culprits"]:
        if op_of(x["line"]) != "TOML": continue
        m = re.search(r"Bun\.TOML\.parse\((\".*?\")\)\)\);", x["line"])
        src = json.loads(m.group(1))
        try:
            ref = "OK " + fmt_num(js(tomllib.loads(src)))
        except Exception as e:
            ref = "ERR"
        a, n = x["A"][1].strip(), x["N"][1].strip()
        def cls(o): return "ERR" if o.startswith("ERR") else "OK " + o
        ca, cn = cls(a), cls(n)
        v = ("new==ref" if cn == ref and ca != ref else "old==ref" if ca == ref and cn != ref else "both==ref" if ca == cn == ref else "neither")
        cnt[v] += 1; ex[v].append((src, a, n, ref))
print(cnt)
for v in ("old==ref", "neither"):
    for e in ex[v][:6]: print(v, repr(e))
