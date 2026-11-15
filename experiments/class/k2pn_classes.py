#!/usr/bin/env python3
# scripts_general/k2pn_classes.py - retrograde oracle for K2P+N MATERIAL CLASSES.
#
# Solves one material class (and its capture-closure) of the knight-extended
# game K2P+N: king + 0..1 pawn + 0..1 knight per side on an NxN board.  State
# convention is IDENTICAL to phase1_solver_general.py / k2pn_basis.py:
#   q = N*y + x; white advances +y (promotes y=N-1); black advances -y;
#   pawn band y in 1..N-2; uniform 7-tuple (wk, bk, wp, bp, nw, nb, stm),
#   -1 = piece absent; VAL mover-relative (1=mover wins, 2=mover loses, 3=draw).
#
# Ruleset = the repo's conventions D1-D4 (phase1_solver_general.py docstring)
# with exactly two knight-driven generalisations, both forced by D1-D3:
#   R1 (D1): knights are added to the piece set: L-moves, L-captures of enemy
#      pawns/knights, L-checks.  No new rules for other pieces.
#   R2 (D3): "a pawn arriving on its last rank ends the game, mover wins" is
#      taken literally for ARRIVAL BY CAPTURE too - a pawn capturing a knight
#      standing on its promotion rank wins immediately.  (Unreachable in pure
#      K2P: no enemy piece can stand on the promotion rank except the king, and
#      kings are not capturable - so the K2P sub-blocks are untouched.)
# Everything else is mirrored verbatim from phase1_solver_general.py:
#   - stalemate = draw; mover mated = mover loses (D4);
#   - pawn pushes are forbidden while the mover is in check (repo convention;
#     still WLOG with knights: a push can neither capture a checker nor block a
#     knight/pawn check, since knight checks cannot be blocked at all);
#   - promotion pushes require an empty target and are also forbidden in check;
#   - after any move the mover's king must not be attacked (no sliders, so only
#     surviving knight/pawn attacks matter).
#
# Self-tests (asserted, never assumed):
#   S1 K vs K all draws (inside every closure);
#   S2 K+N vs K is a draw everywhere (a lone knight can never mate);
#   S3 colour-swap mirror preserves mover-relative VAL on every legal state;
#   S4 file reflection H preserves VAL on every legal state;
#   S5 at N in {3,4,5}: the knight-free sub-blocks (every state with nw=nb=-1)
#      match the frozen K2P phase-1 oracle npz (out_n{N}/phase1_values.npz)
#      EXACTLY.
#
# Outputs (out dir out_class_{name}_n{N}/):
#   class_values.npz : VAL/DTC (over enumerated legal states), F (7-tuple
#                      fields), ENC (k2pn_basis.enc8 key), class-state index
#   class_results.txt: log + value distribution per material class
import argparse, os, sys, time
from array import array
from collections import deque
from itertools import combinations

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import k2pn_basis as KB

T0 = time.time()
R = []


def rep(s=""):
    R.append(s)
    print(s, flush=True)


CLASSES = {
    # name -> (max wp, max bp, max nw, max nb); the oracle solves the full
    # capture closure (every material componentwise <= the maximum).
    "kn":     (0, 0, 1, 1),   # K+N vs K+N          (PART 2 minimal class)
    "kpn":    (1, 0, 1, 0),   # K+P+N vs K          (PART 3)
    "mirror": (1, 1, 0, 1),   # K+P vs K+P+N        (PART 3, colour-mirrored)
    "both":   (1, 1, 1, 1),   # K+P+N vs K+P+N      (PART 3, marginal)
}

ap = argparse.ArgumentParser(description="Retrograde oracle for K2P+N material classes")
ap.add_argument("--n", type=int, default=4)
ap.add_argument("--class-name", default="kn", choices=sorted(CLASSES))
ap.add_argument("--out-dir", default=None)
ap.add_argument("--no-k2p-crosscheck", action="store_true",
                help="skip self-test S5 (K2P npz cross-check)")
args = ap.parse_args()
N = args.n
NN = N * N
if N < 3:
    ap.error("--n must be >= 3 (knights need a 3x3 board)")
MAT = CLASSES[args.class_name]
if args.out_dir is None:
    args.out_dir = os.path.join(".", f"out_class_{args.class_name}_n{N}")
os.makedirs(args.out_dir, exist_ok=True)
rep(f"config: N={N} class={args.class_name} mat(max wp,bp,nw,nb)={MAT} out={args.out_dir}")

# ------------------------------------------------------------------ geometry
NEI, ADJ = [], [0] * NN
for s in range(NN):
    x, y = s % N, s // N
    lst = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == dy == 0:
                continue
            nx, ny = x + dx, y + dy
            if 0 <= nx < N and 0 <= ny < N:
                lst.append(N * ny + nx)
    NEI.append(tuple(lst))
    ADJ[s] = sum(1 << t for t in lst)

KN, KNA = [], [0] * NN
for s in range(NN):
    x, y = s % N, s // N
    lst = []
    for dx, dy in ((1, 2), (2, 1), (-1, 2), (-2, 1), (1, -2), (2, -1), (-1, -2), (-2, -1)):
        nx, ny = x + dx, y + dy
        if 0 <= nx < N and 0 <= ny < N:
            lst.append(N * ny + nx)
    KN.append(tuple(lst))
    KNA[s] = sum(1 << t for t in lst)

PAWN_SQS = tuple(N * y + x for y in range(1, N - 1) for x in range(N))
WATT, BATT = [0] * NN, [0] * NN
for s in PAWN_SQS:
    x, y = s % N, s // N
    if y + 1 < N:
        for dx in (-1, 1):
            nx = x + dx
            if 0 <= nx < N:
                WATT[s] |= 1 << (N * (y + 1) + nx)
    if y - 1 >= 0:
        for dx in (-1, 1):
            nx = x + dx
            if 0 <= nx < N:
                BATT[s] |= 1 << (N * (y - 1) + nx)

KING_PAIRS = [(a, b) for a in range(NN) for b in range(NN)
              if a != b and not ((ADJ[a] >> b) & 1)]

# numpy views of the attack tables for the vectorised label pass
KNA_np = np.array(KNA, dtype=np.int32)
WATT_np = np.array(WATT, dtype=np.int32)
BATT_np = np.array(BATT, dtype=np.int32)

ALL_SQS = tuple(range(NN))


# --------------------------------------------------------------- movegen
def gen(wk, bk, wp, bp, nw, nb, stm):
    """Legal moves for `stm`.  Returns (succs, promo): succs = list of
    successor placements (opponent to move); promo = number of immediate
    terminal-promotion wins (D3; not successors, no outgoing edges needed)."""
    succs = []
    promo = 0
    if stm == 0:                                   # ---------------- White moves
        inchk = bool((KNA[nb] >> wk) & 1 if nb >= 0 else False) or \
            bool((BATT[bp] >> wk) & 1 if bp >= 0 else False)
        for t in NEI[wk]:                          # king steps
            if t == wp or t == nw:
                continue
            nbp, nnb = bp, nb
            if t == nb:
                nnb = -1
            elif t == bp:
                nbp = -1
            if (ADJ[bk] >> t) & 1:
                continue
            if nbp >= 0 and (BATT[nbp] >> t) & 1:
                continue
            if nnb >= 0 and (KNA[nnb] >> t) & 1:
                continue
            succs.append((t, bk, wp, nbp, nw, nnb))
        if nw >= 0:                                # knight moves
            for t in KN[nw]:
                if t == wk or t == wp or t == bk:
                    continue
                nbp, nnb = bp, nb
                if t == nb:
                    nnb = -1
                elif t == bp:
                    nbp = -1
                if nbp >= 0 and (BATT[nbp] >> wk) & 1:
                    continue
                if nnb >= 0 and (KNA[nnb] >> wk) & 1:
                    continue
                succs.append((wk, bk, wp, nbp, t, nnb))
        if wp >= 0:                                # pawn moves
            x, y = wp % N, wp // N
            t = wp + N
            if y == N - 2:                         # push to promotion rank
                if (not inchk) and t != wk and t != bk and t != bp and t != nb:
                    promo += 1
            elif (not inchk) and t != wk and t != bk and t != bp and t != nb \
                    and t != nw:
                succs.append((wk, bk, t, bp, nw, nb))
            for dx in (-1, 1):                     # diagonal captures
                nx = x + dx
                if not (0 <= nx < N):
                    continue
                t = wp + N + dx
                if t != nb and t != bp:
                    continue
                nnb = -1 if t == nb else nb
                nbp = -1 if t == bp else bp
                if nbp >= 0 and (BATT[nbp] >> wk) & 1:
                    continue                       # own king still attacked
                if nnb >= 0 and (KNA[nnb] >> wk) & 1:
                    continue
                if y == N - 2:
                    promo += 1                     # capture-arrival (R2)
                else:
                    succs.append((wk, bk, t, nbp, nw, nnb))
    else:                                          # ---------------- Black moves
        inchk = bool((KNA[nw] >> bk) & 1 if nw >= 0 else False) or \
            bool((WATT[wp] >> bk) & 1 if wp >= 0 else False)
        for t in NEI[bk]:
            if t == bp or t == nb:
                continue
            nwp, nnw = wp, nw
            if t == nw:
                nnw = -1
            elif t == wp:
                nwp = -1
            if (ADJ[wk] >> t) & 1:
                continue
            if nwp >= 0 and (WATT[nwp] >> t) & 1:
                continue
            if nnw >= 0 and (KNA[nnw] >> t) & 1:
                continue
            succs.append((wk, t, nwp, bp, nnw, nb))
        if nb >= 0:
            for t in KN[nb]:
                if t == bk or t == bp or t == wk:
                    continue
                nwp, nnw = wp, nw
                if t == nw:
                    nnw = -1
                elif t == wp:
                    nwp = -1
                if nwp >= 0 and (WATT[nwp] >> bk) & 1:
                    continue
                if nnw >= 0 and (KNA[nnw] >> bk) & 1:
                    continue
                succs.append((wk, bk, nwp, bp, nnw, t))
        if bp >= 0:
            x, y = bp % N, bp // N
            t = bp - N
            if y == 1:
                if (not inchk) and t != wk and t != bk and t != wp and t != nw:
                    promo += 1
            elif (not inchk) and t != wk and t != bk and t != wp and t != nw \
                    and t != nb:
                succs.append((wk, bk, wp, t, nw, nb))
            for dx in (-1, 1):
                nx = x + dx
                if not (0 <= nx < N):
                    continue
                t = bp - N + dx
                if t != nw and t != wp:
                    continue
                nnw = -1 if t == nw else nw
                nwp = -1 if t == wp else wp
                if nwp >= 0 and (WATT[nwp] >> bk) & 1:
                    continue
                if nnw >= 0 and (KNA[nnw] >> bk) & 1:
                    continue
                if y == 1:
                    promo += 1                     # capture-arrival (R2)
                else:
                    succs.append((wk, bk, nwp, t, nnw, nb))
    return succs, promo


# --------------------------------------------------------------- enumeration
def venc8(wk, bk, wp, bp, nw, nb, stm):
    """k2pn_basis.enc8 vectorised over numpy arrays (absent = -1 -> slot 0).
    Same radix structure as enc8: EVERY piece slot uses R = NN+1."""
    NNv, R = N * N, N * N + 1
    return ((((((wk.astype(np.int64) * NNv + bk) * R + (wp + 1)) * R + (bp + 1)) * R
              + (nw + 1)) * R + (nb + 1)) * 2 + stm)


def vmirror(q):
    """rank reflection y -> N-1-y (absent preserved), vectorised."""
    return np.where(q >= 0, (q % N) + N * (N - 1 - (q // N)), -1)


rep("enumerating closure placements ...")
flds = {k: array('h') for k in ("wk", "bk", "wp", "bp", "nw", "nb", "stm")}
enc_of_state = array('q')
ed_src, ed_dst = array('i'), array('i')
n_placed = 0

wp_max, bp_max, nw_max, nb_max = MAT
W_PAWNS = ((-1,) + PAWN_SQS) if wp_max else (-1,)
B_PAWNS = ((-1,) + PAWN_SQS) if bp_max else (-1,)
W_KNIGHTS = ((-1,) + ALL_SQS) if nw_max else (-1,)
B_KNIGHTS = ((-1,) + ALL_SQS) if nb_max else (-1,)
for wk, bk in KING_PAIRS:
    occ_k = (1 << wk) | (1 << bk)
    for wp in W_PAWNS:
        if wp >= 0 and (occ_k >> wp) & 1:
            continue                              # pawns may not share a king square
        occ_wp = occ_k | (0 if wp < 0 else (1 << wp))
        for bp in B_PAWNS:
            if bp >= 0 and (occ_wp >> bp) & 1:
                continue
            occ_bp = occ_wp | (0 if bp < 0 else (1 << bp))
            for nw in W_KNIGHTS:
                if nw >= 0 and (occ_bp >> nw) & 1:
                    continue
                occ_nw = occ_bp | (0 if nw < 0 else (1 << nw))
                for nb in B_KNIGHTS:
                    if nb >= 0 and (occ_nw >> nb) & 1:
                        continue
                    for stm in (0, 1):
                        # legality: the side NOT to move is not attacked by the
                        # mover's knight/pawn (kings non-adjacent by construction)
                        if stm == 0:              # White moves: Black must be safe
                            if nw >= 0 and (KNA[nw] >> bk) & 1:
                                continue
                            if wp >= 0 and (WATT[wp] >> bk) & 1:
                                continue
                        else:                     # Black moves: White must be safe
                            if nb >= 0 and (KNA[nb] >> wk) & 1:
                                continue
                            if bp >= 0 and (BATT[bp] >> wk) & 1:
                                continue
                        n_placed += 1
                        idx = len(enc_of_state)
                        enc_of_state.append(KB.enc8(wk, bk, wp, bp, nw, nb, stm, N))
                        flds["wk"].append(wk); flds["bk"].append(bk)
                        flds["wp"].append(wp); flds["bp"].append(bp)
                        flds["nw"].append(nw); flds["nb"].append(nb)
                        flds["stm"].append(stm)
                        succs, promo = gen(wk, bk, wp, bp, nw, nb, stm)
                        if promo:
                            continue              # terminal win; edges not needed
                        nxt = 1 - stm
                        for (a, b, c, d, e, f) in succs:
                            ed_src.append(idx)
                            ed_dst.append(KB.enc8(a, b, c, d, e, f, nxt, N))

rep(f"placements enumerated: {n_placed:,} legal states ({time.time()-T0:.1f}s)")
NS = len(enc_of_state)
ENC = np.frombuffer(enc_of_state, dtype=np.int64).copy()
assert len(np.unique(ENC)) == NS, "state encoding enc8 is not injective!"
F = {k: np.frombuffer(v, dtype=np.int16).astype(np.int32) for k, v in flds.items()}

order = np.argsort(ENC, kind='stable')
ENC_sorted = ENC[order]
d_dst = np.frombuffer(ed_dst, dtype=np.int32).copy()
src_idx = np.frombuffer(ed_src, dtype=np.int32).copy()
assert ENC.max() < 2**31 - 1 and int(d_dst.max()) < 2**31 - 1, "enc overflows int32"
succ_pos = np.searchsorted(ENC_sorted, d_dst)
if not (ENC_sorted[np.minimum(succ_pos, NS - 1)] == d_dst).all():
    bad = np.nonzero(ENC_sorted[np.minimum(succ_pos, NS - 1)] != d_dst)[0][:3]
    for k in bad.tolist():
        si = int(src_idx[k])
        s1 = (int(F["wk"][si]), int(F["bk"][si]), int(F["wp"][si]), int(F["bp"][si]),
              int(F["nw"][si]), int(F["nb"][si]), int(F["stm"][si]))
        c = int(d_dst[k]); NNv = N * N; Rd = NNv + 1; t = c
        stm = t % 2; t //= 2
        nb = t % Rd - 1; t //= Rd
        nw = t % Rd - 1; t //= Rd
        bp = t % Rd - 1; t //= Rd
        wp = t % Rd - 1; t //= Rd
        bk = t % NNv; t //= NNv
        rep(f"LEAK: from {s1} -> ({t}, {bk}, {wp}, {bp}, {nw}, {nb}, {stm})")
    raise AssertionError("unmapped successor state (closure leaked?)")
succ_idx = order[succ_pos].astype(np.int32)
NE_ = len(src_idx)
rep(f"legal states: {NS:,}   directed edges: {NE_:,}")

# --------------------------------------------------------------- labels
VAL = np.zeros(NS, dtype=np.int8)                  # 0 unknown; 1 W; 2 L; 3 D
deg = np.bincount(src_idx, minlength=NS).astype(np.int64)

wk_a, bk_a = F["wk"], F["bk"]
wp_a, bp_a = F["wp"], F["bp"]
nw_a, nb_a = F["nw"], F["nb"]
stm_a = F["stm"]

# mover-in-check mask (vectorised; stm==0: WHITE king attacked by black pieces)
att_n = np.where(stm_a == 0,
                 np.where(nb_a >= 0, KNA_np[np.clip(nb_a, 0, NN - 1)] >> wk_a, 0),
                 np.where(nw_a >= 0, KNA_np[np.clip(nw_a, 0, NN - 1)] >> bk_a, 0))
att_p = np.where(stm_a == 0,
                 np.where(bp_a >= 0, BATT_np[np.clip(bp_a, 0, NN - 1)] >> wk_a, 0),
                 np.where(wp_a >= 0, WATT_np[np.clip(wp_a, 0, NN - 1)] >> bk_a, 0))
INCHK = ((att_n | att_p) & 1).astype(bool)

# promo flags exactly as movegen sees them (pawn states only; small subset)
PROMO = np.zeros(NS, dtype=bool)
pawn_ids = np.nonzero(((wp_a >= 0) & (stm_a == 0)) |
                      ((bp_a >= 0) & (stm_a == 1)))[0]
for i in pawn_ids.tolist():
    _, promo = gen(int(wk_a[i]), int(bk_a[i]), int(wp_a[i]), int(bp_a[i]),
                   int(nw_a[i]), int(nb_a[i]), int(stm_a[i]))
    PROMO[i] = promo > 0

VAL[PROMO] = 1                                     # terminal promotion = win
nomove = (deg == 0) & (~PROMO)
VAL[nomove & INCHK] = 2                            # checkmate
VAL[nomove & ~INCHK] = 3                           # stalemate
rep(f"terminals: mates={int((VAL==2).sum()):,} stalemates={int((VAL==3).sum()):,} "
    f"immediate-promotion wins={int((PROMO & (VAL==1)).sum()):,}")

# pending-count propagation (phase1 verbatim)
rptr = np.zeros(NS + 1, dtype=np.int64)
rptr[1:] = np.cumsum(np.bincount(succ_idx, minlength=NS))
rev_order = np.argsort(succ_idx, kind='stable')
rsrc = src_idx[rev_order]
win_pending = deg.copy()
q = deque(np.nonzero((VAL == 1) | (VAL == 2))[0].tolist())
while q:
    s = q.popleft()
    vs = VAL[s]
    if vs == 3:
        continue
    for p in rsrc[rptr[s]:rptr[s + 1]].tolist():
        if VAL[p] != 0:
            continue
        if vs == 2:
            VAL[p] = 1
            q.append(p)
        else:
            win_pending[p] -= 1
            if win_pending[p] == 0:
                VAL[p] = 2
                q.append(p)
n_cyc = int((VAL == 0).sum())
VAL[VAL == 0] = 3
assert not (VAL == 0).any(), "unresolved legal state"
rep(f"retrograde fixpoint reached ({time.time()-T0:.1f}s); cycle-draws = {n_cyc:,}")

# --------------------------------------------------------------- DTC
BIG = 1 << 30
DTC = np.full(NS, BIG, dtype=np.int32)
DTC[(VAL == 2) & (deg == 0)] = 0
DTC[(VAL == 1) & PROMO] = 1
iptr = np.zeros(NS + 1, dtype=np.int64)
iptr[1:] = np.cumsum(deg)
red = np.clip(iptr[:-1], 0, max(NE_ - 1, 0))
edge_val = VAL[succ_idx]
win_m = (VAL == 1)
loss_m = (VAL == 2) & (deg > 0)
for sweep in range(400):
    d_idx = DTC[succ_idx] + 1
    wL = np.where(edge_val == 2, d_idx, BIG)
    wW = np.where(edge_val == 1, d_idx, -1)
    mn = np.minimum.reduceat(wL, red)
    mx = np.maximum.reduceat(wW, red)
    changed = False
    nw_ = np.minimum(DTC[win_m], mn[win_m])
    if not np.array_equal(nw_, DTC[win_m]):
        changed = True
    DTC[win_m] = nw_
    nl_ = mx[loss_m]
    if not np.array_equal(nl_, DTC[loss_m]):
        changed = True
    DTC[loss_m] = nl_
    if not changed:
        break
else:
    raise AssertionError("DTC did not converge")
assert (DTC[VAL == 1] >= 1).all() and (DTC[VAL == 1] < BIG).all()
assert (DTC[VAL == 2] >= 0).all() and (DTC[VAL == 2] < BIG).all()
DTC[VAL == 3] = -1
rep(f"DTC converged in {sweep+1} sweeps; max DTC = {int(DTC[VAL != 3].max())} plies")

# --------------------------------------------------------------- self-tests
rep("self-tests:")
kvk = (nw_a < 0) & (nb_a < 0) & (wp_a < 0) & (bp_a < 0)
assert (VAL[kvk] == 3).all(), "S1 K vs K must be all draws"
rep(f"  S1 K vs K all draws: OK ({int(kvk.sum()):,} states)")

knn_vs_k = (((nw_a >= 0) & (nb_a < 0)) | ((nb_a >= 0) & (nw_a < 0))) & \
           (wp_a < 0) & (bp_a < 0)
assert knn_vs_k.sum() == 0 or (VAL[knn_vs_k] == 3).all(), "S2 K+N vs K must be all draws"
rep(f"  S2 K+N vs K all draws: OK ({int(knn_vs_k.sum()):,} states)")

# S3/S4: map every legal state to its V'-/H-image via one vectorised searchsorted
# S3 needs a colour-symmetric closure (the V' image of a kpn state lives in the
# mirror class, not here); S4 (H, colour-preserving) always applies.
colour_symmetric = (MAT[0] == MAT[1]) and (MAT[2] == MAT[3])
tests = (("S4 file reflection H", "H"),)
if colour_symmetric:
    tests = (("S3 colour-swap mirror", "V"),) + tests
else:
    rep("  S3 colour-swap mirror: SKIPPED (closure is colour-asymmetric; the "
        "V' image lives in the mirrored class)")
for tag, kind in tests:
    if kind == "H":
        mk = lambda arr: np.where(arr >= 0, (arr // N) * N + (N - 1 - arr % N), -1)
        img = mk(wk_a), mk(bk_a), mk(wp_a), mk(bp_a), mk(nw_a), mk(nb_a), stm_a
    else:
        img = (vmirror(bk_a), vmirror(wk_a), vmirror(bp_a), vmirror(wp_a),
               vmirror(nb_a), vmirror(nw_a), 1 - stm_a)
    e_img = venc8(*img)
    pos = np.searchsorted(ENC_sorted, e_img)
    assert (ENC_sorted[np.minimum(pos, NS - 1)] == e_img).all(), \
        f"{tag}: image of a legal state must be legal"
    img_idx = order[pos]
    assert (VAL[img_idx] == VAL).all(), f"{tag} must preserve mover-relative VAL"
    rep(f"  {tag} VAL-preserving: OK ({NS:,} states)")

if not args.no_k2p_crosscheck and N in (3, 4, 5):
    npz_p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         f"out_n{N}", "phase1_values.npz")
    if os.path.exists(npz_p):
        VAL2 = np.load(npz_p)["VAL"]
        KPID = np.full((NN, NN), -1, dtype=np.int64)
        for i, (a, b) in enumerate(KING_PAIRS):
            KPID[a, b] = i
        CFGS = [()] + [(s,) for s in PAWN_SQS]
        for r in (2,):
            CFGS += list(combinations(PAWN_SQS, r))
        CID = {c: i for i, c in enumerate(CFGS)}
        NC = len(CFGS)
        PP_LIST, PPID = [], np.full((NC, NC), -1, dtype=np.int64)
        for wi, wc in enumerate(CFGS):
            for bi, bc in enumerate(CFGS):
                if set(wc) & set(bc):
                    continue
                PPID[wi, bi] = len(PP_LIST)
                PP_LIST.append((wi, bi))
        NPP = len(PP_LIST)
        sub = np.nonzero((nw_a < 0) & (nb_a < 0))[0]
        n_cmp = 0
        for i in sub.tolist():
            wk, bk = int(wk_a[i]), int(bk_a[i])
            wp, bp = int(wp_a[i]), int(bp_a[i])
            kpi = int(KPID[wk, bk])
            if kpi < 0:
                continue
            wi = CID[()] if wp < 0 else CID[(wp,)]
            bi = CID[()] if bp < 0 else CID[(bp,)]
            ppi = int(PPID[wi, bi])
            if ppi < 0:
                continue
            sid2 = (kpi * NPP + ppi) * 2 + int(stm_a[i])
            assert VAL2[sid2] == VAL[i], \
                f"K2P crosscheck mismatch at state {i} ({wk},{bk},{wp},{bp},{stm_a[i]})"
            n_cmp += 1
        rep(f"  S5 K2P phase-1 crosscheck (N={N}): {n_cmp:,} knight-free states "
            f"match out_n{N}/phase1_values.npz exactly: OK")
    else:
        rep(f"  S5 SKIPPED (no {npz_p})")

# --------------------------------------------------------------- class subset
wp_m, bp_m, nw_m, nb_m = MAT
cls_mask = ((wp_a >= 0) if wp_m else (wp_a < 0)) & \
           ((bp_a >= 0) if bp_m else (bp_a < 0)) & \
           ((nw_a >= 0) if nw_m else (nw_a < 0)) & \
           ((nb_a >= 0) if nb_m else (nb_a < 0))
n_cls = int(cls_mask.sum())
rep(f"\nclass {args.class_name}: {n_cls:,} of {NS:,} closure states "
    f"({100.0*n_cls/NS:.1f}%)")

rep("\n== VALUE BY MATERIAL (wp,bp,nw,nb) ==  (closure-wide)")
mats = {}
has = {k: (F[k] >= 0) for k in ("wp", "bp", "nw", "nb")}
for v, k0, k1, k2, k3 in zip(VAL.tolist(), has["wp"].tolist(), has["bp"].tolist(),
                             has["nw"].tolist(), has["nb"].tolist()):
    key = (k0, k1, k2, k3)
    e = mats.setdefault(key, [0, 0, 0, 0])
    e[v] += 1
for key in sorted(mats, reverse=True):
    w, l, d = mats[key][1], mats[key][2], mats[key][3]
    tot = w + d + l
    rep(f"  mat{key}  n={tot:>9,}  mover-wins {w:>8,} ({100.0*w/tot:5.1f}%)  "
        f"draws {d:>8,} ({100.0*d/tot:5.1f}%)  mover-losses {l:>8,} ({100.0*l/tot:5.1f}%)")

OUT_NPZ = os.path.join(args.out_dir, "class_values.npz")
FALL = np.stack([wk_a, bk_a, wp_a, bp_a, nw_a, nb_a, stm_a], axis=1).astype(np.int16)
np.savez_compressed(OUT_NPZ, VAL=VAL, DTC=DTC.astype(np.int32), F=FALL, ENC=ENC,
                    CLASS=np.nonzero(cls_mask)[0].astype(np.int64),
                    MAT=np.array(MAT, dtype=np.int8), NPAR=np.array([N], dtype=np.int8))
rep(f"\narrays saved -> {OUT_NPZ}")
with open(os.path.join(args.out_dir, "class_results.txt"), "w") as fh:
    fh.write("\n".join(R) + "\n")
rep(f"total runtime {time.time()-T0:.1f}s")
