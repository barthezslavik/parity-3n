# parity-3n

When is a rewritten system ready to replace the old one? Green tests are not the answer:
Bun's agent-driven Zig → Rust port merged with 100% of its test suite passing and then shipped regressions.

This repo has three things:

1. **`parity.py`** — a calculator for the cutover rule and the math behind the "N clean in a row" trap.
2. **`data/bun_rust_port_regressions.csv`** — 18 regressions of the Bun Rust port confirmed from public issues and PRs
   (Bun reports 19 but publishes no list), classified by why the test suite missed them.
3. **`run_vs_window.png`** — how often three common stopping rules switch a broken traffic class.

## The rule

A traffic class switches when, on a **pre-registered fixed window** of N independent sessions, the one-sided
Clopper–Pearson upper bound on the rate of unexplained divergences between old and new is ≤ ε at confidence 1 − δ.

- k = 0 divergences: N = ln(1/δ)/ε, i.e. ~3/ε at δ = 5% (the textbook "rule of three"; the application is the point).
- K classes switched together under one family-wise δ: N = ln(K/δ)/ε.
- Count sessions (deduplicated by input fingerprint), not requests. Window ≥ 1 week, one code/config version.
- A divergence counts only where two copies of the old system agree (A = B) and the new one differs.
- A failed window is closed by a new code version or a registry entry for an intentional difference — **never by rerunning it**.

```
uv run --with numpy --with scipy --with matplotlib parity.py
```

```python
from parity import n_required
n_required(0.001)            # 2995 sessions for 0.1% at 95%
n_required(0.001, k=2)       # 6294 — size N for power, not just for the bound
n_required(0.001, K=20)      # 5989 per class for 20 classes
```

## The trap (threshold 0.1%, N = 2,995, a month of traffic = 30 windows)

| Stopping rule | class 2× worse | 1.5× worse | at threshold |
|---|---|---|---|
| N clean in a row, restart after each divergence | 36% | 79% | 99.5% |
| fixed window, rerun on the same build after a failure | 7.2% | 29% | 79% |
| fixed window, failure closed only by a new version | 0.2% | 1.1% | 5% |

Exact formulas; a Monte Carlo in the script is only a sanity check. Power of the strict rule: a class at a quarter of
the threshold passes with 47% (k = 0, N = 2,995), 79% (k = 2, N = 6,294), 95% (k = 5, N = 10,511).

## The Bun dataset

Sources: Bun's post "Rewriting Bun in Rust" (2026-07-08), PR #30412 (merged 2026-05-14T08:09Z), community tracker
#31477, and every issue/PR cited in the CSV. Blind spots: A — input not in tests; B — ported line by line, behaves
differently; C — noise; D — intentional difference nobody recorded; E — limits, state, timing, load.

| Blind spot | Regressions |
|---|---|
| B — ported line by line, behaves differently | 12 |
| E — limits, state, timing, load | 3 |
| D — unrecorded intentional difference | 2 |
| A — input not in tests | 1 |

Median days from merge to discovery: 14.6. 11 of 18 came from user reports. A shadow diff against Zig 1.3.14 on the
same inputs would plausibly catch 14 of 18 (about 7 without caveats such as TTY capture or salt normalization);
2 not at all (a pure slowdown and a thread race). The "would catch" column is a judgment, not a measurement.

## A real run on Bun (`bun-run/`)

Pre-registered plan (`plan.md`, hashed in `prereg.sha256` before the first session): 5 classes (runtime, bundler,
transpiler, test runner, utils), ε = 0.1%, family δ = 5%, k = 0 → N = 4,603 sessions per class; generated offline
inputs with fixed seeds. Each session runs Bun 1.3.14 (Zig) twice, the npm canary built from the port's merge commit
(1.3.14-canary.1+19d8ade2c, 2026-05-14), and Bun 1.4.0 (Rust). 23,015 sessions, 92,060 CLI calls, ~20 minutes on
macOS arm64.

- **Merge-day canary vs Zig:** the bundler passes (0 divergences, bound 0.100%); the other four classes fail. Found
  without hints: #31188 (panic, 44 sessions), #31401 (47), the #30693 family (754), #31012 (74), and a semver
  `unreachable` panic fixed in PR #31234 (35) that is not in the 18-regression list. 9 of 12 offline repros diverge.
- **1.4.0 vs Zig:** no class passes (k = 116…3,542), almost entirely from changes made on purpose after the merge and
  listed in the 1.4 changelog, behaviour-equal bundles, and old Zig bugs fixed silently. 23 undocumented divergent
  sessions remain after a post-hoc review (e.g. `Bun.semver.satisfies("10.10.19", "1.0.0 || a - 0")` true → false).
- Lessons: keep the intentional-differences registry *before* the window; one A/B pair estimates noise but does not
  filter it per session (141 noisy test-runner sessions counted as divergences).

Raw results (~45 MB of JSONL) are not committed; the generators and runner reproduce them.

Corrections welcome — open an issue with a link to the primary source.
