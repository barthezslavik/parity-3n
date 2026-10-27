"""English figures for the parity article: cover, regression classes, days to discovery, the retry trap.

    uv run --with numpy --with scipy --with matplotlib figures.py <out_dir>
"""
import csv, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from parity import n_required, p_switch_fixed, p_switch_fixed_retried, p_switch_run

out = sys.argv[1]
INK, MUTED, GRID = "#1d1d1b", "#6f6e68", "#e4e2dc"
GREEN, RED, BLUE, ORANGE, PINK = "#1baf7a", "#e34948", "#2a78d6", "#eb6834", "#e87ba4"
plt.rcParams.update({"font.size": 12, "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED})

def clean(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

# cover
fig = plt.figure(figsize=(16, 9), dpi=100)
fig.patch.set_facecolor("#fcfcfb")
fig.text(0.27, 0.58, "CI", ha="center", fontsize=40, color=MUTED)
fig.text(0.27, 0.40, "100% ✓", ha="center", fontsize=110, color=GREEN, weight="bold")
fig.text(0.515, 0.47, "→", ha="center", fontsize=90, color=MUTED)
fig.text(0.73, 0.58, "after merge", ha="center", fontsize=40, color=MUTED)
fig.text(0.73, 0.40, "18", ha="center", fontsize=110, color=RED, weight="bold")
fig.text(0.73, 0.32, "regressions · 11 found by users", ha="center", fontsize=30, color=INK)
fig.text(0.5, 0.12, "Bun's agent-written Zig → Rust port", ha="center", fontsize=30, color=MUTED)
fig.savefig(os.path.join(out, "cover.png")); plt.close(fig)

# classes
rows = [("Ported, behaves differently", 12), ("Limits, state, timing, load", 3), ("Intentional change nobody recorded", 2), ("Input not in the tests", 1)]
fig, ax = plt.subplots(figsize=(10, 4.2), dpi=180)
ax.barh([r[0] for r in rows][::-1], [r[1] for r in rows][::-1], color=[GRID, GRID, GRID, BLUE], height=0.6)
for i, (_, v) in enumerate(rows[::-1]):
    ax.text(v + 0.2, i, str(v), va="center", color=INK, fontsize=13)
ax.set_title("Why 100% green tests missed 18 regressions in Bun's Rust port", loc="left", fontsize=14, color=INK)
ax.set_xticks([]); clean(ax); ax.spines["bottom"].set_visible(False)
fig.tight_layout(); fig.savefig(os.path.join(out, "classes.png")); plt.close(fig)

# days to discovery
data = list(csv.DictReader(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "bun_rust_port_regressions.csv"))))
days = sorted(float(r["days_from_merge"]) for r in data)
users = [float(r["days_from_merge"]) for r in data if r["found_by"].startswith("user")]
others = [float(r["days_from_merge"]) for r in data if not r["found_by"].startswith("user")]
fig, ax = plt.subplots(figsize=(10, 3.4), dpi=180)
ax.scatter(users, np.full(len(users), 0.15), s=90, color=RED, label="found by users", zorder=3)
ax.scatter(others, np.full(len(others), -0.15), s=90, color=MUTED, label="found by maintainers, bots, CI", zorder=3)
med = float(np.median(days))
ax.axvline(med, color=INK, lw=1, ls="--"); ax.text(med + 0.8, 0.42, f"median {med:.1f} days", color=INK)
ax.axvline(34, color=ORANGE, lw=1.5); ax.text(34.8, -0.45, "Rust build ships inside Claude Code (Jun 17)", color=ORANGE)
ax.set_ylim(-0.6, 0.6); ax.set_yticks([]); ax.set_xlabel("days from merge (May 14) to discovery")
ax.set_title("When the 18 regressions surfaced", loc="left", fontsize=14, color=INK)
ax.legend(frameon=False, loc="upper right", fontsize=10); clean(ax); ax.spines["left"].set_visible(False)
fig.tight_layout(); fig.savefig(os.path.join(out, "days.png")); plt.close(fig)

# retry trap, direct labels
eps = 0.001; n = n_required(eps); budget = 30 * n
xs = np.linspace(0, 4, 161)
curves = [("N clean in a row", ORANGE, [p_switch_run(m * eps, n, budget) for m in xs]),
          ("rerun the window on the same build", PINK, [p_switch_fixed_retried(m * eps, n, budget) for m in xs]),
          ("failed window closed only by a fix", BLUE, [p_switch_fixed(m * eps, n) for m in xs])]
fig, ax = plt.subplots(figsize=(10, 5), dpi=180)
for name, col, ys in curves:
    ax.plot(xs, ys, color=col, lw=2.5)
for label, col, y0, yt in [("N clean in a row: 36% per month", ORANGE, p_switch_run(2 * eps, n, budget), 0.80),
                           ("rerun the window on the same build: 7% per month", PINK, p_switch_fixed_retried(2 * eps, n, budget), 0.66),
                           ("failed window closed only by a fix: 0.25% per window", BLUE, p_switch_fixed(2 * eps, n), 0.52)]:
    ax.annotate(label, xy=(2, y0), xytext=(2.35, yt), color=col, fontsize=12,
                arrowprops=dict(arrowstyle="-", color=col, lw=0.8, relpos=(0, 0.5), shrinkA=4, shrinkB=4))
ax.scatter([2, 2, 2], [p_switch_run(2 * eps, n, budget), p_switch_fixed_retried(2 * eps, n, budget), p_switch_fixed(2 * eps, n)],
           color=[ORANGE, PINK, BLUE], s=30, zorder=4)
ax.axvline(1, color=MUTED, lw=1, ls=":"); ax.text(0.97, 0.62, "threshold", color=MUTED, ha="right")
ax.axvline(2, color=GRID, lw=1)
ax.set_xlabel("true divergence rate, × threshold (0.1%)"); ax.set_ylabel("chance to switch")
ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}"); ax.set_ylim(0, 1.02)
ax.set_title("'N clean in a row' switches a class 2× worse than threshold 36% of the time", loc="left", fontsize=13, color=INK)
clean(ax); ax.grid(axis="y", color=GRID, lw=0.6)
fig.tight_layout(); fig.savefig(os.path.join(out, "retry_trap.png")); plt.close(fig)
print("ok")
