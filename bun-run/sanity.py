"""Sanity set: offline repros of public Rust-port regressions (bun_regressions.md), run on A, B, C, C2.

python3 -I sanity.py results_sanity.jsonl
Same normalizations as run.py; the binary's own dir is prepended to PATH so scripts can call `bun`.
Each repro is run REPEAT times (#31636 is a use-after-free that can vary between runs).
"""
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run as R  # noqa: E402

REPEAT = 5
LIB_C = "int add(int a, int b) { return a + b; }\n"

REPROS = {
    "31401": (["{BUN}", "run", "1.ts"], {"1.ts": "export default function () {}\nconsole.log(\"ok\");\n"}),
    "31012": (["{BUN}", "run", "build"], {"package.json": json.dumps({"name": "p", "scripts": {"build": ""}})}),
    "32686": (["{BUN}", "build.ts"], {
        "entry.ts": "console.log(WORKER_PATH)\n",
        "build.ts": "const result = await Bun.build({ entrypoints: [\"entry.ts\"], outdir: \"dist\", define: { WORKER_PATH: \"./src/worker.ts\" } });\n"
                    "console.log(result.success);\nif (result.success) console.log(await Bun.file(\"dist/entry.js\").text());\n"}),
    "31575": (["{BUN}", "build.mjs"], {
        "assets/nested/data.txt": "hello",
        "entry.ts": "import assetPath from './assets/nested/data.txt' with { type: 'file' }\n"
                    "console.log('embeddedFiles:', JSON.stringify(Bun.embeddedFiles.map((f) => f.name)))\n"
                    "console.log('content      :', await Bun.file(assetPath).text())\n",
        "build.mjs": "const r = await Bun.build({ entrypoints: ['entry.ts'], compile: { outfile: 'app' }, naming: { asset: '[dir]/[name].[ext]' } })\n"
                     "if (!r.success) { for (const l of r.logs) console.error(String(l)); process.exit(1) }\n"
                     "const p = Bun.spawnSync(['./app']); console.log(p.stdout.toString()); console.log(p.stderr.toString(), p.exitCode)\n"}),
    "30960": (["{BUN}", "run", "p.ts"], {"p.ts": "import { password } from \"bun\";\n"
                                                 "const hash = await password.hash(\"test\", { algorithm: \"argon2id\", memoryCost: 3, timeCost: 1 });\n"
                                                 "console.log(hash.split(\"$\").find(s => s.includes(\"m=\")));\n"}),
    "31188": (["{BUN}", "run", "b.js"], {"b.js": "const b = new Blob([new Uint8Array([0xFF, 0xFE, 0x41, 0x41, 0x41, 0x41, 0x41])]);\n"
                                                 "const t = await b.text(); console.log(t.length, escape(t));\n"
                                                 "await Bun.write(\"f.bin\", new Uint8Array([0xFF, 0xFE, 0x41]));\n"
                                                 "console.log(escape(await Bun.file(\"f.bin\").text()));\n"}),
    "30757": (["{BUN}", "run", "s.js"], {"s.js": "const input = 1751241600000; const it = [...new Set([input])]; console.log(it[0], it[0] === input);\n"
                                                 "const m = new Map([[2**31, 'a'], [2**32 + 5, 'b']]); console.log([...m.keys()]);\n"}),
    "31001": (["{BUN}", "run", "u.js"], {"u.js": "console.log(\"𐀀\"[0]);\nconsole.log(\"\\uD800\");\n"}),
    "35644": (["{BUN}", "b.ts"], {
        "logo.png": "PNG",
        "entry.ts": "import logo from './logo.png'; console.log(logo);\n",
        "b.ts": "const r = await Bun.build({ entrypoints: ['entry.ts'], outdir: 'out', target: 'browser', naming: { asset: '[target]/[name].[ext]' } });\n"
                "console.log(r.success, r.outputs.map(o => o.path.slice(process.cwd().length)).sort());\n"}),
    "31636": (["{BUN}", "run", "--parallel", "--filter=pdf-service", "dev"], {
        "package.json": json.dumps({"name": "monorepo-root", "private": True, "workspaces": ["packages/*"]}),
        "packages/pdf-service/package.json": json.dumps({"name": "pdf-service", "scripts": {"dev": "bun index.ts"}}),
        "packages/pdf-service/index.ts": "console.log(\"started\");\n"}),
    "30711": (["{BUN}", "run", "--bun", "bun", "run", "--bun", "x"], {
        "package.json": json.dumps({"name": "x", "scripts": {"x": "node -e \"console.log(typeof Bun)\""}})}),
    "30717": (["{BUN}", "build.ts"], {
        "lib.c": LIB_C,
        "entry.ts": "import { dlopen, FFIType } from 'bun:ffi';\nimport lib from './libadd.dylib' with { type: 'file' };\n"
                    "const { symbols } = dlopen(lib, { add: { args: [FFIType.i32, FFIType.i32], returns: FFIType.i32 } });\n"
                    "console.log('add', symbols.add(2, 3));\n",
        "build.ts": "const c = Bun.spawnSync(['/usr/bin/cc', '-shared', '-o', 'libadd.dylib', 'lib.c']); if (c.exitCode) throw new Error('cc');\n"
                    "const r = await Bun.build({ entrypoints: ['entry.ts'], compile: { outfile: 'app' } });\n"
                    "if (!r.success) { for (const l of r.logs) console.error(String(l)); process.exit(1) }\n"
                    "const p = Bun.spawnSync(['./app']); console.log(p.stdout.toString(), p.stderr.toString().split('\\n').slice(-6).join('\\n'), p.exitCode)\n"}),
}


def run_one(sid, role, argv, files):
    d = f"{R.RUNS}/sanity-{sid}/{role}"
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    R.write_files(d, files)
    env = dict(R.ENVS[role])
    env["PATH"] = os.path.dirname(R.BINS[role]) + ":" + env["PATH"]
    counts = {}
    try:
        p = subprocess.run([R.BINS[role] if a == "{BUN}" else a for a in argv], cwd=d, env=env, capture_output=True,
                           timeout=60, stdin=subprocess.DEVNULL)
        res = {"code": p.returncode, "out": R.normalize(p.stdout.decode("utf-8", "backslashreplace"), d, counts),
               "err": R.normalize(p.stderr.decode("utf-8", "backslashreplace"), d, counts)}
    except subprocess.TimeoutExpired:
        res = {"code": "TIMEOUT", "out": "", "err": ""}
    shutil.rmtree(d, ignore_errors=True)
    return res


def main():
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        for issue, (argv, files) in REPROS.items():
            for rep in range(REPEAT):
                res = {role: run_one(f"{issue}-{rep}", role, argv, files) for role in R.ORDER}
                k = {r: R.key(v) for r, v in res.items()}
                f.write(json.dumps({"issue": issue, "rep": rep, "A==B": k["A"] == k["B"], "C==A": k["C"] == k["A"],
                                    "C2==A": k["C2"] == k["A"], "outputs": res}, ensure_ascii=False) + "\n")
                print(issue, rep, k["A"] == k["B"], k["C"] == k["A"], k["C2"] == k["A"], flush=True)


if __name__ == "__main__":
    main()
