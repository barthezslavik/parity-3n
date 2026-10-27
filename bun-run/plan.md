# Pre-registered plan — Bun 1.3.14 (Zig) vs 1.4.0 (Rust) parity run

Written 2026-10-27 before any session was run. Not to be edited after the run starts
(any later deviation is appended in a "Deviations" section at the bottom, with a reason).

## Systems
- OLD = Bun 1.3.14+0d9b296af (last Zig release), official bun-darwin-aarch64.zip, GitHub release bun-v1.3.14.
- NEW = Bun 1.4.0+34cbb9a40 (first release from the Rust port; blog: "Bun v1.4.0 will be the first version
  of Bun written in Rust"), official bun-darwin-aarch64.zip, release bun-v1.4.0.
- NEW2 (secondary, reported separately, not used for the switch verdict) = 1.3.14-canary.1+19d8ade2c,
  npm @oven/bun-darwin-aarch64@1.3.14-canary.20260514.1; commit 19d8ade2c is merge commit 23427dbc of
  PR #30412 ("Rewrite Bun in Rust") + 1 commit ("Delete stray files").

## Session
One session = one generated input (files in a fresh temp dir) + one CLI command. Each session runs:
A = OLD, B = OLD again (fresh dir), C = NEW, C2 = NEW2, every run in its own fresh dir, order A,C,B,C2.
Captured: exit code (or signal), stdout, stderr. Timeout 30 s.
Environment: HOME, TMPDIR, BUN_INSTALL, BUN_INSTALL_CACHE_DIR inside the work dir; NO_COLOR=1, FORCE_COLOR=0,
DO_NOT_TRACK=1, BUN_RUNTIME_TRANSPILER_CACHE_PATH=0, TZ=UTC, LANG=C.UTF-8. No network needed by any generator.

## Normalizations (the only ones allowed; each application is counted per class)
N1 run-dir absolute path (all spellings: /private/tmp/..., /tmp/...) -> <DIR>
N2 version / revision strings of the three binaries (1.3.14, 1.4.0, 1.3.14-canary.1, 0d9b296af, 34cbb9a40,
   19d8ade2c and their 8-char prefixes) -> <VER> / <REV>
N3 durations in bun test / bun build summaries: `[12.34ms]`, `[1.2s]`, `in 12ms` -> <T>
Nothing else. Platform strings (macOS Silicon etc.) are equal across binaries and are not normalized.

## Counting
- excluded: A or B or C timed out / failed to start (harness failure).
- noise: A != B (after normalization). Such sessions are not counted for divergence.
- divergence: A == B and C != A.
- n_eff = N - noise - excluded. Upper bound = one-sided Clopper-Pearson on (k, n_eff) at delta/K.

## Classes (K = 5 traffic classes) and generators (Python random.Random(seed), seed fixed per class)
1. runtime  — `bun run s.ts`: generated snippets printing via console.log: unicode strings incl. lone
   surrogates, emoji, combining marks; numbers/floats/-0/NaN/BigInt/radix/toFixed/toPrecision; Map/Set/
   nested objects/arrays/typed arrays/class instances/Symbols; Error objects; JSON.stringify/parse;
   string ops; Buffer (hex/base64/base64url/latin1/utf16le/ascii, odd lengths); TextEncoder/TextDecoder
   (incl. invalid bytes, fatal); URL / URLSearchParams on generated strings; crypto.createHash and
   Bun.CryptoHasher / Bun.hash on fixed input; atob/btoa; structuredClone; Bun.inspect; Bun.escapeHTML;
   Bun.stringWidth. seed 101.
2. bundler  — `bun build entry.ts [--minify] [--format=esm|cjs|iife] [--target=bun|node|browser]`
   on 1–4 generated modules (imports/exports, re-exports, default exports, consts folding, classes, JSON
   import, dead code); bundle to stdout. seed 202.
3. transpiler — `bun build --no-bundle f.(ts|tsx|jsx)` and `Bun.Transpiler.transformSync` with loader
   ts/tsx/jsx on generated TS/JSX (types, enums, namespaces, decorators-free, generics, JSX with
   attributes/spread/fragments/entities, optional chaining, template literals, numeric literals,
   file names incl. leading digits). seed 303.
4. test-runner — `bun test` on 1 generated `x.test.ts` with 1–6 tests (pass/fail mixes, expect matchers
   toBe/toEqual/toThrow/toContain/toMatchObject/toBeCloseTo/snapshots-free, describe/each, skip/todo). seed 404.
5. utils — `bun run u.ts` exercising Bun.semver.satisfies/order on generated versions & ranges,
   Bun.Glob.match on generated patterns/paths, Bun.TOML.parse on generated TOML, package.json
   field handling via `bun run <script>` on generated package.json scripts (echo-only, incl. empty script). seed 505.
Dedup: sha256 over (command, all input files); generator draws until N unique inputs.

Sanity set (not a traffic class, no bound): offline repros of public port regressions from
bun_regressions.md (#31401, #31012, #32686, #31575, #30960, #31188, #30757, #31001, #35644, #31636, #30711-ish).
Expectation: OLD == NEW on all (fixed), NEW2 (canary at merge) diverges on those present at merge.

## Thresholds (fixed before running)
eps = 0.1% per class, delta = 5% family-wise over K = 5 (Bonferroni, delta/K = 1%), k = 0:
N = n_required(0.001, 0.05, k=0, K=5) = 4603 sessions per class (from instrument/parity.py).
Switch rule: class switches iff k == 0 unexplained divergences among its N sessions
(=> upper bound <= 0.1% at 99%). Explained = listed in the whitelist below BEFORE the run.
Pre-registered whitelist of intentional differences:
 W1 #31001 lone surrogate printing (Zig printed nothing / NEW prints U+FFFD), accepted by maintainers.
Divergences found during the run are investigated and classified afterwards, but the verdict above is
computed on the pre-registered whitelist only; a post-hoc "if we whitelisted X" number is reported
separately and labelled as such.
Runtime cap: ~3 h. If the run would exceed it, fall back to eps = 1% (N = 459 per class) and say so.

## Pre-run amendments (made after a harness pilot, BEFORE the main run)
Pilot: 60 sessions per class with seed offset +7000 (disjoint from the main seeds), used only to debug the
harness; its results are not counted.
- P1 harness bug: N1 replaced "/tmp/..." before "/private/tmp/...", leaving "/private<DIR>" in half the runs
  (fake A!=B noise). Fixed: spellings replaced longest-first.
- P2 bundler generator imported `default` from modules that had none (half the sessions were the same
  "No matching export" error). Fixed: default is imported only when the module has one.
- P3 N2 is context-bound (only after "Bun v", "bun test v" etc., revisions in parentheses, bun.report URLs),
  so that semver inputs like "1.4.0" in class 5 are never rewritten.
- P4 operational rule for W1 (#31001): a divergence is explained by W1 iff the session source contains a
  lone-surrogate escape and A and C become identical after deleting every U+FFFD from both outputs.
- Seen in the pilot (NOT added to the whitelist, because no changelog entry was checked at that point):
  bundler export-map ordering, TOML error messages, URL error message format, iso-8859-2 support,
  source-column off-by-one on lines with astral characters, escapeHTML after lone surrogates.
  They will count as unexplained in the verdict.
