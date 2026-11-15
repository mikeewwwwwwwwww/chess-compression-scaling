#!/usr/bin/env python3
# scripts_general/probe_signed_fix.py - fast numpy probe (no Z3): which feature
# increments close the Z3-injectivity conflicts found by the v1 run?
#
# Levels (on the SAME class_values.npz oracles used by z3_injectivity.py):
#   L0  v1 basis                 : 5 king + 13 knight [+ 14 pawn]  (must
#                                  reproduce the v1 z3_injectivity.json counts)
#   L1  L0 + knight->own signed  : + k_dx_w k_dy_w k_dx_b k_dy_b
#   L2  L1 + knight->enemy signed: + k_dxe_w k_dye_w k_dxe_b k_dye_b
#   L3  L2 + king rank edge      : + re_w re_b = min(y, N-1-y) of each king
#   L4  L3 + opp orientation     : + opp_file opp_rank (split of 'opp')
#   L5  L4 + pawn signed o/e     : + p_dx_w p_dy_w p_dx_b p_dy_b
#                                  + p_dxe_w p_dye_w p_dxe_b p_dye_b
# For every level: distinct vectors + conflict buckets; counterexample dumps
# for levels that still fail.  Signed delta convention: b - a per axis
# ("from piece a to piece b"), (-1, -1) when a is absent.
import os, sys, time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import k2pn_basis as KB

CLASSES = [("kn", 3), ("kn", 4), ("kn", 5), ("kpn", 4), ("kpn", 5),
           ("mirror", 4), ("both", 4)]
MATD = {"kn": (0, 0, 1, 1), "kpn": (1, 0, 1, 0),
        "mirror": (1, 1, 0, 1), "both": (1, 1, 1, 1)}
FILES = "abcdefgh"


def sq(q, N):
    return "--" if q < 0 else f"{FILES[q % N]}{q // N + 1}"


def sgn(a, b, N):
    if a < 0:
        return (-1, -1)
    return (b % N - a % N, b // N - a // N)


def names_for(N, mat, level):
    wp_m, bp_m, nw_m, nb_m = mat
    ns = ["tau", "d_AK", "opp", "e_w", "e_b"]
    ns += ["re_w", "re_b"] if level >= 3 else []
    ns += ["opp_file", "opp_rank"] if level >= 4 else []
    ns += list(KB.KNIGHT_NAMES)
    ns += ["k_dx_w", "k_dy_w", "k_dx_b", "k_dy_b"]
    ns += ["k_dxe_w", "k_dye_w", "k_dxe_b", "k_dye_b"] if level >= 2 else []
    if wp_m or bp_m:
        ns += list(KB.PAWN_NAMES)
        ns += ["p_dx_w", "p_dy_w", "p_dx_b", "p_dy_b"] if level >= 5 else []
        ns += ["p_dxe_w", "p_dye_w", "p_dxe_b", "p_dye_b"] if level >= 5 else []
    return ns


def feats(st, N, mat, level):
    wk, bk, wp, bp, nw, nb, stm = (int(v) for v in st)
    wp_m, bp_m, nw_m, nb_m = mat
    d_AK = KB.cheb(wk, bk, N)
    same_f = wk % N == bk % N
    same_r = wk // N == bk // N
    f = {"tau": stm, "d_AK": d_AK, "opp": int(d_AK == 2 and (same_f or same_r)),
         "e_w": min(wk % N, (N - 1) - wk % N),
         "e_b": min(bk % N, (N - 1) - bk % N),
         "re_w": min(wk // N, (N - 1) - wk // N),
         "re_b": min(bk // N, (N - 1) - bk // N),
         "opp_file": int(d_AK == 2 and same_f),
         "opp_rank": int(d_AK == 2 and same_r and not same_f)}
    f.update(zip(KB.KNIGHT_NAMES, KB.knight_feats(wk, bk, wp, bp, nw, nb, N)))
    dx, dy = sgn(nw, wk, N)
    f.update({"k_dx_w": dx, "k_dy_w": dy})
    dx, dy = sgn(nb, bk, N)
    f.update({"k_dx_b": dx, "k_dy_b": dy})
    dx, dy = sgn(nw, bk, N)
    f.update({"k_dxe_w": dx, "k_dye_w": dy})
    dx, dy = sgn(nb, wk, N)
    f.update({"k_dxe_b": dx, "k_dye_b": dy})
    if wp_m or bp_m:
        f.update(zip(KB.PAWN_NAMES, KB.pawn_feats(wk, bk, wp, bp, nw, nb, N)))
        dx, dy = sgn(wp, wk, N)
        f.update({"p_dx_w": dx, "p_dy_w": dy})
        dx, dy = sgn(bp, bk, N)
        f.update({"p_dx_b": dx, "p_dy_b": dy})
        dx, dy = sgn(wp, bk, N)
        f.update({"p_dxe_w": dx, "p_dye_w": dy})
        dx, dy = sgn(bp, wk, N)
        f.update({"p_dxe_b": dx, "p_dye_b": dy})
    return [f[n] for n in names_for(N, mat, level)]


def bucket_conflicts(F, vals):
    keys = {}
    for i in range(len(F)):
        k = F[i].tobytes()
        b = keys.get(k)
        if b is None:
            keys[k] = [i]
        else:
            b.append(i)
    conflicts = []
    for k, members in keys.items():
        vs = set(int(v) for v in vals[members])
        if len(vs) > 1:
            conflicts.append((members, vs))
    return len(keys), conflicts


V1_EXPECT = {("kn", 3): (290, 4), ("kn", 4): (6328, 6), ("kn", 5): (55312, 6),
             ("kpn", 4): (5469, 518), ("kpn", 5): (39307, 4004),
             ("mirror", 4): (43489, 2946), ("both", 4): (568978, 17892)}

for cls, N in CLASSES:
    mat = MATD[cls]
    d = f"out_class_{cls}_n{N}"
    npz = np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), d, "class_values.npz"))
    states = npz["F"][npz["CLASS"]]
    vals = npz["VAL"][npz["CLASS"]].astype(np.int64)
    NS = len(states)
    print(f"== {cls} N={N}: {NS:,} states ==", flush=True)
    lvl_res = {}
    F = None
    for level in range(6):
        t0 = time.time()
        names = names_for(N, mat, level)
        if level == 0:                       # exact v1 phi from the shared basis
            names = KB.class_semantic_names(mat)
            F = np.empty((NS, len(names)), dtype=np.int32)
            for i, st in enumerate(states):
                F[i] = KB.class_features(int(st[0]), int(st[1]), int(st[2]),
                                         int(st[3]), int(st[4]), int(st[5]),
                                         int(st[6]), N, mat)
        else:
            F1 = np.empty((NS, len(names)), dtype=np.int32)
            for i, st in enumerate(states):
                F1[i] = feats(st, N, mat, level)
            F = F1
        nv, conf = bucket_conflicts(F, vals)
        lvl_res[level] = (nv, conf, names)
        tag = ""
        if level == 0:
            ev, ec = V1_EXPECT[(cls, N)]
            tag = "  [matches v1 run]" if (nv, len(conf)) == (ev, ec) \
                else f"  [MISMATCH vs v1 ({ev:,}, {ec})]"
        print(f"  L{level}: features {len(names):2d}  vectors {nv:,}  "
              f"conflicts {len(conf):,}  ({time.time()-t0:.0f}s){tag}", flush=True)
        if len(conf) == 0:
            break
    failing = [(l, c) for l, (_, c, _) in lvl_res.items() if len(c) > 0]
    if not failing:
        print(f"  -> CLOSED at L{max(lvl_res)}", flush=True)
        continue
    lvl, conf = failing[0]
    _, _, names = lvl_res[lvl]
    print(f"  sample counterexamples at L{lvl}:", flush=True)
    for members, vs in conf[:3]:
        m1 = next(m for m in members if int(vals[m]) == min(vs))
        m2 = next(m for m in members if int(vals[m]) == max(vs))
        s1 = [int(x) for x in states[m1]]
        s2 = [int(x) for x in states[m2]]
        lab = ["wk", "bk", "wp", "bp", "nw", "nb", "stm"]
        f1 = " ".join(f"{l}={sq(q, N)}" for l, q in zip(lab, s1))
        f2 = " ".join(f"{l}={sq(q, N)}" for l, q in zip(lab, s2))
        print(f"    val {min(vs)}: {f1}", flush=True)
        print(f"    val {max(vs)}: {f2}", flush=True)
        print(f"    differing: {[lab[j] for j in range(7) if s1[j] != s2[j]]}"
              f"  bucket {len(members)}", flush=True)
print("probe done")
