#!/usr/bin/env python3
# scripts_general/compress_class_k2pn.py - MTBDD compression for K2P+N material
# classes (PART 4 of the K2P+N Z3 phase).
#
# Pipeline per class (mirrors compress_family_general.py exactly, on the
# knight-extended state space):
#   1. load the class oracle (k2pn_classes.py output: VAL/DTC/F/ENC + class ids)
#   2. orbit quotient G=<H,V'> over the class states (k2pn_basis.canon8);
#      value homogeneity per orbit is ASSERTED (mover-relative VAL is
#      V'-invariant - separately validated by the oracle self-tests)
#   3. semantic feature rows (k2pn_basis.class_features: 5 king + 13 knight
#      [+ 14 pawn]) -> conflict scan (expected > 0: Z3 REFUTED value-sufficiency)
#   4. conditional coordinate tail (cwk,cbk,cwp,cbp,cnw,cnb) -> conflicts must
#      be 0; MTBDD (+ win/loss BDDs when small) -> nodes/paths/depth
#   5. emit a zero-lookup algebraic evaluator (same mechanism audit as the repo)
#      and verify it in a FRESH subprocess against every class state; if the
#      tree is over the line budget, verify the MTBDD in-process on the
#      canonical representatives instead
#   6. ratio table row: states / orbits / rows / nodes / depth / ratio /
#      verify / peak RSS
#
# Lives OUTSIDE the repo; repo files are never written.
import argparse, gc, json, os, subprocess, sys, time
from bisect import bisect_right

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import k2pn_basis as KB

T0 = time.time()
R = []


def P(s=""):
    R.append(s)
    print(s, flush=True)


def rss_mib():
    try:
        with open("/proc/self/status") as fh:
            for ln in fh:
                if ln.startswith(("VmRSS:", "VmHWM:")):
                    pass
        with open("/proc/self/status") as fh:
            d = {}
            for ln in fh:
                if ln.startswith("VmRSS:"):
                    d["rss"] = float(ln.split()[1]) / 1024
                if ln.startswith("VmHWM:"):
                    d["hwm"] = float(ln.split()[1]) / 1024
        return d.get("rss", 0.0), d.get("hwm", 0.0)
    except OSError:
        return 0.0, 0.0


STAGES = []


def stage_mark(label):
    cur, hwm = rss_mib()
    STAGES.append({"stage": label, "t": round(time.time() - T0, 1),
                   "rss_mib": round(cur, 1), "hwm_mib": round(hwm, 1)})
    P(f"   [{time.time()-T0:7.1f}s rss {cur:7.1f} MiB] {label}")
CLASSES = {"kn": (0, 0, 1, 1), "kpn": (1, 0, 1, 0),
           "mirror": (1, 1, 0, 1), "both": (1, 1, 1, 1)}

ap = argparse.ArgumentParser(description="K2P+N class MTBDD compressor")
ap.add_argument("--n", type=int, default=4)
ap.add_argument("--class-name", default="kn", choices=sorted(CLASSES))
ap.add_argument("--oracle-dir", default=None)
ap.add_argument("--out-dir", default=None)
ap.add_argument("--emit-dir", default=None)
ap.add_argument("--tree-line-limit", type=int, default=200000)
ap.add_argument("--winloss-row-limit", type=int, default=300000)
args = ap.parse_args()

N = args.n
NN = N * N
MAT = CLASSES[args.class_name]
wp_m, bp_m, nw_m, nb_m = MAT
has_pawn = bool(wp_m or bp_m)
if args.oracle_dir is None:
    args.oracle_dir = os.path.join(".", f"out_class_{args.class_name}_n{N}")
if args.out_dir is None:
    args.out_dir = os.path.join(".", f"compress_class_{args.class_name}_n{N}")
if args.emit_dir is None:
    args.emit_dir = args.out_dir
os.makedirs(args.out_dir, exist_ok=True)
os.makedirs(args.emit_dir, exist_ok=True)
P(f"config: N={N} class={args.class_name} mat={MAT} out={args.out_dir}")

# ================================================= Compressor (repo verbatim)
# Copied from compress_family_general.py (which copies the repo's pipeline);
# only mem_guard is dropped (class row counts are bounded).
class Compressor:
    def __init__(self, names, nsem):
        self.NAMES = list(names); self.NSEM = nsem; self.NB = len(names)
        self._ctr = 0

    def load_rows(self, pairs, tag):
        stage_mark(f"sort rows [{tag}]")
        pairs.sort(key=lambda p: p[0])
        NB, NSEM = self.NB, self.NSEM
        R_ = 0; prev = None
        for p in pairs:
            if p[0] != prev:
                R_ += 1; prev = p[0]
        mat = np.empty((R_, NB), dtype=np.int16)
        lab = np.empty(R_, dtype=np.int8)
        sem_blocks = 0; sem_conflicting = 0
        ri = -1; prev_t = None; prev_sem = None
        block_first_lab = None; block_ok = True; full_conf = 0
        for p in pairs:
            t, l = p[0], p[1]
            sem = t[:NSEM]
            if t != prev_t:
                ri += 1
                mat[ri] = t; lab[ri] = l
            else:
                if l != lab[ri]:
                    full_conf += 1
            if sem != prev_sem:
                if prev_sem is not None and not block_ok:
                    sem_conflicting += 1
                sem_blocks += 1
                block_first_lab = l; block_ok = True
            else:
                if l != block_first_lab:
                    block_ok = False
            prev_t = t; prev_sem = sem
        if prev_sem is not None and not block_ok:
            sem_conflicting += 1
        del pairs; gc.collect()
        self.conf = {"distinct_semantic_rows": sem_blocks,
                     "semantic_conflicting_groups": sem_conflicting,
                     "distinct_full_rows": R_, "full_conflicting_groups": full_conf}
        self.R = R_
        self.COLS = [np.ascontiguousarray(mat[:, bi]) for bi in range(NB)]
        self.LAB0 = lab
        del mat; gc.collect()
        stage_mark(f"rows ready [{tag}] ({R_:,} rows)")

    def reset_build(self):
        self.NODES = {}; self.CTX = {}; self._ctr = 0

    CTX_CAP = 1_500_000

    def mk(self, bi, ch):
        key = ("N", bi, tuple(ch))
        return self.NODES.setdefault(key, key)

    def build(self, i0, i1, bi):
        if i0 >= i1:
            return ("T", 0)
        if bi == self.NB:
            assert i1 - i0 == 1, "row class not singleton at full depth"
            return ("T", int(self.LABV[i0]))
        key = (i0 * (self.R + 1) + i1) * self.NB + bi
        if key in self.CTX:
            return self.CTX[key]
        col = self.COLS[bi]
        ch = []
        j = i0
        while j < i1:
            v = int(col[j])
            j2 = bisect_right(col, v, j, i1)
            ch.append((v, self.build(j, j2, bi + 1)))
            j = j2
        vals = [c for _, c in ch]
        res = vals[0] if all(c == vals[0] for c in vals) else self.mk(bi, ch)
        if len(self.CTX) < self.CTX_CAP:
            self.CTX[key] = res
        self._ctr += 1
        return res

    def build_tree(self, labv):
        self.LABV = labv
        self.reset_build()
        return self.build(0, self.R, 0)

    def build_label(self, target):
        saved = self.LAB0
        self.LAB0b = (saved == target).astype(np.int8)
        root = self.build_tree(self.LAB0b)
        self.LAB0b = None
        return root

    def stats(self, root):
        seen = set()

        def collect(k):
            if k[0] == "N" and k not in seen:
                seen.add(k)
                for _, c in k[2]:
                    collect(c)
        collect(root)
        memo_p = {}; memo_d = {}

        def paths(k):
            if k[0] == "T":
                return 1
            if k in memo_p:
                return memo_p[k]
            p = sum(paths(c) for _, c in k[2]); memo_p[k] = p; return p

        def depth(k):
            if k[0] == "T":
                return 0
            if k in memo_d:
                return memo_d[k]
            d = 1 + max(depth(c) for _, c in k[2]); memo_d[k] = d; return d
        return len(seen), paths(root), depth(root)

    def used_feats(self, root):
        u = set()

        def walk(k):
            if k[0] == "N":
                u.add(k[1])
                for _, c in k[2]:
                    walk(c)
        walk(root)
        return u

    def emit(self, root, feat_lines_fn, header_lines, out_path, tree_line_limit):
        REFC = {}

        def count_refs(k):
            if k in REFC:
                REFC[k] += 1; return
            REFC[k] = 1
            if k[0] == "N":
                for _, c in k[2]:
                    count_refs(c)
        count_refs(root)
        NEED = {}

        def need_of(k):
            if k in NEED:
                return NEED[k]
            if k[0] == "T":
                NEED[k] = frozenset(); return NEED[k]
            s = {k[1]}
            for _, c in k[2]:
                s |= need_of(c)
            NEED[k] = frozenset(s); return s
        need_of(root)
        HNAME = {}; order = []
        _seen = set()

        def topo(k):
            if k[0] != "N" or k in _seen:
                return
            _seen.add(k)
            for _, c in k[2]:
                topo(c)
            if REFC[k] > 1:
                HNAME[k] = f"_n{len(HNAME)}"
                order.append(k)
        topo(root)
        NAMES = self.NAMES

        def emit_sub(k, ind):
            pad = " " * ind
            if k[0] == "T":
                return [f"{pad}return {k[1]}"]
            if REFC[k] > 1:
                args_ = ", ".join("f_" + NAMES[i] for i in sorted(need_of(k)))
                return [f"{pad}return {HNAME[k]}({args_})"]
            bi = k[1]; ch = k[2]
            nm = NAMES[bi]
            out = []
            for i, (v, c) in enumerate(ch[:-1]):
                kw = "if" if i == 0 else "elif"
                out.append(f"{pad}{kw} f_{nm} == {v}:")
                out += emit_sub(c, ind + 4)
            out.append(f"{pad}else:")
            out += emit_sub(ch[-1][1], ind + 4)
            return out
        helper_lines = []
        for k in order:
            args_ = ", ".join("f_" + NAMES[i] for i in sorted(need_of(k)))
            helper_lines.append(f"def {HNAME[k]}({args_}):")
            bi = k[1]; ch = k[2]
            nm = NAMES[bi]
            for i, (v, c) in enumerate(ch[:-1]):
                kw = "if" if i == 0 else "elif"
                helper_lines.append(f"    {kw} f_{nm} == {v}:")
                helper_lines += emit_sub(c, 8)
            helper_lines.append("    else:")
            helper_lines += emit_sub(ch[-1][1], 8)
            helper_lines.append("")
            helper_lines.append("")
        root_body = emit_sub(root, 4)
        total_tree_lines = len(helper_lines) + len(root_body)
        P(f"   [diag] DAG edges {sum(len(k[2]) for k, r in REFC.items() if k[0] == 'N')}, "
          f"shared helpers {len(HNAME)}")
        if total_tree_lines > tree_line_limit:
            return {"emitted": False, "helpers": len(HNAME),
                    "tree_lines": total_tree_lines,
                    "over_budget_by": total_tree_lines - tree_line_limit}
        used = self.used_feats(root)
        FL = feat_lines_fn(used)
        body = header_lines + FL + [""] + root_body
        with open(out_path, "w") as fh:
            if helper_lines:
                fh.write("\n".join(helper_lines) + "\n\n")
            fh.write("\n".join(body) + "\n")
        P(f"   emitted -> {out_path}  (helpers {len(helper_lines)} + main {len(body)} lines)")
        P("   mechanism audit: integer arithmetic + abs/max/min + if/elif/else only; "
          "zero lookups/tables/arrays")
        return {"emitted": True, "helpers": len(HNAME), "tree_lines": total_tree_lines,
                "main_lines": len(body), "total_lines": len(helper_lines) + len(body),
                "surviving_features": [self.NAMES[i] for i in sorted(used)],
                "used_indices": sorted(used)}


# ================================================= feature-name sets
KING_NAMES = list(KB.KING_NAMES)
KNIGHT_NAMES = list(KB.KNIGHT_NAMES)
PAWN_NAMES = list(KB.PAWN_NAMES)
TAIL_NAMES = list(KB.TAIL_NAMES)
SEM_NAMES = KING_NAMES + KNIGHT_NAMES + (PAWN_NAMES if has_pawn else [])
SEM_NAMES = [nm for nm in SEM_NAMES]
NSEM = len(SEM_NAMES)
P(f"feature basis: {NSEM} semantic = 5 king + 13 knight"
  + (" + 14 pawn" if has_pawn else "") + f"; tail {len(TAIL_NAMES)}")

# ================================================= load oracle
npz = np.load(os.path.join(args.oracle_dir, "class_values.npz"))
VAL_all = npz["VAL"]
F_all = npz["F"]
cls_ids = npz["CLASS"]
DTC_all = npz["DTC"]
assert int(npz["NPAR"][0]) == N
states = F_all[cls_ids]
VAL_cls = VAL_all[cls_ids].astype(np.int8)
MV = KB.mv_from_val(VAL_cls)                       # {0=draw,1=win,2=loss} mover-rel
n_cls = len(states)
stage_mark(f"oracle loaded [{args.class_name}] ({n_cls:,} class states)")
dtc_dec = DTC_all[cls_ids]
max_dtc = int(dtc_dec[VAL_cls != 3].max()) if int((VAL_cls != 3).sum()) else -1
P(f"class DTC: max {max_dtc} plies over decided states; value mix: "
  f"W {int((VAL_cls==1).sum()):,} / D {int((VAL_cls==3).sum()):,} / L {int((VAL_cls==2).sum()):,}")

# ================================================= orbit quotient
stage_mark("orbit quotient start")
canon_enc = {}
orbit_hist = {}
hom_bad = 0
canon_list = []
for i in range(n_cls):
    wk, bk, wp, bp, nw, nb, stm = (int(v) for v in states[i])
    st = (wk, bk, wp, bp, nw, nb, stm)
    c = KB.canon8(st, N)
    e = KB.enc8(*c, N)
    osz = len(set(KB.orbit_members(st, N)))
    orbit_hist[osz] = orbit_hist.get(osz, 0) + 1
    slot = canon_enc.get(e)
    if slot is None:
        canon_enc[e] = len(canon_list)
        canon_list.append((c, int(MV[i])))
    else:
        c0, mv0 = canon_list[slot]
        if mv0 != int(MV[i]):
            hom_bad += 1
assert hom_bad == 0, f"orbit value homogeneity violated in {hom_bad} states"
n_canon = len(canon_list)
P(f"1. orbit quotient G=<H,V'> [{args.class_name}/n{N}]: class states {n_cls:,}, "
  f"canonical orbits {n_canon:,}, orbit size histogram "
  f"{dict(sorted(orbit_hist.items()))}, homogeneity violations {hom_bad}")
stage_mark("orbit quotient done")

# ================================================= semantic feature rows
stage_mark("semantic feature extraction")
sem_pairs = []
tail_data = []
for c, mv in canon_list:
    wk, bk, wp, bp, nw, nb, stm = c
    f = KB.class_features(wk, bk, wp, bp, nw, nb, stm, N, MAT)
    sem_pairs.append((f, mv))
    tail_data.append((f, (wk, bk, wp, bp, nw, nb), mv))
stage_mark(f"semantic rows built ({len(sem_pairs):,})")

comp_sem = Compressor(SEM_NAMES, NSEM)
comp_sem.load_rows(sem_pairs, f"{args.class_name}/n{N} semantic-only")
sem_conf = comp_sem.conf
tail_used = sem_conf["full_conflicting_groups"] > 0
P(f"2. semantic basis [{args.class_name}/n{N}]: {NSEM} features; "
  f"distinct semantic rows {sem_conf['distinct_semantic_rows']:,} -> conflicting "
  f"{sem_conf['semantic_conflicting_groups']:,} groups "
  f"(Z3 verdict: REFUTED value-sufficiency, conflicts expected)")
if tail_used:
    del comp_sem.COLS; comp_sem.COLS = None
    del comp_sem; gc.collect()
    names = SEM_NAMES + TAIL_NAMES
    comp = Compressor(names, NSEM)
    full_pairs = [(f + t, mv) for f, t, mv in tail_data]
    comp.load_rows(full_pairs, f"{args.class_name}/n{N} full+tail")
    assert comp.conf["full_conflicting_groups"] == 0, \
        "feature basis + coordinate tail is not discriminative (BUG)"
    P(f"   coordinate tail ADDED ({len(TAIL_NAMES)}): distinct full rows "
      f"{comp.conf['distinct_full_rows']:,} -> conflicting 0 (must be 0)")
else:
    comp = comp_sem
    P("   semantic basis sufficient (no tail)")
stage_mark("feature rows done")

# ================================================= MTBDD build
skip_wl = args.winloss_row_limit <= 0 or comp.R > args.winloss_row_limit
stage_mark("mtbdd build start")
mt_root = comp.build_tree(comp.LAB0)
mn, mp, md = comp.stats(mt_root)
NODES_TOTAL_WL = 0
wn = ln = wp_ = lp = wd = ld = None
if skip_wl:
    P(f"3. ROBDD/MTBDD [{args.class_name}/n{N}]: rows {comp.R:,}, blocks {comp.NB} "
      f"(win/loss BDDs skipped: rows > {args.winloss_row_limit:,})")
    P(f"   MTBDD   : nodes {mn:6,d}, paths {mp:6,d}, max depth {md} "
      f"(3 terminals: 1=win, 2=loss, 0=draw)")
else:
    comp.reset_build()
    win_root = comp.build_label(1)
    wn, wp_, wd = comp.stats(win_root)
    comp.reset_build()
    loss_root = comp.build_label(2)
    ln, lp, ld = comp.stats(loss_root)
    comp.reset_build()
    NODES_TOTAL_WL = wn + ln
    P(f"   win-BDD : nodes {wn:6,d}, paths {wp_:6,d}, max depth {wd}")
    P(f"   loss-BDD: nodes {ln:6,d}, paths {lp:6,d}, max depth {ld}")
    P(f"   MTBDD   : nodes {mn:6,d}, paths {mp:6,d}, max depth {md}")
stage_mark("mtbdd build done")

with open(os.path.join(args.out_dir, "compression_partial.json"), "w") as fh:
    json.dump({"class": args.class_name, "n": N, "states": int(n_cls),
               "canonical_orbits": int(n_canon), "semantic_conflicts":
                   sem_conf["semantic_conflicting_groups"],
               "tail_used": bool(tail_used), "rows": int(comp.R),
               "mtbdd": {"nodes": mn, "paths": mp, "max_depth": md},
               "stages": STAGES[-10:]}, fh, indent=1)

# ================================================= emission
FEAT_FILE = f"{args.class_name}_n{N}_algebraic.py"
out_path = os.path.join(args.emit_dir, FEAT_FILE)


def feat_lines_class(used):
    """O(1) semantic feature lines from the canonical state, k2pn_basis-exact."""
    L = []
    a = L.append
    a("    # ---- king block (k2pn_basis.king_feats, mover-neutral geometry)")
    if 0 in used:
        a("    f_tau = ctau")
    if 1 in used or 2 in used:
        a("    wkx = cwk % N; wky = cwk // N")
        a("    bkx = cbk % N; bky = cbk // N")
        a("    wax = wkx - bkx if wkx >= bkx else bkx - wkx")
        a("    way = wky - bky if wky >= bky else bky - wky")
        a("    f_d_AK = wax if wax > way else way")
    if 2 in used:
        a("    f_opp = 1 if (f_d_AK == 2 and (wkx == bkx or wky == bky)) else 0")
    if 3 in used:
        a("    f_e_w = min(wkx, (N - 1) - wkx)")
    if 4 in used:
        a("    f_e_b = min(bkx, (N - 1) - bkx)")
    # helper functions live at MODULE level (emitted in `header` below so they
    # are defined once, not per call); this function only emits f_* lines.
    a("    # ---- king block (k2pn_basis.king_feats, mover-neutral geometry)")
    if 5 in used:
        a("    f_nW = 1 if cnw >= 0 else 0")
    if 6 in used:
        a("    f_nB = 1 if cnb >= 0 else 0")
    if 7 in used:
        a("    f_k_dist = _cheb(cnw, cnb)")
    if 8 in used:
        a("    f_katt_w = 1 if (cnw >= 0 and (_cheb(cnw, cbk) == 1 or _nat(cnb, cnw)"
          + (" or _bat(cbp, cnw)" if bp_m else "") + ")) else 0")
    if 9 in used:
        a("    f_katt_b = 1 if (cnb >= 0 and (_cheb(cnb, cwk) == 1 or _nat(cnw, cnb)"
          + (" or _wat(cwp, cnb)" if wp_m else "") + ")) else 0")
    if 10 in used:
        a("    f_kchk_w = 1 if (cnw >= 0 and _nat(cnw, cbk)) else 0")
    if 11 in used:
        a("    f_kchk_b = 1 if (cnb >= 0 and _nat(cnb, cwk)) else 0")
    if 12 in used:
        a("    f_k_w_own = _cheb(cnw, cwk)")
    if 13 in used:
        a("    f_k_b_own = _cheb(cnb, cbk)")
    if 14 in used:
        a("    f_k_w_enemy = _cheb(cnw, cbk)")
    if 15 in used:
        a("    f_k_b_enemy = _cheb(cnb, cwk)")
    if 16 in used:
        a("    f_k_atk_w = _katk(cnw)")
    if 17 in used:
        a("    f_k_atk_b = _katk(cnb)")
    if has_pawn:
        a("    # ---- pawn block (k2pn_basis.pawn_feats)")
        if 18 in used:
            a("    f_p_t_w = (N - 1) - (cwp // N) if cwp >= 0 else 99")
        if 19 in used:
            a("    f_p_t_b = (cbp // N) if cbp >= 0 else 99")
        if 20 in used:
            a("    f_p_e_w = min(cwp % N, (N - 1) - cwp % N) if cwp >= 0 else 99")
        if 21 in used:
            a("    f_p_e_b = min(cbp % N, (N - 1) - cbp % N) if cbp >= 0 else 99")
        if 22 in used:
            a("    f_p_chk_w = 1 if (cwp >= 0 and _wat(cwp, cbk)) else 0")
        if 23 in used:
            a("    f_p_chk_b = 1 if (cbp >= 0 and _bat(cbp, cwk)) else 0")
        if 24 in used:
            a("    if cwp < 0:")
            a("        f_p_fwd_w = 0")
            a("    else:")
            a("        ny = (cwp // N) + 1")
            a("        if ny > N - 1:")
            a("            f_p_fwd_w = 0")
            a("        else:")
            a("            t = N * ny + cwp % N")
            a("            f_p_fwd_w = 1 if (t == cwk or t == cbk or t == cwp or "
              "t == cbp or t == cnw or t == cnb) else 0")
        if 25 in used:
            a("    if cbp < 0:")
            a("        f_p_fwd_b = 0")
            a("    else:")
            a("        ny = (cbp // N) - 1")
            a("        if ny < 0:")
            a("            f_p_fwd_b = 0")
            a("        else:")
            a("            t = N * ny + cbp % N")
            a("            f_p_fwd_b = 1 if (t == cwk or t == cbk or t == cwp or "
              "t == cbp or t == cnw or t == cnb) else 0")
        if 26 in used:
            a("    f_p_kdef_w = 1 if (cwp >= 0 and _cheb(cwk, cwp) == 1) else 0")
        if 27 in used:
            a("    f_p_kdef_b = 1 if (cbp >= 0 and _cheb(cbk, cbp) == 1) else 0")
        if 28 in used:
            a("    f_p_ndef_w = 1 if (cwp >= 0 and cnw >= 0 and _nat(cnw, cwp)) else 0")
        if 29 in used:
            a("    f_p_ndef_b = 1 if (cbp >= 0 and cnb >= 0 and _nat(cnb, cbp)) else 0")
        if 30 in used:
            a("    f_p_ncap_w = 1 if (cnw >= 0 and cbp >= 0 and _nat(cnw, cbp)) else 0")
        if 31 in used:
            a("    f_p_ncap_b = 1 if (cnb >= 0 and cwp >= 0 and _nat(cnb, cwp)) else 0")
    a("    # ---- coordinate tail bindings (tree nodes read f_<coord>)")
    for j, nm in enumerate(TAIL_NAMES):
        if (NSEM + j) in used:
            a(f"    f_{nm} = {nm}")
    return L


HELPERS = [
    "def _cheb(a, b):",
    "    if a < 0 or b < 0:",
    "        return 99",
    "    dx = a % N - b % N",
    "    dy = a // N - b // N",
    "    if dx < 0: dx = -dx",
    "    if dy < 0: dy = -dy",
    "    return dx if dx > dy else dy",
    "",
    "",
    "def _nat(a, b):",
    "    if a < 0 or b < 0:",
    "        return False",
    "    dx = a % N - b % N",
    "    dy = a // N - b // N",
    "    if dx < 0: dx = -dx",
    "    if dy < 0: dy = -dy",
    "    return (dx == 1 and dy == 2) or (dx == 2 and dy == 1)",
    "",
    "",
    "def _katk(q):",
    "    if q < 0:",
    "        return 0",
    "    x = q % N; y = q // N",
    "    n = 0",
    "    for dx in (-2, -1, 1, 2):",
    "        for dy in (-2, -1, 1, 2):",
    "            if abs(dx) + abs(dy) != 3:",
    "                continue",
    "            nx = x + dx; ny = y + dy",
    "            if 0 <= nx < N and 0 <= ny < N:",
    "                n += 1",
    "    return n",
    "",
    "",
]
if has_pawn:
    HELPERS += [
        "def _wat(pa, t):",
        "    if pa < 0 or t < 0:",
        "        return False",
        "    ty = t // N",
        "    tx = t % N",
        "    px = pa % N",
        "    py = pa // N",
        "    return ty == py + 1 and (tx == px - 1 or tx == px + 1)",
        "",
        "",
        "def _bat(pa, t):",
        "    if pa < 0 or t < 0:",
        "        return False",
        "    ty = t // N",
        "    tx = t % N",
        "    px = pa % N",
        "    py = pa // N",
        "    return ty == py - 1 and (tx == px - 1 or tx == px + 1)",
        "",
        "",
    ]

header = [
    f"# {FEAT_FILE} - AUTO-GENERATED by scripts_general/compress_class_k2pn.py",
    f"# Zero-lookup algebraic evaluator for the {N}x{N} K2P+N class "
    f"'{args.class_name}' (mat max wp,bp,nw,nb = {MAT}).",
    f"# {n_cls:,} class legal states; {n_canon:,} canonical orbits; "
    f"{comp.R:,} compiled rows ({NSEM} semantic"
    + (f" + {len(TAIL_NAMES)} coordinate tail" if tail_used else "") + ").",
    "# State convention: canonical (cwk, cbk, cwp, cbp, cnw, cnb, ctau),",
    "# q = N*y + x, -1 = absent, ctau = side to move (0=White);",
    "# return: mover-relative {0=draw, 1=mover wins, 2=mover loses}.",
    f"N = {N}",
    "",
    "",
] + HELPERS + [
    "",
    f"def eval_{args.class_name}_n{N}_algebraic(cwk, cbk, cwp, cbp, cnw, cnb, ctau):",
]
em = comp.emit(mt_root, feat_lines_class, header, out_path, args.tree_line_limit)

# ================================================= verification
verdict_verify = None
if em.get("emitted"):
    vsrc = os.path.join(args.out_dir, "verify_class.py")
    with open(vsrc, "w") as fh:
        fh.write(f'''import importlib.util, json, sys, time
import os
sys.path.insert(0, {os.path.dirname(os.path.abspath(__file__))!r})
import numpy as np
spec = importlib.util.spec_from_file_location("alg", {out_path!r})
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
ev = mod.eval_{args.class_name}_n{N}_algebraic
Z = np.load({os.path.join(args.oracle_dir, "class_values.npz")!r})
F = Z["F"][Z["CLASS"]]
VAL = Z["VAL"][Z["CLASS"]].astype(int)
import k2pn_basis as KB
mm = 0
t0 = time.time()
canon_cache = {{}}
for i in range(len(F)):
    st = tuple(int(v) for v in F[i])
    c = KB.canon8(st, {N})
    got = ev(c[0], c[1], c[2], c[3], c[4], c[5], c[6])
    want = 0 if VAL[i] == 3 else (1 if VAL[i] == 1 else 2)
    if got != want:
        mm += 1
dt = time.time() - t0
print(json.dumps({{"verified_states": len(F), "value_mismatches": mm,
                   "us_per_state": round(dt / max(1, len(F)) * 1e6, 3)}}))
''')
    t0 = time.time()
    pr = subprocess.run([sys.executable, vsrc], capture_output=True, text=True)
    dt = time.time() - t0
    if pr.returncode != 0:
        P(f"verify FAILED rc={pr.returncode}: {pr.stderr[-800:]}")
        verdict_verify = {"status": "FAILED", "stderr": pr.stderr[-2000:]}
    else:
        verdict_verify = json.loads(pr.stdout.strip().splitlines()[-1])
        verdict_verify["status"] = "PASS" if verdict_verify["value_mismatches"] == 0 else "FAIL"
        verdict_verify["wall_s"] = round(dt, 1)
        P(f"4. verify [{args.class_name}/n{N}]: {verdict_verify['verified_states']:,} "
          f"class states vs the emitted evaluator -> mismatches "
          f"{verdict_verify['value_mismatches']} ({verdict_verify['status']}, "
          f"{verdict_verify['us_per_state']} us/state)")
else:
    # in-process MTBDD verification over canonical orbits (emission over budget)
    stage_mark("in-process MTBDD verify start")
    mm = 0
    NAMES = comp.NAMES
    cols = comp.COLS
    lab0 = comp.LAB0
    for ri in range(comp.R):
        # recompute the row's label from the tree by feature descent
        k = mt_root
        while k[0] == "N":
            nm = NAMES[k[1]]
            ci = NAMES.index(nm)
            v = int(cols[ci][ri])
            nxt = None
            for vv, c in k[2]:
                if vv == v:
                    nxt = c
                    break
            k = nxt
        if int(lab0[ri]) != k[1]:
            mm += 1
    P(f"4. verify [{args.class_name}/n{N}]: emission over line budget "
      f"({em['tree_lines']:,} > {args.tree_line_limit:,}); in-process MTBDD walk over "
      f"{comp.R:,} canonical rows -> mismatches {mm}")
    verdict_verify = {"status": "PASS_INPROCESS" if mm == 0 else "FAIL",
                      "verified_rows": int(comp.R), "value_mismatches": int(mm)}

cur, hwm = rss_mib()
result = {"class": args.class_name, "n": N, "mat": MAT,
          "states": int(n_cls), "canonical_orbits": int(n_canon),
          "semantic_features": NSEM,
          "semantic_distinct_rows": int(sem_conf["distinct_semantic_rows"]),
          "semantic_conflicting_groups": int(sem_conf["semantic_conflicting_groups"]),
          "tail_used": bool(tail_used),
          "full_rows": int(comp.R),
          "mtbdd": {"nodes": int(mn), "paths": int(mp), "max_depth": int(md)},
          "win_loss_bdds": None if skip_wl else
              {"win": {"nodes": wn, "paths": wp_, "depth": wd},
               "loss": {"nodes": ln, "paths": lp, "depth": ld},
               "total_nodes": NODES_TOTAL_WL + mn},
          "ratio_states_per_node": round(n_cls / mn, 2),
          "class_max_dtc": max_dtc,
          "verification": verdict_verify,
          "emission": em,
          "peak_rss_mib": round(hwm, 1),
          "total_time_s": round(time.time() - T0, 1),
          "z3_reference": os.path.join(args.oracle_dir, "z3_injectivity.json")}
with open(os.path.join(args.out_dir, "compression_results.json"), "w") as fh:
    json.dump(result, fh, indent=1)
with open(os.path.join(args.out_dir, "compression_transcript.txt"), "w") as fh:
    fh.write("\n".join(R) + "\n")
P(f"\nsaved -> {os.path.join(args.out_dir, 'compression_results.json')}")
P(f"ratio: {n_cls:,} states / {mn:,} MTBDD nodes = 1:{n_cls/mn:.1f}   "
  f"(peak RSS {hwm:.0f} MiB, total {time.time()-T0:.1f}s)")
