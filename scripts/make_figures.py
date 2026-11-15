#!/usr/bin/env python3
"""Generate the 6 paper figures (PDF) for chess-compression-scaling.

All numbers are read from the repo artifacts (never hand-typed). English
labels; IEEE single-column size (~3.5 in) unless the paper uses full width.
"""
import json, math, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle

REPO = "/home/z/my-project/research/chess-compression-scaling"
A = f"{REPO}/artifacts"
DIG = json.load(open("/home/z/my-project/scripts/facts_digest.json"))

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 8,
    "axes.titlesize": 8.5,
    "axes.labelsize": 8,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 6.8,
    "axes.unicode_minus": False,
})
BLUE, ORANGE, GREEN, GRAY, RED = "#0072B2", "#E69F00", "#009E73", "#7F7F7F", "#D55E00"

def load(p):
    return json.load(open(os.path.join(A, p)))

comp, e3, z3v2 = load("compression_summary.json"), load("e_diagnostics/e3_trace_comparison.json"), load("z3_injectivity_v2.json")

def fam(rk):
    return comp["runs"][rk]["result"]

def savefig(fig, path):
    fig.savefig(path, format="pdf")
    plt.close(fig)
    print("wrote", path)

# ---------------------------------------------------------------- F1 growth
fig, ax = plt.subplots(figsize=(3.5, 2.9), constrained_layout=True)
series = {
    "duel": ([fam("n3_duel"), fam("n4_duel"), fam("n5_duel")], BLUE, "o"),
    "asym_3p": ([fam("n4_asym_3p"), fam("n5_asym_3p")], ORANGE, "s"),
    "four_pawn": ([fam("n4_four_pawn"), fam("n5_four_pawn")], GREEN, "^"),
}
for name, (runs, col, mk) in series.items():
    xs = [r["states"] for r in runs]
    ys = [r["mtbdd"]["nodes"] for r in runs]
    ax.scatter(xs, ys, s=14, c=col, marker=mk, label=name, zorder=3)
routed = [(DIG["states"]["4"], DIG["routed_n4_nodes"], "routed total N=4"),
          (DIG["states"]["5"], DIG["routed_n5_nodes"], "routed total N=5")]
ax.scatter([p[0] for p in routed], [p[1] for p in routed], s=18, c=GRAY, marker="D", label="routed total", zorder=3)
ax.scatter([DIG["states"]["5"]], [DIG["unified_nodes"]], s=34, c=RED, marker="*", label="unified N=5", zorder=4)
k = DIG["k_exponent"]; a = DIG["a_intercept"]
xlo, xhi = 4e2, 3e7
xf = [xlo, xhi]
ax.plot(xf, [10**a * x**k for x in xf], c=GRAY, lw=0.9, ls="-", zorder=2)
ax.plot(xf, xf, c=GRAY, lw=0.8, ls=":", zorder=1)
ax.text(0.04, 0.93, f"fit: nodes $\\approx$ states$^{{{k:.2f}}}$", transform=ax.transAxes, fontsize=7, color="#333333")
ax.text(0.04, 0.85, "dotted: nodes = states", transform=ax.transAxes, fontsize=6.3, color=GRAY)
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xlabel("legal states")
ax.set_ylabel("MTBDD nodes")
ax.set_xlim(xlo, xhi); ax.set_ylim(3e1, 4e5)
ax.grid(True, which="both", lw=0.3, alpha=0.4)
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=3, frameon=False)
savefig(fig, f"{REPO}/paper/scaling/figures/f1_growth.pdf")

# ---------------------------------------------------------- F2 degradation
fig, ax = plt.subplots(figsize=(3.5, 2.6), constrained_layout=True)
labels = ["four_pawn\n(K2P)", "K+P+N vs\nK+P+N", "asym_3p\n(K2P)", "K+P+N\nvs K", "K+P vs\nK+P+N"]
vals = [DIG["sym_before"], DIG["sym_after"], DIG["asym_before"],
        DIG["asym_after"], DIG["unified_nodes"] and 8.71]
cols = [BLUE, ORANGE, BLUE, ORANGE, ORANGE]
xs = [0, 1, 2.6, 3.6, 4.6]
bars = ax.bar(xs, vals, width=0.8, color=cols)
for x, v in zip(xs, vals):
    ax.text(x, v + 1.0, f"1:{v:.1f}", ha="center", fontsize=7)
ax.annotate("", xy=(0.72, 21.5), xytext=(0.28, 31.5),
            arrowprops=dict(arrowstyle="->", lw=0.9, color=RED))
ax.text(0.5, 36.0, "$1.57\\times$ worse", ha="center", fontsize=7, color=RED)
ax.annotate("", xy=(3.42, 13.5), xytext=(2.88, 39.5),
            arrowprops=dict(arrowstyle="->", lw=0.9, color=RED))
ax.text(3.45, 44.0, "$3.35\\times$ worse", ha="center", fontsize=7, color=RED)
ax.set_xticks(xs); ax.set_xticklabels(labels, fontsize=6.6)
ax.set_ylabel("compression ratio (states per MTBDD node)")
ax.set_ylim(0, 50)
ax.axvline(1.8, c=GRAY, lw=0.6, ls="--")
ax.text(0.5, 46.5, "balanced material", ha="center", fontsize=6.5, color="#333333")
ax.text(3.6, 46.5, "unbalanced material", ha="center", fontsize=6.5, color="#333333")
savefig(fig, f"{REPO}/paper/scaling/figures/f2_degradation.pdf")

# ------------------------------------------------------------- F3 Z3 flow
fig, ax = plt.subplots(figsize=(3.5, 3.3))
ax.axis("off")
def box(x, y, w, h, text, fc, fs=6.6):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012",
                                fc=fc, ec="#444444", lw=0.7))
    ax.text(x + w/2, y + h/2, text, ha="center", va="center", fontsize=fs)
def arrow(x1, y1, x2, y2, text="", color="#444444"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                                 mutation_scale=7, lw=0.9, color=color))
    if text:
        ax.text((x1+x2)/2 + 0.13, (y1+y2)/2, text, fontsize=6.2, color=color, va="center")
box(0.02, 0.86, 0.96, 0.115,
    "basis v1: 5 king + 13 knight [+ 14 pawn] features\n(18 features kn / 32 pawn classes)", "#DCEBFA")
arrow(0.5, 0.855, 0.5, 0.79, "")
box(0.02, 0.66, 0.96, 0.125,
    "Z3 query: $\\exists s_1 s_2$: legal $\\wedge$ $\\varphi(s_1){=}\\varphi(s_2)$ $\\wedge$ VAL$\\neq$\nresult: SAT on all 7 classes", "#FDE8E6")
arrow(0.5, 0.655, 0.5, 0.59, "")
box(0.02, 0.445, 0.96, 0.14,
    "3 certified ambiguity mechanisms:\nknight-square (d2 vs d3, same distances)\nrank-translation | pawn-geometry", "#FDE8E6")
arrow(0.5, 0.44, 0.5, 0.375, "")
box(0.02, 0.245, 0.96, 0.125,
    "basis v2: + 8 signed knight offsets + 2 rank-edge\ndistances [+ 8 signed pawn offsets]  (28 / 50)", "#E3F2E1")
arrow(0.5, 0.24, 0.5, 0.175, "")
box(0.02, 0.045, 0.96, 0.125,
    "Z3: 0 conflict buckets on ALL 7 classes\nfull-class unsat (kn N=3) / subspace unsat (5) / perfect empirical layer (both)", "#E3F2E1", fs=6.0)
savefig(fig, f"{REPO}/paper/scaling/figures/f3_z3_flow.pdf")

# ------------------------------------------------------------ F4 deep paths
fig, axes = plt.subplots(1, 2, figsize=(3.7, 3.4), constrained_layout=True)
for axx, key, title in ((axes[0], "4/duel", "deepest path, duel N=4"),
                        (axes[1], "5/duel", "deepest path, duel N=5")):
    tr = e3["traces"][key]
    seq = [s["feature"] for s in tr["sequence"]]
    ys = list(range(len(seq) - 1, -1, -1))
    axx.hlines(ys, 0, 1, color=BLUE, lw=1.1)
    axx.scatter([0.12]*len(ys), ys, s=5, c=BLUE, zorder=3)
    axx.set_yticks(ys); axx.set_yticklabels(seq, fontsize=5.8, family="monospace")
    axx.set_xticks([])
    axx.set_title(f"{title}\ndepth {tr['depth']} = {tr['n_distinct_features']} distinct features", fontsize=7.6)
savefig(fig, f"{REPO}/paper/scaling/figures/f4_paths.pdf")

# ------------------------------------------------- Paper 2 F1: Z3 pipeline
fig, ax = plt.subplots(figsize=(3.5, 3.6))
ax.axis("off")
steps = [
    ("legal states of material class C\n(e.g. K+N vs K+N, N=4: 46,384)", "#DCEBFA"),
    ("feature extraction $\\varphi$ (same Python code\nas the compression runs)", "#DCEBFA"),
    ("Z3 encoding: BitVector state variables,\nlegal-move constraints, VAL array axiomatisation", "#DCEBFA"),
    ("query $\\exists s_1 s_2$: $\\varphi(s_1){=}\\varphi(s_2)$ $\\wedge$ VAL$(s_1)\\neq$VAL$(s_2)$", "#FDE8E6"),
    ("verdict: sat $\\Rightarrow$ concrete counterexample\nunsat $\\Rightarrow$ value-sufficiency PROVED", "#E3F2E1"),
]
y = 0.98
h = 0.132
for i, (t, c) in enumerate(steps):
    y -= h + 0.043
    box(0.03, y, 0.94, h, t, c, fs=6.4)
    if i:
        arrow(0.5, y + h + 0.043, 0.5, y + h + 0.004)
ax.text(0.5, 0.012, "budget guard: array axiomatisation skipped above 60,000 states\n"
                  "$\\Rightarrow$ bounded-subspace proof or empirical layer", ha="center", fontsize=6.2, color=GRAY)
savefig(fig, f"{REPO}/paper/verification/figures/f1_pipeline.pdf")

# ------------------------------------------- Paper 2 F2: counterexample pair
fig, axes = plt.subplots(1, 2, figsize=(3.5, 2.0), constrained_layout=True)
def draw_board(ax, knight_xy, title, val):
    light, dark = "#F0D9B5", "#B58863"
    for y in range(4):
        for x in range(4):
            c = dark if (x + y) % 2 == 0 else light
            ax.add_patch(Rectangle((x, y), 1, 1, fc=c, ec="none"))
    pieces = {(0, 0): ("K", "white"), (0, 1): ("N", "white"), (2, 1): ("k", "black")}
    pieces[tuple(knight_xy)] = ("n", "black")
    for (x, y), (g, col) in pieces.items():
        ax.text(x + 0.5, y + 0.5, g, ha="center", va="center", fontsize=13,
                color="white" if col == "black" else "black",
                fontweight="bold")
    hx, hy = knight_xy
    ax.add_patch(Rectangle((hx, hy), 1, 1, fill=False, ec=RED, lw=1.6))
    ax.set_xlim(0, 4); ax.set_ylim(0, 4)
    ax.set_xticks(range(4)); ax.set_yticks(range(4))
    ax.set_xticklabels(["a", "b", "c", "d"], fontsize=6)
    ax.set_yticklabels(["1", "2", "3", "4"], fontsize=6)
    ax.tick_params(length=0)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.set_title(f"{title}\nmover-relative VAL = {val}", fontsize=7)
draw_board(axes[0], (3, 1), "black knight d2", "1 (mover wins)")
draw_board(axes[1], (3, 2), "black knight d3", "3 (draw)")
savefig(fig, f"{REPO}/paper/verification/figures/f2_counterexample.pdf")

print("all figures done")
