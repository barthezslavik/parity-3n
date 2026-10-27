"""Parity calculator and the "N clean in a row" trap, for the parity-definition article.

    uv run --with numpy --with scipy --with matplotlib parity.py

n_required(eps, delta, k, K): sessions needed so that k unexplained divergences on a fixed, pre-registered
window still give a one-sided Clopper-Pearson upper bound <= eps at family-wise confidence 1-delta over K classes.
The simulation compares two stopping rules on a stream with true divergence rate p:
  fixed window   — run N sessions once, switch if k == 0 (fail on the first divergence);
  run in a row   — keep going, restart the count after every divergence, switch at the first run of N clean.
"""
import math

import numpy as np
from scipy.stats import beta


def upper(k, n, delta):
    return 1.0 if k >= n else beta.ppf(1 - delta, k + 1, n - k)


def n_required(eps, delta=0.05, k=0, K=1):
    d = delta / K
    lo, hi = k + 1, 10
    while upper(k, hi, d) > eps:
        hi *= 2
    while lo < hi:
        mid = (lo + hi) // 2
        if upper(k, mid, d) <= eps:
            hi = mid
        else:
            lo = mid + 1
    return lo


def p_switch_fixed(p, n):
    return (1 - p) ** n


def p_switch_run(p, n, budget):
    """Probability that a run of n clean sessions appears within `budget` sessions (exact, by recursion on runs)."""
    if p == 0:
        return 1.0 if budget >= n else 0.0
    q = 1 - p
    # P(no run of length n in t trials): f[t] = f[t-1] - p * q**n * f[t-n-1], with f[t]=1 for t<n, f[n]=1-q**n
    f = np.ones(budget + 1)
    if budget >= n:
        f[n] = 1 - q ** n
        for t in range(n + 1, budget + 1):
            f[t] = f[t - 1] - p * q ** n * f[t - n - 1]
    return 1 - f[budget]


def p_switch_fixed_retried(p, n, budget):
    """The same fixed window, rerun on the same build after every failure until the budget runs out."""
    return 1 - (1 - (1 - p) ** n) ** (budget // n)


def power_table(eps, delta=0.05, ks=(0, 2, 5), ratios=(0.25, 0.5)):
    """Pass rate of a class that is better than the threshold, for windows sized with k allowed divergences."""
    from scipy.stats import binom
    rows = []
    for k in ks:
        n = n_required(eps, delta, k)
        rows.append((k, n, [binom.cdf(k, n, r * eps) for r in ratios]))
    return rows


def expected_wait_run(p, n):
    q = 1 - p
    return (1 - q ** n) / (p * q ** n)


def simulate(p, n, budget, trials, rng):
    fixed = run = 0
    for _ in range(trials):  # sanity check only; the exact formulas above are the result
        x = rng.random(budget) < p
        fixed += not x[:n].any()
        # run rule
        streak, ok = 0, False
        for bad in x:
            streak = 0 if bad else streak + 1
            if streak >= n:
                ok = True
                break
        run += ok
    return fixed / trials, run / trials


if __name__ == "__main__":
    eps, delta = 0.001, 0.05
    print("N required (eps, delta=5%, k=0,1,2; K=1 and K=20):")
    for e in (0.01, 0.001, 0.0001):
        print(f"  eps={e:g}: k0={n_required(e)} k1={n_required(e, k=1)} k2={n_required(e, k=2)} K20={n_required(e, K=20)}")
    n = n_required(eps, delta)
    budget = 30 * n  # a month of a class that gives one window a day
    print(f"\nN={n}; budget={budget} sessions")
    print(f"expected wait for a clean run at p=2*eps: {expected_wait_run(2 * eps, n):,.0f} sessions")
    print("power: pass rate of a good class (true rate 0.25 eps, 0.5 eps):")
    for k, nk, rates in power_table(eps, delta):
        print(f"  k={k}: N={nk}  " + "  ".join(f"{r:.0%}" for r in rates))
    rng = np.random.default_rng(7)
    rows = []
    for mult in (0, 0.5, 1, 1.5, 2, 3, 5):
        p = mult * eps
        f, r = p_switch_fixed(p, n), p_switch_run(p, n, budget)
        sf, sr = simulate(p, n, budget, 400, rng) if p > 0 else (f, r)
        rows.append((mult, f, r, sf, sr))
        print(f"  p={mult:>3}×eps  fixed={f:6.1%} (sim {sf:6.1%})  fixed retried={p_switch_fixed_retried(p, n, budget):6.1%}  run-in-a-row={r:6.1%} (sim {sr:6.1%})")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    xs = np.linspace(0, 5, 101)
    fixed = [p_switch_fixed(m * eps, n) for m in xs]
    retried = [p_switch_fixed_retried(m * eps, n, budget) for m in xs]
    run = [p_switch_run(m * eps, n, budget) for m in xs]
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=200)
    ax.plot(xs, run, color="#eb6834", lw=2, label="N clean in a row, restart after each divergence")
    ax.plot(xs, retried, color="#e87ba4", lw=2, ls="--", label="fixed window, rerun on the same build after a failure")
    ax.plot(xs, fixed, color="#2a78d6", lw=2, label="fixed window, a failure is closed only by a new code version")
    ax.axvline(1, color="#8a8983", lw=1, ls="--")
    ax.text(1.04, 0.92, "threshold ε = 0.1%", color="#5f5e58", fontsize=9)
    ax.set_xlabel("true divergence rate, in multiples of the threshold ε")
    ax.set_ylabel("probability of switching within a month")
    ax.set_title(f"A broken class passes the streak: N = {n:,} sessions, a month of traffic", fontsize=11, loc="left")
    ax.set_ylim(0, 1.02)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", color="#e4e2dc", lw=0.6)
    ax.legend(frameon=False, fontsize=9, loc="center right")
    fig.tight_layout()
    fig.savefig("run_vs_window.png")
    print("\nchart: run_vs_window.png")
