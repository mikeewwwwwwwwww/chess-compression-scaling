#!/usr/bin/env python3
# scripts_general/probe2_minimality.py - which of the candidate v2 features are
# actually load-bearing?  Tests explicit feature-set compositions per class.
# Candidate increments (on top of the v1 basis):
#   A = k_dx_w k_dy_w k_dx_b k_dy_b        (knight -> OWN king, signed)
#   B = k_dxe_w k_dye_w k_dxe_b k_dye_b    (knight -> ENEMY king, signed)
#   C = re_w re_b                          (king rank-edge distance min(y,N-1-y))
#   D = p_dx_w p_dy_w p_dx_b p_dy_b        (pawn -> OWN king, signed)
#   E = p_dxe_w p_dye_w p_dxe_b p_dye_b    (pawn -> ENEMY king, signed)
#   O = opp_file opp_rank                  (orientation split of 'opp')
import os, sys, time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import k2pn_basis as KB

CLASSES = [("kn", 3), ("kn", 4), ("kn", 5), ("kpn", 4), ("kpn", 5),
           ("mirror", 4), ("both", 4)]
MATD = {"kn": (0, 0, 1, 1), "kpn": (1, 0, 1, 0),
        "mirror": (1, 1, 0, 1), "both": (1, 1, 1, 1)}

CONFIGS = [("", set()), ("A", {"A"}), ("B", {"B"}), ("AB", {"A", "B"}),
           ("AC", {"A", "C"}), ("BC", {"B", "C"}), ("ABC", {"A", "B", "C"}),
           ("ABCO", {"A", "B", "C", "O"}),
           ("ABCD", {"A", "B", "C", "D"}), ("ABCE", {"A", "B", "C", "E"}),
           ("ABDE", {"A", "B", "D", "E"}),
           ("ABCDE", {"A", "B", "C", "D", "E"})]


def all_feats(st, N, mat):
    """One pass: v1 features + every candidate increment, named."""
    wk, bk, wp, bp, nw, nb, stm = (int(v) for v in st)
    wp_m, bp_m, nw_m, nb_m = mat
    d_AK = KB.cheb(wk, bk, N)
    same_f = wk % N == bk % N
    same_r = wk // N == bk // N

    def sgn(a, b):
        if a < 0:
            return (-1, -1)
        return (b % N - a % N, b // N - a // N)
    # (a = piece, b = king; signed delta "from piece to king")

    f = list(KB.class_features(wk, bk, wp, bp, nw, nb, stm, N, mat))
    out = {"V1": f}
    dx, dy = sgn(nw, wk); out.update({"A_k_dx_w": dx, "A_k_dy_w": dy})
    dx, dy = sgn(nb, bk); out.update({"A_k_dx_b": dx, "A_k_dy_b": dy})
    dx, dy = sgn(nw, bk); out.update({"B_k_dxe_w": dx, "B_k_dye_w": dy})
    dx, dy = sgn(nb, wk); out.update({"B_k_dxe_b": dx, "B_k_dye_b": dy})
    out.update({"C_re_w": min(wk // N, (N - 1) - wk // N),
                "C_re_b": min(bk // N, (N - 1) - bk // N)})
    out.update({"O_opp_file": int(d_AK == 2 and same_f),
                "O_opp_rank": int(d_AK == 2 and same_r and not same_f)})
    if wp_m or bp_m:
        dx, dy = sgn(wp, wk); out.update({"D_p_dx_w": dx, "D_p_dy_w": dy})
        dx, dy = sgn(bp, bk); out.update({"D_p_dx_b": dx, "D_p_dy_b": dy})
        dx, dy = sgn(wp, bk); out.update({"E_p_dxe_w": dx, "E_p_dye_w": dy})
        dx, dy = sgn(bp, wk); out.update({"E_p_dxe_b": dx, "E_p_dye_b": dy})
    return out


def cols_for(nv, keys, tagset):
    idx, names = [], []
    for i, nm in enumerate(keys["V1"]):
        idx.append(("V1", i)); names.append(nm)
    for grp, pairs in (("A", ["k_dx_w", "k_dy_w", "k_dx_b", "k_dy_b"]),
                       ("B", ["k_dxe_w", "k_dye_w", "k_dxe_b", "k_dye_b"]),
                       ("D", ["p_dx_w", "p_dy_w", "p_dx_b", "p_dy_b"]),
                       ("E", ["p_dxe_w", "p_dye_w", "p_dxe_b", "p_dye_b"])):
        if grp in tagset:
            for p in pairs:
                idx.append((grp, p)); names.append(p)
    for grp, p in (("C", "re_w"), ("C", "re_b"), ("O", "opp_file"), ("O", "opp_rank")):
        if grp in tagset and p in keys:
            idx.append((grp, p)); names.append(p)
    return idx, names


for cls, N in CLASSES:
    mat = MATD[cls]
    d = f"out_class_{cls}_n{N}"
    npz = np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), d, "class_values.npz"))
    states = npz["F"][npz["CLASS"]]
    vals = npz["VAL"][npz["CLASS"]].astype(np.int64)
    NS = len(states)
    print(f"== {cls} N={N}: {NS:,} states ==", flush=True)
    t0 = time.time()
    recs = [all_feats(st, N, mat) for st in states]
    keys = recs[0]
    print(f"  feature pass ({time.time()-t0:.0f}s); configs:", flush=True)
    for tag, tagset in CONFIGS:
        if not (mat[0] or mat[1]) and (set(tag) & {"D", "E"}):
            continue
        idx, names = cols_for(None, keys, tagset)
        F = np.empty((NS, len(idx)), dtype=np.int32)
        for i, r in enumerate(recs):
            for j, (grp, nm) in enumerate(idx):
                F[i, j] = r["V1"][nm] if grp == "V1" else r[f"{grp}_{nm}"]
        keysd = {}
        for i in range(NS):
            k = F[i].tobytes()
            b = keysd.get(k)
            if b is None:
                keysd[k] = [i]
            else:
                b.append(i)
        nc = sum(1 for members in keysd.values()
                 if len(set(int(v) for v in vals[members])) > 1)
        print(f"    {tag:6s} ({len(names):2d} feats): vectors {len(keysd):,}  "
              f"conflicts {nc:,}", flush=True)
        del F, keysd
    del recs
print("probe2 done")
