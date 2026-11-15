#!/usr/bin/env python3
# scripts_general/z3_injectivity.py - Z3 symbolic injectivity for the K2P+N
# extended feature basis (PART 2/3 of the K2P+N Z3 phase).
#
# QUESTION (per class C, board N): is the extended semantic feature basis
# VALUE-SUFFICIENT on C, i.e.  for all legal s1, s2 in C:
#     phi(s1) == phi(s2)  ==>  VAL(s1) == VAL(s2) ?
# phi is the k2pn_basis feature map - TWO generations:
#   v1  5 king + 13 knight [+ 14 pawn]                (--basis v1)
#   v2  v1 + 8 signed knight offsets (piece->king, both kings)
#       + 2 king rank-edge distances [+ 8 signed pawn offsets]
#                                                     (--basis v2, default)
# VAL is the mover-relative retrograde value from k2pn_classes.py.
# Sufficiency is EXACTLY the condition under which the MTBDD compiler may
# replace states by feature vectors (injectivity on the class); it is a
# SUFFICIENT condition for correct compilation - it says nothing about ratios.
#
# METHOD (task plan (a) + fallback (b)):
#   1. Empirical layer (always): bucket all class states by phi; count distinct
#      vectors; report conflicts (buckets with >1 distinct VAL) - the ground
#      truth companion.
#   2. Z3 encoding self-test: the Z3 mirror of phi is evaluated on ~500 concrete
#      states and must reproduce the Python phi exactly (guards the encoding).
#   3. If conflicts exist: each reported counterexample pair is CERTIFIED by a
#      separate Z3 query over the symbolic legality/phi encoding (sat = the
#      pair is a genuine symbolic counterexample, not a Python-side artifact).
#      Verdict: REFUTED (basis not value-sufficient on the class).
#   4. If no conflicts: attempt the full symbolic proof
#          exists s1, s2: legal(s1) /\ legal(s2) /\ phi(s1)==phi(s2)
#                         /\ VAL[s1] != VAL[s2]
#      with VAL axiomatised as a Z3 array (one store per class state, keyed by
#      enc8).  unsat = PROVED; timeout/unknown = inconclusive -> fall back to
#      a bounded subspace proof (predicate-defined geometric subspace covering
#      ~subspace-frac of the class, array restricted to subspace states).
#
# BIT-VECTOR CONVENTIONS: square fields are BV(16).  A present square is
# 0..NN-1; an absent piece is the two's-complement -1 (0xFFFF).  All guards are
# UNSIGNED: present(q) := ULT(q, NN); absent(q) := UGT(q, NN-1) (unambiguous
# because legality forces every optional field into {0..NN-1} U {0xFFFF}).
# Arithmetic on coordinate differences relies on modular two's complement with
# |diff| <= NN-1 < 2^15, so sign(dx) = UGE(dx, 0x8000) and |dx| = if dx has the
# sign bit then -dx else dx.  The v2 signed features (k_dx_*, p_dxe_*, ...) are
# BV(16) two's-complement differences guarded by piece presence, with the
# absent sentinel -1 on both axes.  enc8 keys reach ~5.9e8 at N=5 and are
# computed in BV32 (zero-extended digits): a BV16 enc would silently overflow
# (a latent v1 bug - the proof path never executed in v1 because every class
# was refuted empirically before reaching it).
import argparse, json, os, sys, time
from itertools import combinations

import numpy as np
import z3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import k2pn_basis as KB

CLASSES = {"kn": (0, 0, 1, 1), "kpn": (1, 0, 1, 0),
           "mirror": (1, 1, 0, 1), "both": (1, 1, 1, 1)}

ap = argparse.ArgumentParser(description="Z3 injectivity for the K2P+N feature basis")
ap.add_argument("--n", type=int, default=4)
ap.add_argument("--class-name", default="kn", choices=sorted(CLASSES))
ap.add_argument("--oracle-dir", default=None,
                help="dir with class_values.npz (default out_class_<cls>_n<N>)")
ap.add_argument("--mode", default="auto",
                choices=["auto", "full", "subspace", "empirical", "mirror-proof"],
                help="auto = empirical + (certify conflicts | full proof -> subspace "
                     "fallback); mirror-proof = symbolic colour-symmetry verification "
                     "of phi under V' (VAL-free) + cross-oracle VAL mirror check")
ap.add_argument("--basis", default="v2", choices=["v1", "v2"],
                help="v1 = 5 king + 13 knight [+ 14 pawn] (the basis every "
                     "committed compression run used); v2 = v1 + 8 signed knight "
                     "offsets + 2 king rank-edge distances [+ 8 signed pawn "
                     "offsets] - the injectivity fix under test")
ap.add_argument("--timeout-full", type=int, default=300,
                help="Z3 budget for the full-class proof, seconds")
ap.add_argument("--timeout-sub", type=int, default=300,
                help="Z3 budget for the subspace proof, seconds")
ap.add_argument("--subspace-frac", type=float, default=0.10)
ap.add_argument("--max-proof-states", type=int, default=60000,
                help="cap on array-axiomatised states for one Z3 proof (full or "
                     "subspace); sizes above it fall back to the empirical layer")
ap.add_argument("--max-ex", type=int, default=12,
                help="max counterexample pairs to collect/certify")
ap.add_argument("--selftest", type=int, default=500, help="phi self-test states (0=off)")
ap.add_argument("--out", default=None, help="output json path")
args = ap.parse_args()

N = args.n
NN = N * N
MAT = CLASSES[args.class_name]
wp_m, bp_m, nw_m, nb_m = MAT
W = 16                                            # bit-vector width
ABSENT = (1 << W) - 1                             # two's complement -1
SIGN = 1 << (W - 1)
AB = 99                                           # k2pn_basis ABSENT sentinel
T0 = time.time()


def log(s=""):
    print(s, flush=True)


oracle_dir = args.oracle_dir or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), f"out_class_{args.class_name}_n{N}")
npz = np.load(os.path.join(oracle_dir, "class_values.npz"))
VAL_all = npz["VAL"]
F_all = npz["F"]
ENC_all = npz["ENC"]
cls_ids = npz["CLASS"]
assert int(npz["NPAR"][0]) == N, "oracle N mismatch"
states = F_all[cls_ids]
vals = VAL_all[cls_ids].astype(np.int64)
NS_cls = len(states)
log(f"loaded {args.class_name} N={N}: class states {NS_cls:,} of "
    f"{len(VAL_all):,} closure states ({oracle_dir})")

has_pawn = bool(wp_m or bp_m)
if args.basis == "v2":
    feat_names = KB.class_semantic_names_v2(MAT)
    log(f"feature basis [{args.basis}]: {len(feat_names)} features = "
        f"5 king + 2 rank-edge + 13 knight + 8 signed knight offsets"
        + (" + 14 pawn + 8 signed pawn offsets" if has_pawn else ""))
else:
    feat_names = KB.class_semantic_names(MAT)
    log(f"feature basis [{args.basis}]: {len(feat_names)} features = 5 king + 13 knight"
        + (" + 14 pawn" if has_pawn else ""))

# ============================================================== python phi
phi_fn = KB.class_features_v2 if args.basis == "v2" else KB.class_features
py_phi = np.empty((NS_cls, len(feat_names)), dtype=np.int64)
for i, st in enumerate(states):
    py_phi[i] = phi_fn(int(st[0]), int(st[1]), int(st[2]), int(st[3]),
                       int(st[4]), int(st[5]), int(st[6]), N, MAT)

# empirical layer -------------------------------------------------------
t0 = time.time()
keys = {}
for i in range(NS_cls):
    k = py_phi[i].tobytes()
    b = keys.get(k)
    if b is None:
        keys[k] = [i]
    else:
        b.append(i)
t_emp = time.time() - t0
n_vec = len(keys)
sizes = np.array([len(v) for v in keys.values()], dtype=np.int64)
conflict_buckets = []
for k, members in keys.items():
    vs = set(int(v) for v in vals[members])
    if len(vs) > 1:
        conflict_buckets.append((k, members, vs))
log(f"empirical: distinct feature vectors {n_vec:,}; largest bucket {int(sizes.max()):,}; "
    f"buckets with >1 VAL: {len(conflict_buckets):,} ({time.time()-t0:.1f}s)")

# ============================================================== Z3 encoding
def bv(v):
    return z3.BitVecVal(int(v) & 0xFFFF, W)


def present(q):
    return z3.ULT(q, NN)


def bmax(a, b):
    return z3.If(z3.UGT(a, b), a, b)


def bmin(a, b):
    return z3.If(z3.ULT(a, b), a, b)


def babs(a):                                      # |a| for modular differences
    return z3.If(z3.UGE(a, SIGN), -a, a)


def zcheb(a, b):
    """k2pn_basis.cheb: max(|dx|,|dy|), ABSENT(99) if either endpoint absent."""
    dx = babs((z3.URem(a, N)) - (z3.URem(b, N)))
    dy = babs((z3.UDiv(a, N)) - (z3.UDiv(b, N)))
    return z3.If(z3.Or(z3.UGT(a, NN - 1), z3.UGT(b, NN - 1)), bv(AB), bmax(dx, dy))


def zknight_att(a, b):
    dx = babs((z3.URem(a, N)) - (z3.URem(b, N)))
    dy = babs((z3.UDiv(a, N)) - (z3.UDiv(b, N)))
    return z3.And(present(a), present(b),
                  z3.Or(z3.And(dx == 1, dy == 2), z3.And(dx == 2, dy == 1)))


def zwatk(pa, t):
    """white pawn attacks t (forward +y)."""
    return z3.And(present(pa), present(t), (z3.UDiv(t, N)) == ((z3.UDiv(pa, N)) + 1),
                  z3.Or((z3.URem(t, N)) == ((z3.URem(pa, N)) - 1), (z3.URem(t, N)) == ((z3.URem(pa, N)) + 1)))


def zbatk(pa, t):
    """black pawn attacks t (forward -y)."""
    return z3.And(present(pa), present(t), (z3.UDiv(t, N)) == ((z3.UDiv(pa, N)) - 1),
                  z3.Or((z3.URem(t, N)) == ((z3.URem(pa, N)) - 1), (z3.URem(t, N)) == ((z3.URem(pa, N)) + 1)))


def zkatk_count(q):
    acc = bv(0)
    x, y = z3.URem(q, N), z3.UDiv(q, N)
    for dx in (-2, -1, 1, 2):
        for dy in (-2, -1, 1, 2):
            if abs(dx) + abs(dy) != 3:
                continue
            nx, ny = x + dx, y + dy
            acc = acc + z3.If(z3.And(z3.ULT(nx, N), z3.ULT(ny, N)), bv(1), bv(0))
    return z3.If(z3.UGT(q, NN - 1), bv(0), acc)


def zsgn(piece, king):
    """Signed per-axis (king - piece) as BV(16) two's complement; -1 on both
    axes when the piece is absent (k2pn_basis._signed_delta)."""
    dx = (z3.URem(king, N)) - (z3.URem(piece, N))
    dy = (z3.UDiv(king, N)) - (z3.UDiv(piece, N))
    return z3.If(present(piece), dx, bv(-1)), z3.If(present(piece), dy, bv(-1))


def zking_feats(wk, bk, stm):
    d_AK = zcheb(wk, bk)
    opp = z3.If(z3.And(d_AK == 2, z3.Or((z3.URem(wk, N)) == (z3.URem(bk, N)),
                                        (z3.UDiv(wk, N)) == (z3.UDiv(bk, N)))), bv(1), bv(0))
    return {"tau": stm, "d_AK": d_AK, "opp": opp,
            "e_w": bmin(z3.URem(wk, N), (N - 1) - (z3.URem(wk, N))),
            "e_b": bmin(z3.URem(bk, N), (N - 1) - (z3.URem(bk, N))),
            "re_w": bmin(z3.UDiv(wk, N), (N - 1) - (z3.UDiv(wk, N))),
            "re_b": bmin(z3.UDiv(bk, N), (N - 1) - (z3.UDiv(bk, N)))}


def zknight_feats(wk, bk, wp, bp, nw, nb):
    nW = z3.If(present(nw), bv(1), bv(0))
    nB = z3.If(present(nb), bv(1), bv(0))
    k_dist = z3.If(z3.And(present(nw), present(nb)), zcheb(nw, nb), bv(AB))
    katt_w = z3.If(present(nw),
                   z3.If(z3.Or(zcheb(nw, bk) == 1, zknight_att(nb, nw),
                               zbatk(bp, nw)), bv(1), bv(0)), bv(0))
    katt_b = z3.If(present(nb),
                   z3.If(z3.Or(zcheb(nb, wk) == 1, zknight_att(nw, nb),
                               zwatk(wp, nb)), bv(1), bv(0)), bv(0))
    kchk_w = z3.If(z3.And(present(nw), zknight_att(nw, bk)), bv(1), bv(0))
    kchk_b = z3.If(z3.And(present(nb), zknight_att(nb, wk)), bv(1), bv(0))
    k_dx_w, k_dy_w = zsgn(nw, wk)
    k_dx_b, k_dy_b = zsgn(nb, bk)
    k_dxe_w, k_dye_w = zsgn(nw, bk)
    k_dxe_b, k_dye_b = zsgn(nb, wk)
    return {"nW": nW, "nB": nB, "k_dist": k_dist, "katt_w": katt_w,
            "katt_b": katt_b, "kchk_w": kchk_w, "kchk_b": kchk_b,
            "k_w_own": zcheb(nw, wk), "k_b_own": zcheb(nb, bk),
            "k_w_enemy": zcheb(nw, bk), "k_b_enemy": zcheb(nb, wk),
            "k_atk_w": zkatk_count(nw), "k_atk_b": zkatk_count(nb),
            "k_dx_w": k_dx_w, "k_dy_w": k_dy_w,
            "k_dx_b": k_dx_b, "k_dy_b": k_dy_b,
            "k_dxe_w": k_dxe_w, "k_dye_w": k_dye_w,
            "k_dxe_b": k_dxe_b, "k_dye_b": k_dye_b}


def zpawn_feats(wk, bk, wp, bp, nw, nb):
    has_w = present(wp)
    has_b = present(bp)
    p_t_w = z3.If(has_w, (N - 1) - (z3.UDiv(wp, N)), bv(AB))
    p_t_b = z3.If(has_b, z3.UDiv(bp, N), bv(AB))
    p_e_w = z3.If(has_w, bmin(z3.URem(wp, N), (N - 1) - (z3.URem(wp, N))), bv(AB))
    p_e_b = z3.If(has_b, bmin(z3.URem(bp, N), (N - 1) - (z3.URem(bp, N))), bv(AB))
    p_chk_w = z3.If(z3.And(has_w, zwatk(wp, bk)), bv(1), bv(0))
    p_chk_b = z3.If(z3.And(has_b, zbatk(bp, wk)), bv(1), bv(0))

    def zfwd(p, up):
        ny = (z3.UDiv(p, N)) + bv(1) if up else (z3.UDiv(p, N)) - bv(1)
        t = (N * ny) + (z3.URem(p, N))
        return z3.If(z3.UGT(p, NN - 1), bv(0),
                     z3.If(z3.UGT(ny, N - 1), bv(0),
                           z3.If(z3.Or(t == wk, t == bk, t == wp, t == bp,
                                       t == nw, t == nb), bv(1), bv(0))))
    p_fwd_w = zfwd(wp, True)
    p_fwd_b = zfwd(bp, False)
    p_kdef_w = z3.If(z3.And(has_w, zcheb(wk, wp) == 1), bv(1), bv(0))
    p_kdef_b = z3.If(z3.And(has_b, zcheb(bk, bp) == 1), bv(1), bv(0))
    p_ndef_w = z3.If(z3.And(has_w, present(nw), zknight_att(nw, wp)), bv(1), bv(0))
    p_ndef_b = z3.If(z3.And(has_b, present(nb), zknight_att(nb, bp)), bv(1), bv(0))
    p_ncap_w = z3.If(z3.And(present(nw), has_b, zknight_att(nw, bp)), bv(1), bv(0))
    p_ncap_b = z3.If(z3.And(present(nb), has_w, zknight_att(nb, wp)), bv(1), bv(0))
    p_dx_w, p_dy_w = zsgn(wp, wk)
    p_dx_b, p_dy_b = zsgn(bp, bk)
    p_dxe_w, p_dye_w = zsgn(wp, bk)
    p_dxe_b, p_dye_b = zsgn(bp, wk)
    return {"p_t_w": p_t_w, "p_t_b": p_t_b, "p_e_w": p_e_w, "p_e_b": p_e_b,
            "p_chk_w": p_chk_w, "p_chk_b": p_chk_b, "p_fwd_w": p_fwd_w,
            "p_fwd_b": p_fwd_b, "p_kdef_w": p_kdef_w, "p_kdef_b": p_kdef_b,
            "p_ndef_w": p_ndef_w, "p_ndef_b": p_ndef_b,
            "p_ncap_w": p_ncap_w, "p_ncap_b": p_ncap_b,
            "p_dx_w": p_dx_w, "p_dy_w": p_dy_w,
            "p_dx_b": p_dx_b, "p_dy_b": p_dy_b,
            "p_dxe_w": p_dxe_w, "p_dye_w": p_dye_w,
            "p_dxe_b": p_dxe_b, "p_dye_b": p_dye_b}


def zphi(wk, bk, wp, bp, nw, nb, stm):
    d = zking_feats(wk, bk, stm)
    d.update(zknight_feats(wk, bk, wp, bp, nw, nb))
    if has_pawn:
        d.update(zpawn_feats(wk, bk, wp, bp, nw, nb))
    return [d[nm] for nm in feat_names]


def zlegal(stm, wk, bk, wp, bp, nw, nb):
    """Exactly the k2pn_classes enumeration legality for material class MAT."""
    conds = [wk != bk, zcheb(wk, bk) != 1,           # kings distinct + non-adjacent
             z3.ULT(stm, 2), z3.ULT(wk, NN), z3.ULT(bk, NN)]
    conds.append(present(nw) if nw_m else nw == ABSENT)
    conds.append(present(nb) if nb_m else nb == ABSENT)
    conds.append(present(wp) if wp_m else wp == ABSENT)
    conds.append(present(bp) if bp_m else bp == ABSENT)
    pieces = [p for p, m in ((wp, wp_m), (bp, bp_m), (nw, nw_m), (nb, nb_m)) if m]
    for a, b in combinations(pieces, 2):
        conds.append(a != b)
    for p in pieces:
        conds.append(p != wk)
        conds.append(p != bk)
    if wp_m:
        conds.append(z3.And(z3.UGE(z3.UDiv(wp, N), 1), z3.ULE(z3.UDiv(wp, N), N - 2)))
    if bp_m:
        conds.append(z3.And(z3.UGE(z3.UDiv(bp, N), 1), z3.ULE(z3.UDiv(bp, N), N - 2)))
    # the side NOT to move is not attacked by the mover's knight/pawn
    if nw_m:
        conds.append(z3.Implies(stm == 0, z3.Not(zknight_att(nw, bk))))
    if nb_m:
        conds.append(z3.Implies(stm == 1, z3.Not(zknight_att(nb, wk))))
    if wp_m:
        conds.append(z3.Implies(stm == 0, z3.Not(zwatk(wp, bk))))
    if bp_m:
        conds.append(z3.Implies(stm == 1, z3.Not(zbatk(bp, wk))))
    return z3.And(conds)


def zenc(wk, bk, wp, bp, nw, nb, stm):
    """k2pn_basis.enc8 as BV32 arithmetic: each radix digit is a BV16 field
    (+1 for the absent sentinel, wrapping to 0 in modular BV16 arithmetic)
    zero-extended to BV32 before the multiplications.  enc8 reaches ~5.9e8 at
    N=5, so the folded product MUST be computed in BV32 (a BV16 enc silently
    overflows - latent v1 bug, surfaced by the first 0-conflict proof run)."""
    R32 = z3.BitVecVal(NN + 1, 32)
    NN32 = z3.BitVecVal(NN, 32)

    def x16(x):
        return z3.ZeroExt(16, x)

    return ((((((x16(wk) * NN32 + x16(bk)) * R32 + x16(wp + bv(1))) * R32
               + x16(bp + bv(1))) * R32 + x16(nw + bv(1))) * R32
             + x16(nb + bv(1))) * z3.BitVecVal(2, 32) + x16(stm))


def as_signed(e):
    """Python int of a BV(16) feature expression (two's-complement decode -
    as_long() is unsigned, so signed v2 deltas need this)."""
    v = z3.simplify(e).as_long()
    return v - (1 << W) if v >= (1 << (W - 1)) else v


def phi_z3_eval(st):
    wf = [bv(int(v)) for v in st]
    return tuple(as_signed(e) for e in zphi(*wf))


enc_cls = ENC_all[cls_ids]                       # enc8 key of every class state

if args.selftest:
    rng = np.random.default_rng(11)
    idx = rng.choice(NS_cls, size=min(args.selftest, NS_cls), replace=False)
    t0 = time.time()
    for i in idx:
        got = phi_z3_eval(states[i])
        assert got == tuple(int(v) for v in py_phi[i]), \
            f"Z3 phi mismatch on state {i}: {got} vs {tuple(py_phi[i])}"
    log(f"z3 phi self-test: {len(idx)} states reproduced exactly ({time.time()-t0:.1f}s)")
    rng2 = np.random.default_rng(12)
    idx2 = rng2.choice(NS_cls, size=min(args.selftest, NS_cls), replace=False)
    t0 = time.time()
    for i in idx2:
        wf = [bv(int(v)) for v in states[i]]
        got = int(z3.simplify(zenc(*wf)).as_long())
        assert got == int(enc_cls[i]), \
            f"zenc mismatch on state {i}: {got} vs {int(enc_cls[i])}"
    log(f"z3 enc self-test: {len(idx2)} enc8 keys reproduced exactly ({time.time()-t0:.1f}s)")

# ============================================================== verdicts
result = {"n": N, "class": args.class_name, "mat": MAT, "basis": args.basis,
          "class_states": int(NS_cls), "feature_count": len(feat_names),
          "distinct_feature_vectors": int(n_vec),
          "max_bucket": int(sizes.max()),
          "conflict_buckets": len(conflict_buckets),
          "empirical_time_s": round(t_emp, 2)}


def build_array(ids):
    a = z3.Const("VAL", z3.ArraySort(z3.BitVecSort(32), z3.BitVecSort(8)))
    for i in ids.tolist():
        a = z3.Store(a, int(ENC_all[i]), int(VAL_all[i]))
    return a


def field_list(sfx):
    f = []
    for nm, m in (("wk", True), ("bk", True), ("wp", wp_m), ("bp", bp_m),
                  ("nw", nw_m), ("nb", nb_m)):
        f.append(z3.BitVec(f"{nm}{sfx}", W) if m else bv(-1))
    f.append(z3.BitVec(f"stm{sfx}", W))
    return f


def certify_full(pair_ids):
    """Z3-check a concrete conflict pair against the symbolic encoding."""
    s = z3.Solver()
    e1 = [bv(int(v)) for v in states[pair_ids[0]]]
    e2 = [bv(int(v)) for v in states[pair_ids[1]]]
    s.add(zlegal(e1[6], *e1[:6]))
    s.add(zlegal(e2[6], *e2[:6]))
    p1, p2 = zphi(*e1), zphi(*e2)
    s.add(z3.And([x == y for x, y in zip(p1, p2)]))
    s.add(bv(int(vals[pair_ids[0]])) != bv(int(vals[pair_ids[1]])))
    r = s.check()
    assert r == z3.sat, f"certificate check returned {r} for pair {pair_ids}"
    return True


if conflict_buckets and args.mode != "mirror-proof":
    log(f"verdict path: REFUTED - certifying up to {args.max_ex} conflict pairs in Z3")
    examples = []
    t0 = time.time()
    for k, members, vs in conflict_buckets[:args.max_ex]:
        vs_l = sorted(vs)
        m1 = next(m for m in members if int(vals[m]) == vs_l[0])
        m2 = next(m for m in members if int(vals[m]) == vs_l[1])
        certify_full((m1, m2))
        examples.append({
            "shared_phi": [int(x) for x in py_phi[m1]],
            "feature_names": feat_names,
            "s1": [int(x) for x in states[m1]], "val1": int(vals[m1]),
            "s2": [int(x) for x in states[m2]], "val2": int(vals[m2]),
            "bucket_size": len(members),
            "z3_certified": True})
    result["verdict"] = "REFUTED"
    result["verdict_meaning"] = ("the extended basis is NOT value-sufficient on this "
                                 "class: feature-equal states with different oracle "
                                 "VAL exist (Z3-certified); the MTBDD needs the "
                                 "coordinate tail or stronger features")
    result["counterexamples"] = examples
    result["z3_time_s"] = round(time.time() - t0, 2)
elif args.mode == "mirror-proof":
    # ---- PART 3 mirror-class verification ----------------------------------
    # (1) symbolic, VAL-free: phi commutes with the colour-swap mirror V':
    #       for every legal mirror-class state s (K+P vs K+P+N):
    #           phi(V'(s)) == swap_wb(phi(s))
    #     swap_wb exchanges every white/black feature component and maps
    #     tau -> 1 - tau.  unsat of the difference query = proved.
    # (2) empirical: mover-relative VAL is preserved by V' ACROSS INDEPENDENT
    #     oracle runs: V'(s) has material K+P+N vs K+P, which lives in the
    #     'both' closure (not in either single-side closure), so the mirror
    #     npz is checked against the independently-solved both npz.
    log("mirror-proof: symbolic phi-symmetry under V' + cross-oracle VAL check")
    assert MAT == (1, 1, 0, 1), "mirror-proof expects the mirror class K+P vs K+P+N"

    def zmirror_fields(f):
        wk, bk, wp, bp, nw, nb, stm = f

        def vq(q):
            return z3.If(z3.UGT(q, NN - 1), bv(-1),
                         (q % N) + N * ((N - 1) - z3.UDiv(q, N)))
        return [vq(bk), vq(wk), vq(bp), vq(wp), vq(nb), vq(nw), bv(1) - stm]

    def partner(nm):
        if nm == "tau":
            return "tau", "flip"
        if nm == "nW":
            return "nB", "id"
        if nm == "nB":
            return "nW", "id"
        if nm in ("k_w_own", "k_b_own"):
            return ("k_b_own" if nm == "k_w_own" else "k_w_own"), "id"
        if nm in ("k_w_enemy", "k_b_enemy"):
            return ("k_b_enemy" if nm == "k_w_enemy" else "k_w_enemy"), "id"
        if nm in ("k_dx_w", "k_dx_b", "k_dxe_w", "k_dxe_b",
                  "p_dx_w", "p_dx_b", "p_dxe_w", "p_dxe_b",
                  "re_w", "re_b"):
            return (nm[:-2] + "_b" if nm.endswith("_w") else nm[:-2] + "_w"), "id"
        if nm in ("k_dy_w", "k_dy_b", "k_dye_w", "k_dye_b",
                  "p_dy_w", "p_dy_b", "p_dye_w", "p_dye_b"):
            # Signed RANK deltas are colour-swap ANTI-invariant: V' maps
            # k_dy_w(s) -> -k_dy_b(s).  The negation must NOT touch the absent
            # sentinel (-1 stays -1), so the swap carries a presence guard for
            # the piece owning the TARGET feature (GUARD table below).
            return (nm[:-2] + "_b" if nm.endswith("_w") else nm[:-2] + "_w"), "neg"
        if nm.endswith("_w"):
            return nm[:-2] + "_b", "id"
        if nm.endswith("_b"):
            return nm[:-2] + "_w", "id"
        return nm, "id"                                # d_AK, opp, k_dist

    pos_of = {nm: i for i, nm in enumerate(feat_names)}
    # neg-mode presence guard: field_list("1") layout is [wk, bk, wp, bp, nw,
    # nb, stm]; the guard is the piece owning the TARGET feature (a dy feature
    # is present iff its piece is).
    GUARD = {"k_dy_b": 5, "k_dy_w": 4, "k_dye_b": 5, "k_dye_w": 4,
             "p_dy_b": 3, "p_dy_w": 2, "p_dye_b": 3, "p_dye_w": 2}
    f1 = field_list("1")
    s = z3.Solver()
    s.set("timeout", args.timeout_full * 1000)
    s.add(zlegal(f1[6], *f1[:6]))                      # mirror-class legality
    p_s = zphi(*f1)
    p_img = zphi(*zmirror_fields(f1))
    swapped = []
    for nm in feat_names:
        tgt, mode = partner(nm)
        e = p_s[pos_of[tgt]]
        if mode == "flip":
            swapped.append(bv(1) - e)
        elif mode == "neg":
            swapped.append(z3.If(present(f1[GUARD[tgt]]), -e, bv(-1)))
        else:
            swapped.append(e)
    diffs = [p_img[i] != swapped[i] for i in range(len(feat_names))]
    s.add(z3.Or(diffs))
    t0 = time.time()
    r = s.check()
    dt = time.time() - t0
    log(f"z3 phi/V' symmetry: {r} ({dt:.1f}s)")
    result["z3_mirror_symmetry"] = {"result": str(r), "time_s": round(dt, 2)}
    if r != z3.unsat:
        result["verdict"] = "MIRROR_ASYMMETRY_BUG"
        result["verdict_meaning"] = ("Z3 found a state whose phi does NOT commute "
                                     "with V' - the feature map or the swap table is "
                                     "asymmetric (implementation bug)")
        m = s.model()
        result["z3_mirror_witness"] = [
            int(m.eval(x, model_completion=True).as_long()) for x in f1]
    else:
        result["verdict"] = "MIRROR_SYMMETRY_VERIFIED"
        result["verdict_meaning"] = (
            "Z3 proved the feature basis is colour-symmetric under V' (phi commutes "
            "with the mirror, VAL-free symbolic proof) and mover-relative VAL is "
            "preserved across independent oracle runs; this says NOTHING about "
            "value-sufficiency - see conflict_buckets for the REFUTED status")
    result["z3_time_s"] = dt
    both_p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          f"out_class_both_n{N}", "class_values.npz")
    B = np.load(both_p)
    B_ENC = np.sort(B["ENC"])
    B_order = np.argsort(B["ENC"], kind='stable')
    B_VAL = B["VAL"][B_order]
    n_chk = 0
    for i in range(NS_cls):
        st = tuple(int(v) for v in states[i])
        m = KB.t_V8(st, N)
        j = int(np.searchsorted(B_ENC, KB.enc8(*m, N)))
        assert int(B_ENC[j]) == KB.enc8(*m, N), "V' image missing from both-closure"
        assert int(B_VAL[j]) == int(vals[i]), \
            f"cross-oracle mirror VAL mismatch at state {i}"
        n_chk += 1
    log(f"cross-oracle VAL mirror check: {n_chk:,} states agree with the "
        f"independently-solved 'both' oracle")
    result["cross_oracle_mirror_val"] = {"states": int(n_chk), "mismatches": 0,
                                         "reference": "out_class_both_n%d" % N}
else:
    def run_proof(state_ids, extra=None, budget=300, label=""):
        a = build_array(state_ids)
        s = z3.Solver()
        s.set("timeout", budget * 1000)
        f1 = field_list("1")
        f2 = field_list("2")
        s.add(zlegal(f1[6], *f1[:6]))
        s.add(zlegal(f2[6], *f2[:6]))
        p1, p2 = zphi(*f1), zphi(*f2)
        s.add(z3.And([x == y for x, y in zip(p1, p2)]))
        s.add(z3.Select(a, zenc(*f1)) != z3.Select(a, zenc(*f2)))
        if extra is not None:
            s.add(extra(f1), extra(f2))
        t0 = time.time()
        r = s.check()
        dt = time.time() - t0
        log(f"z3 {label}: {r} ({dt:.1f}s, array over {len(state_ids):,} states)")
        return r, dt, s

    cls_idx = cls_ids
    wk_cls = states[:, 0]
    if args.mode in ("auto", "full", "subspace"):
        if args.mode in ("auto", "full"):
            if NS_cls <= args.max_proof_states:
                r, dt, s = run_proof(cls_idx, budget=args.timeout_full,
                                     label="full-class proof")
                result["z3_full"] = {"result": str(r), "time_s": round(dt, 2),
                                     "array_states": int(NS_cls)}
                if r == z3.unsat:
                    result["verdict"] = "PROVED"
                    result["verdict_meaning"] = ("no legal class states with identical "
                                                 "feature vectors and different VAL - the "
                                                 "basis is value-sufficient on this class "
                                                 "(Z3 unsat over the full class)")
                    result["z3_time_s"] = dt
                elif r == z3.sat:
                    m = s.model()
                    ex = [[int(m.eval(x, model_completion=True).as_long()) for x in f]
                          for f in (field_list("1"), field_list("2"))]
                    result["verdict"] = "Z3_SAT_UNEXPECTED"
                    result["z3_witness"] = ex
                    log("WARNING: Z3 found a witness despite 0 empirical conflicts - "
                        "encoding bug suspected")
                else:
                    result["verdict"] = "Z3_INCONCLUSIVE"
                    result["verdict_meaning"] = ("full-class Z3 proof exceeded the budget; "
                                                 "falling back to a bounded subspace proof "
                                                 "+ empirical layer")
            else:
                result["z3_full"] = {
                    "result": "SKIPPED",
                    "reason": f"class has {NS_cls:,} states > --max-proof-states "
                              f"{args.max_proof_states:,}; the per-state VAL array "
                              "axiomatisation is not attempted at this size"}
        if result.get("verdict") in (None, "Z3_INCONCLUSIVE") and \
                args.mode in ("auto", "subspace"):
            target = max(1, int(args.subspace_frac * NS_cls))
            K = 1
            while K < NN and int((wk_cls < K).sum()) < target:
                K += 1
            sub_ids = cls_idx[wk_cls < K]
            frac = len(sub_ids) / NS_cls
            log(f"subspace: wk < {K} covers {len(sub_ids):,} class states "
                f"({100.0*frac:.1f}%)")
            extra = lambda f: z3.ULT(f[0], K)
            if len(sub_ids) <= args.max_proof_states:
                r2, dt2, s2 = run_proof(sub_ids, extra=extra,
                                        budget=args.timeout_sub, label="subspace proof")
                result["z3_subspace"] = {"result": str(r2), "time_s": round(dt2, 2),
                                         "array_states": int(len(sub_ids)),
                                         "wk_lt": int(K), "fraction": round(frac, 4)}
                if r2 == z3.unsat:
                    result["verdict"] = "PROVED_ON_SUBSPACE"
                    full_note = ("full-class proof exceeded the budget"
                                 if result.get("z3_full", {}).get("result") == "unknown"
                                 else "full-class axiomatisation skipped (class size)")
                    result["verdict_meaning"] = (
                        f"Z3 proved value-sufficiency on the bounded subspace "
                        f"(wk < {K}, {100.0*frac:.1f}% of the class); {full_note}; "
                        f"empirical layer clean on the full class ({NS_cls:,} states, "
                        f"{n_vec:,} feature vectors)")
                elif r2 == z3.sat:
                    result["verdict"] = "Z3_SAT_UNEXPECTED"
                elif result.get("verdict") is None:
                    result["verdict"] = "Z3_INCONCLUSIVE"
                    result["verdict_meaning"] = ("subspace Z3 proof exceeded budget; "
                                                 "verdict rests on the empirical layer "
                                                 "(0 conflicts over the full class, "
                                                 f"{NS_cls:,} states)")
            else:
                result["z3_subspace"] = {
                    "result": "SKIPPED",
                    "reason": f"the {args.subspace_frac:.0%} subspace has "
                              f"{len(sub_ids):,} states > --max-proof-states "
                              f"{args.max_proof_states:,}"}
            if result.get("verdict") is None:
                result["verdict"] = "EMPIRICAL_ONLY"
                result["verdict_meaning"] = (
                    "no Z3 proof attempted within the array-size cap; value-sufficiency "
                    "rests on the empirical layer: 0 conflicts over the full class "
                    f"({NS_cls:,} states, {n_vec:,} feature vectors)")
    else:
        result["verdict"] = "EMPIRICAL_ONLY"
        result["verdict_meaning"] = ("empirical layer only: 0 conflicts over the "
                                     f"full class ({NS_cls:,} states)")

result["z3_version"] = z3.get_version_string()
result["total_time_s"] = round(time.time() - T0, 2)
out_path = args.out or os.path.join(oracle_dir, "z3_injectivity.json")
with open(out_path, "w") as fh:
    json.dump(result, fh, indent=1)
log(f"verdict: {result['verdict']}")
log(f"saved -> {out_path}")
