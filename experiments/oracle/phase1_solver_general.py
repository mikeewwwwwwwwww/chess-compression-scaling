#!/usr/bin/env python3
"""
Phase 1 (N-generalized): Micro-Domain Retrograde Oracle
=======================================================
Game: K+2P vs K+2P on an NxN board ("K2P-NxN"; N set via --n, default 4).

This file is a copy of the repo's scripts/phase1_solver.py (commit 76ba614),
made N-parameterized for the board-scaling experiment; it lives in
research/k2p/scripts_general/ OUTSIDE the repo. All board-dimension literals
of the 4x4 original (16/4/3/15) are derived from N here. The N-dependent
INVARIANT LAYER (PHI/MU/CHI/BLOCK + falsifier labs) is SKIPPED by default
(--skip-invariants; use --no-skip-invariants to enable) because its semantics
do not transfer across N: the arrays are still allocated (zeros) so the .npz
layout is unchanged. VAL/DTC/edges/mirror mechanics are exact and are
validated at N=4 against the frozen artifacts before any N!=4 run.

FORMAL RULESET (conventions D1-D4, see accompanying write-up)
-------------------------------------------------------------
Board: squares s = N*y + x, x,y in {0..N-1}; files a.. = x 0..N-1, ranks 1..N = y 0..N-1.
       Chessboard colour: c(s) = (x+y) mod 2.  White advances +y (promotes y=N-1),
       Black advances -y (promotes y=0). Middle (pawn) band M = {y in 1..N-2}.

D1. Pieces: 1 King + up to 2 Pawns per side (captures reduce material; no new
    piece types ever appear).
D2. Pawns: single-step forward push into an empty square; diagonal forward
    capture of an enemy PAWN; no double step; no en passant; no castling.
D3. TERMINAL PROMOTION: a pawn arriving on its last rank ends the game, mover
    wins immediately. (Consequence: control of the promotion square has zero
    defensive value - the defender must physically blockade a push target or
    capture the pawn.)
D4. Draw convention: stalemate = draw; cycles under optimal play = draw
    (threefold/50-move rules deliberately omitted; strong-solution scope:
    every legal position, tablebase-style).

Check: only pawns give check (kings can never be adjacent by construction).
Legal position: the side NOT to move is not in check; kings non-adjacent.
Terminals: (i) mover in check with no legal move  -> mover LOSES (mate);
           (ii) mover not in check, no legal move -> DRAW (stalemate);
           (iii) promotion move available          -> mover WINS immediately.

Output: exact W/L/D value of every legal state via retrograde analysis on the
complete directed transition graph, DTC distances, candidate-invariant
evaluation (phi, mu, chi), zugzwang statistics, falsifier extraction.
"""

import argparse, os, time, sys, platform
from collections import deque
from itertools import combinations
import numpy as np

T0 = time.time()
R = []          # report buffer

def rep(s=""):
    R.append(s)
    print(s)

ap = argparse.ArgumentParser(
    description="N-parameterized retrograde WDL/DTC oracle for K+2P vs K+2P on an "
                "NxN board (generalized copy of scripts/phase1_solver.py).")
ap.add_argument("--n", type=int, default=4, help="board edge N (board is NxN)")
ap.add_argument("--out-dir", default=None,
                help="output directory (default: ./out_n{N}/)")
ap.add_argument("--skip-invariants", action=argparse.BooleanOptionalAction, default=True,
                help="skip the N-dependent invariant layer (PHI/MU/CHI/BLOCK + falsifier "
                     "labs); arrays are still allocated as zeros so the .npz layout is "
                     "unchanged (default: skipped)")
args = ap.parse_args()
if args.n < 2:
    ap.error("--n must be >= 2")
N = args.n
NN = N * N
if args.out_dir is None:
    args.out_dir = os.path.join(".", f"out_n{N}")
os.makedirs(args.out_dir, exist_ok=True)
OUT_TXT = os.path.join(args.out_dir, "phase1_results.txt")
OUT_NPZ = os.path.join(args.out_dir, "phase1_values.npz")
SKIP_INV = bool(args.skip_invariants)
rep(f"config: N={N}  out_dir={args.out_dir}  skip_invariants={SKIP_INV}")

# ------------------------------------------------------------------ geometry
def xy(s): return (s % N, s // N)

NEI, ADJ = [], [0]*NN
for s in range(NN):
    x, y = s % N, s // N
    lst = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == dy == 0: continue
            nx, ny = x+dx, y+dy
            if 0 <= nx < N and 0 <= ny < N: lst.append(N*ny+nx)
    NEI.append(tuple(lst))
    ADJ[s] = sum(1 << t for t in lst)

PAWN_SQS = tuple(N*y + x for y in range(1, N-1) for x in range(N))   # pawn-band squares

WATT, BATT = [0]*NN, [0]*NN     # pawn attack masks (pawns exist only in band)
for s in PAWN_SQS:
    x, y = s % N, s // N
    if y+1 < N:
        for dx in (-1, 1):
            nx = x+dx
            if 0 <= nx < N: WATT[s] |= 1 << (N*(y+1)+nx)
    if y-1 >= 0:
        for dx in (-1, 1):
            nx = x+dx
            if 0 <= nx < N: BATT[s] |= 1 << (N*(y-1)+nx)

# --------------------------------------------------------- king pairs / configs
KING_PAIRS, KPID = [], [[-1]*NN for _ in range(NN)]
for wk in range(NN):
    for bk in range(NN):
        if wk == bk or (ADJ[wk] >> bk) & 1: continue
        KPID[wk][bk] = len(KING_PAIRS); KING_PAIRS.append((wk, bk))
NK = len(KING_PAIRS)

CFGS = [()]
for r in (1, 2): CFGS += list(combinations(PAWN_SQS, r))
NC = len(CFGS)
CID = {c: i for i, c in enumerate(CFGS)}
CMASK = [sum(1 << s for s in c) for c in CFGS]

PP_LIST, PPID = [], [[-1]*NC for _ in range(NC)]
for wi, wc in enumerate(CFGS):
    ws = set(wc)
    for bi, bc in enumerate(CFGS):
        if ws & set(bc): continue
        PPID[wi][bi] = len(PP_LIST); PP_LIST.append((wi, bi))
NPP = len(PP_LIST)

# config transition tables
CFG_MV_W, CFG_MV_B, CFG_DEL = {}, {}, {}
for ci, c in enumerate(CFGS):
    cs = set(c)
    for q in c:
        CFG_DEL[(ci, q)] = CID[tuple(sorted(cs - {q}))]
        x, y = q % N, q // N
        for dx in (-1, 0, 1):
            nx = x+dx
            if not (0 <= nx < N): continue
            ny = y+1
            if ny <= N-2:    # white in-band target (y=N-1 = terminal promotion)
                CFG_MV_W[(ci, q, N*ny+nx)] = CID[tuple(sorted(cs - {q} | {N*ny+nx}))]
            ny = y-1
            if ny >= 1:      # black in-band target (y=0 = terminal promotion)
                CFG_MV_B[(ci, q, N*ny+nx)] = CID[tuple(sorted(cs - {q} | {N*ny+nx}))]

# ------------------------------------------------------------- move generation
def gen(wk, bk, wi, bi, stm):
    """Legal moves for `stm` in placement. Returns (list of
    (nwk,nbk,nwi,nbi), number_of_promotion_moves)."""
    mv = []; promo = 0
    wset, bset = CFGS[wi], CFGS[bi]
    wm = CMASK[wi] | (1 << wk)
    bm = CMASK[bi] | (1 << bk)
    if stm == 0:                                        # ---- White to move
        bpa = 0
        for s_ in bset: bpa |= BATT[s_]
        for t in NEI[wk]:                               # king moves
            bt = 1 << t
            if bt & wm: continue
            if bt & bm:                                 # capture black pawn
                nbi = CFG_DEL[(bi, t)]
                nbpa = 0
                for s_ in CFGS[nbi]: nbpa |= BATT[s_]
            else:
                nbi = bi; nbpa = bpa
            if (ADJ[bk] >> t) & 1: continue             # adjacent to enemy K
            if (nbpa >> t) & 1: continue                # into pawn attack
            mv.append((t, bk, wi, nbi))
        inchk = (bpa >> wk) & 1                         # mover in check?
        for src in wset:                                # pawn moves
            x, y = src % N, src // N
            for dx in (-1, 0, 1):
                nx = x+dx
                if not (0 <= nx < N): continue
                t = N*(y+1)+nx
                bt = 1 << t
                if dx == 0:                             # push
                    if (bt & wm) or (bt & bm) or inchk: continue
                    if y == N-2: promo += 1             # terminal promotion
                    else: mv.append((wk, bk, CFG_MV_W[(wi, src, t)], bi))
                else:                                   # capture
                    if not (bt & bm) or t == bk: continue
                    nwi = CFG_MV_W[(wi, src, t)]
                    nbi = CFG_DEL[(bi, t)]
                    nbpa = 0
                    for s_ in CFGS[nbi]: nbpa |= BATT[s_]
                    if (nbpa >> wk) & 1: continue       # own K still attacked
                    mv.append((wk, bk, nwi, nbi))
    else:                                               # ---- Black to move
        wpa = 0
        for s_ in wset: wpa |= WATT[s_]
        for t in NEI[bk]:
            bt = 1 << t
            if bt & bm: continue
            if bt & wm:                                 # capture white pawn
                nwi = CFG_DEL[(wi, t)]
                nwpa = 0
                for s_ in CFGS[nwi]: nwpa |= WATT[s_]
            else:
                nwi = wi; nwpa = wpa
            if (ADJ[wk] >> t) & 1: continue
            if (nwpa >> t) & 1: continue
            mv.append((wk, t, nwi, bi))
        inchk = (wpa >> bk) & 1
        for src in bset:
            x, y = src % N, src // N
            for dx in (-1, 0, 1):
                nx = x+dx
                if not (0 <= nx < N): continue
                t = N*(y-1)+nx
                bt = 1 << t
                if dx == 0:                             # push
                    if (bt & wm) or (bt & bm) or inchk: continue
                    if y == 1: promo += 1   # black promo push: promo rank is always y=0 (N-independent)
                    else: mv.append((wk, bk, wi, CFG_MV_B[(bi, src, t)]))
                else:                                   # capture
                    if not (bt & wm) or t == wk: continue
                    nwi = CFG_DEL[(wi, t)]
                    nbi = CFG_MV_B[(bi, src, t)]
                    nwpa = 0
                    for s_ in CFGS[nwi]: nwpa |= WATT[s_]
                    if (nwpa >> bk) & 1: continue
                    mv.append((wk, bk, nwi, nbi))
    return mv, promo

# --------------------------------------------------- hand-verified unit checks
# (hand-solved probes reference concrete 4x4 squares; run them only at N=4)
if N == 4:
    wi9, bi0 = CID[(9,)], CID[()]
    mvW, pcW = gen(5, 13, wi9, bi0, 0)      # probe C (Kb2,Pb3 vs kb4), White to move
    mvB, pcB = gen(5, 13, wi9, bi0, 1)
    assert len(mvW)+pcW == 5 and len(mvB)+pcB == 0, "probe C move counts"
    # probe C, Black to move: every black king step is attacked/blocked -> STALEMATE net
    mvA_W, _ = gen(1, 14, CID[(4, 7)], CID[(8, 11)], 0)   # start A, White to move
    mvA_B, _ = gen(1, 14, CID[(4, 7)], CID[(8, 11)], 1)
    assert len(mvA_W) == 2 and len(mvA_B) == 2, "start A move counts"

# ------------------------------------------------------------- enumeration
NS = NK * NPP * 2
# exact per-state pawn counts (for material-class and lab analysis)
_pp_of = np.array([PP_LIST[i][0] for i in range(NPP)])
_bp_of = np.array([PP_LIST[i][1] for i in range(NPP)])
_wlen = np.array([len(CFGS[c]) for c in _pp_of], dtype=np.int8)
_blen = np.array([len(CFGS[c]) for c in _bp_of], dtype=np.int8)
sid_wcount = _wlen[(np.arange(NS) // 2) % NPP]
sid_bcount = _blen[(np.arange(NS) // 2) % NPP]

VAL   = np.full(NS, -1, dtype=np.int8)    # -1 illegal slot; 0 unknown; 1 W;2 L;3 D
INCHK = np.zeros(NS, dtype=bool)
PROMO = np.zeros(NS, dtype=bool)
STMW  = np.zeros(NS, dtype=bool)
PHI   = np.zeros(NS, dtype=np.int8)
MU    = np.zeros(NS, dtype=np.int16)
CHI   = np.zeros(NS, dtype=np.int8)
MAT   = np.zeros(NS, dtype=np.int8)
BLOCK = np.zeros(NS, dtype=bool)
MIR   = np.full(NS, -1, dtype=np.int32)
ed_src, ed_dst = [], []
from array import array
ed_src, ed_dst = array('i'), array('i')

rep(f"NK={NK} king pairs, NC={NC} configs/side, NPP={NPP} valid pawn-config pairs")
rep(f"State slots NS = NK*NPP*2 = {NS}")

nplaced = 0
for kpi, (wk, bk) in enumerate(KING_PAIRS):
    for ppi, (wi, bi) in enumerate(PP_LIST):
        wset, bset = CFGS[wi], CFGS[bi]
        # validity: pawns may not share a square with either king (the PPID
        # disjointness only covers pawn-vs-pawn). Skipped slots stay VAL=-1.
        if (1 << wk) & (CMASK[wi] | CMASK[bi]): continue
        if (1 << bk) & (CMASK[wi] | CMASK[bi]): continue
        wpa = bpa = 0
        for s_ in wset: wpa |= WATT[s_]
        for s_ in bset: bpa |= BATT[s_]
        base = (kpi * NPP + ppi) * 2
        # ---- mirror (colour-swap under (x,y)->(N-1-x,N-1-y)) ----
        # White king of the image sits at NN-1-bk, Black king at NN-1-wk.
        wset_m = tuple(sorted(NN - 1 - s_ for s_ in bset))
        bset_m = tuple(sorted(NN - 1 - s_ for s_ in wset))
        MIR[base]   = (KPID[NN-1-bk][NN-1-wk] * NPP + PPID[CID[wset_m]][CID[bset_m]]) * 2 + 1
        MIR[base+1] = MIR[base] - 1
        w_ok = not (wpa >> bk) & 1      # White to move: Black not in check
        b_ok = not (bpa >> wk) & 1
        mvW, pcW = gen(wk, bk, wi, bi, 0)
        mvB, pcB = gen(wk, bk, wi, bi, 1)
        if SKIP_INV:      # invariant layer is N-dependent SEMANTICS: not ported here
            mu, chi, blk = 0, 0, False
        else:
            mu = len(mvW) + pcW - len(mvB) - pcB
            adv_w = sum((s_ // N) - 1 for s_ in wset)
            adv_b = sum((N - 2) - (s_ // N) for s_ in bset)
            dw = min(((N - 1) - (s_ // N)) for s_ in wset) if wset else N - 1  # race distances
            db = min((s_ // N) for s_ in bset) if bset else N - 1
            chi = sum(1 if ((s_ % N) + (s_ // N)) % 2 == 0 else -1 for s_ in wset) \
                - sum(1 if ((s_ % N) + (s_ // N)) % 2 == 0 else -1 for s_ in bset)
            wm_ = CMASK[wi] | (1 << wk); bm_ = CMASK[bi] | (1 << bk)
            blk = True
            for s_ in wset:
                if not (1 << (s_+N)) & (wm_ | bm_): blk = False; break
            if blk:
                for s_ in bset:
                    if not (1 << (s_-N)) & (wm_ | bm_): blk = False; break
        mat = len(wset) - len(bset)
        nplaced += 1
        for stm in (0, 1):
            sid = base + stm
            STMW[sid] = (stm == 0)
            if not SKIP_INV:
                PHI[sid] = db - dw + (1 if stm == 0 else -1)
            MU[sid]  = mu
            CHI[sid] = chi
            MAT[sid] = mat
            BLOCK[sid] = blk
            if stm == 0 and not w_ok: continue
            if stm == 1 and not b_ok: continue
            VAL[sid] = 0
            INCHK[sid] = bool((bpa >> wk) & 1 if stm == 0 else (wpa >> bk) & 1)
            mv, pc = (mvW, pcW) if stm == 0 else (mvB, pcB)
            PROMO[sid] = pc > 0
            nxt = 1 - stm
            for (nwk, nbk, nwi, nbi) in mv:
                k2 = KPID[nwk][nbk]
                p2 = PPID[nwi][nbi]
                if k2 < 0 or p2 < 0: raise AssertionError("bad successor encode")
                ed_src.append(sid)
                ed_dst.append((k2 * NPP + p2) * 2 + nxt)

rep(f"placements enumerated: {nplaced}   ({time.time()-T0:.1f}s)")

ed_src = np.frombuffer(ed_src, dtype=np.int32)
ed_dst = np.frombuffer(ed_dst, dtype=np.int32)
NE_ = len(ed_dst)
legal_mask = VAL == 0
deg = np.bincount(ed_src, minlength=NS).astype(np.int64)
indptr = np.zeros(NS+1, dtype=np.int64); indptr[1:] = np.cumsum(deg)
indices = ed_dst
order = np.argsort(ed_dst, kind='stable')
rsrc = ed_src[order]
rptr = np.zeros(NS+1, dtype=np.int64); rptr[1:] = np.cumsum(np.bincount(ed_dst, minlength=NS))
rep(f"legal states: {int(legal_mask.sum())}   directed edges: {NE_}")

# every successor of a legal state must be a legal state (well-definedness)
assert (VAL[indices] >= 0).all(), "illegal successor encountered"

# ------------------------------------------------------------- retrograde solve
VAL[PROMO & legal_mask] = 1                              # terminal promotion = win
nomove = legal_mask & (deg == 0) & (~PROMO)
VAL[nomove & INCHK] = 2                                  # checkmate
VAL[nomove & ~INCHK] = 3                                 # stalemate
rep(f"terminal states: mates={int((VAL==2).sum())} stalemates={int((VAL==3).sum())} "
    f"immediate-promotion wins={int(((VAL==1)&PROMO).sum())}")

# pending[p] = number of successors of p not yet marked WIN.
# Initialize to deg (ALL successors counted); init-WIN states (promotions) then
# decrement their predecessors exactly once when popped. Counting them out at
# init AND decrementing later would double-count and force spurious losses.
win_pending = deg.astype(np.int64).copy()
q = deque(np.nonzero((VAL == 1) | (VAL == 2))[0].tolist())
while q:
    s = q.popleft()
    vs = VAL[s]
    if vs == 3: continue
    for p in rsrc[rptr[s]:rptr[s+1]].tolist():
        if VAL[p] != 0: continue
        if vs == 2:
            VAL[p] = 1; q.append(p)
        else:
            win_pending[p] -= 1
            if win_pending[p] == 0:
                VAL[p] = 2; q.append(p)
n_cyc = int(((VAL == 0) & legal_mask).sum())
VAL[VAL == 0] = 3                                         # cycle-draws (convention D4)
assert not (VAL[legal_mask] == 0).any(), "unresolved legal state"
rep(f"retrograde fixpoint reached ({time.time()-T0:.1f}s); unresolved -> cycle-draws = {n_cyc}")

# ------------------------------------------------------------- DTC distances
# Joint value iteration on the value-consistent subgraph:
#   WIN : DTC = min(1 [promo], 1 + min over LOSS successors)
#   LOSS: DTC = 1 + max over WIN successors   (defender's maximal resistance)
# Anchors: terminal mates = 0, immediate promotions = 1. Iteration from above
# is monotone and converges to the unique game-theoretic distance.
BIG = 1 << 30
DTC = np.full(NS, BIG, dtype=np.int64)
DTC[(VAL == 2) & (deg == 0)] = 0                # mates: conversion complete
DTC[(VAL == 1) & PROMO] = 1                     # promotion: converts in 1 ply
edge_val = VAL[indices]   # gather (copy), values -1..3 only: identical comparisons, 1/8 the bytes
red = np.clip(indptr[:-1], 0, max(NE_ - 1, 0))  # reduceat segment starts
win_m = (VAL == 1); loss_m = (VAL == 2) & (deg > 0)
for sweep in range(400):
    # memory hygiene (identical math): one shared gather instead of two
    d_idx = DTC[indices]; d_idx += 1
    wL = np.where(edge_val == 2, d_idx, BIG)              # min-reduce -> WIN
    wW = np.where(edge_val == 1, d_idx, -1)               # max-reduce -> LOSS
    del d_idx
    mn = np.minimum.reduceat(wL, red)
    mx = np.maximum.reduceat(wW, red)
    del wL, wW
    changed = False
    nw_ = np.minimum(DTC[win_m], mn[win_m])
    if not np.array_equal(nw_, DTC[win_m]): changed = True
    DTC[win_m] = nw_
    nl_ = mx[loss_m]
    if not np.array_equal(nl_, DTC[loss_m]): changed = True
    DTC[loss_m] = nl_
    if not changed: break
else:
    raise AssertionError("DTC value iteration did not converge")
assert (DTC[VAL == 1] >= 1).all() and (DTC[VAL == 1] < BIG).all()
assert (DTC[VAL == 2] >= 0).all() and (DTC[VAL == 2] < BIG).all()
DTC[VAL == 3] = -1
DTC[VAL == -1] = -1
rep(f"DTC iteration converged in {sweep+1} sweeps; max DTC = "
    f"{int(DTC[VAL != 3].max())} plies (over decided states)")

# ---- board diagram helper (moved up for self-test diagnostics) ----
def diagram(sid):
    kpi = sid // (2*NPP); ppi = (sid // 2) % NPP; stm = sid % 2
    wk, bk = KING_PAIRS[kpi]; wi, bi = PP_LIST[ppi]
    grid = [['.'] * N for _ in range(N)]
    grid[wk // N][wk % N] = 'K'; grid[bk // N][bk % N] = 'k'
    for s_ in CFGS[wi]: grid[s_ // N][s_ % N] = 'P'
    for s_ in CFGS[bi]: grid[s_ // N][s_ % N] = 'p'
    out = ["   " + " ".join(chr(ord('a') + x) for x in range(N))]
    for y in range(N - 1, -1, -1):
        out.append(f" {y+1} " + " ".join(grid[y]) + f"  {['White','Black'][stm]} to move")
    v = int(VAL[sid]); d = int(DTC[sid])
    vs = {'W': 'White wins', 'D': 'draw', 'B': 'Black wins'}[v == 1 and 'W' or v == 2 and 'B' or 'D']
    out.append(f"   value: {vs}{'  (DTC ' + str(d) + ')' if v in (1, 2) and d >= 0 else ''}"
               f"  phi={int(PHI[sid])} mu={int(MU[sid])} chi={int(CHI[sid])} block={bool(BLOCK[sid])}")
    return "\n".join(out)

# ------------------------------------------------------------- self-tests
FLIP = np.array([-1, 0, 2, 1, 3], dtype=np.int8)   # indexed by VAL+1: -1,0,1,2,3
lm_idx = np.nonzero(legal_mask)[0]
assert (MIR[lm_idx] >= 0).all(), "mirror of a legal state is illegal"
mir_l = MIR[lm_idx]
# Mover-centric value is PRESERVED by the colour-swap mirror (colours AND stm
# are exchanged, so the mover stays the mover); White-oriented functionals anti-flip.
bad = np.nonzero(VAL[mir_l] != VAL[lm_idx])[0]
assert len(bad) == 0, f"colour-swap symmetry violated in {len(bad)} states"
if not SKIP_INV:   # meaningful only when the invariant layer was computed
    assert (PHI[mir_l] == -PHI[lm_idx]).all() and (MU[mir_l] == -MU[lm_idx]).all() \
        and (CHI[mir_l] == -CHI[lm_idx]).all()
ow = np.where(STMW, VAL, FLIP[VAL + 1]).astype(np.int8)   # outcome for White
ow_m = np.where(STMW[mir_l], VAL[mir_l], FLIP[VAL[mir_l] + 1]).astype(np.int8)
assert (ow_m == FLIP[ow[lm_idx] + 1]).all(), "outcome-for-White must anti-flip"
kvk_mask = legal_mask & (sid_wcount == 0) & (sid_bcount == 0)
assert (VAL[kvk_mask] == 3).all(), "K vs K must be all draws"
# structural validity: no legal state has a pawn on a king square
_kmask_of = np.array([(1 << k[0]) | (1 << k[1]) for k in KING_PAIRS], dtype=np.int32)
_cmask_of = np.array([CMASK[w] | CMASK[b] for w, b in PP_LIST], dtype=np.int32)
slot_ok = ((_kmask_of[:, None] & _cmask_of[None, :]) == 0).reshape(-1)
slot_ok = np.repeat(slot_ok, 2)
assert (slot_ok[legal_mask]).all(), "pawn-on-king-square state present"
nw_ = int((legal_mask & (VAL == 1) & STMW).sum()); nb_ = int((legal_mask & (VAL == 1) & ~STMW).sum())
assert nw_ == nb_, "colour-swap symmetry: win counts differ"
rep("self-tests: mirror symmetry OK; phi/mu/chi anti-symmetry OK; K-vs-K all draws OK")

# probe C ground truth (hand-solved): White to move WINS in 3; Black to move is STALEMATE
def sid_of(wk, bk, wset, bset, stm):
    return (KPID[wk][bk] * NPP + PPID[CID[tuple(sorted(wset))]][CID[tuple(sorted(bset))]]) * 2 + stm
if N == 4:   # hand-solved 4x4 ground truth (skip at other N)
    pcW_sid = sid_of(5, 13, (9,), (), 0)
    pcB_sid = sid_of(5, 13, (9,), (), 1)
    rep(f"probe C (Kb2,Pb3 vs kb4): White to move -> {'WLD'[VAL[pcW_sid]-1]} DTC={DTC[pcW_sid]}; "
        f"Black to move -> {'WLD'[VAL[pcB_sid]-1]}")
    assert VAL[pcW_sid] == 1 and DTC[pcW_sid] == 3 and VAL[pcB_sid] == 3, "probe C ground truth"

# ------------------------------------------------------------- analysis helpers
# (ow defined in self-tests section)
L = legal_mask


def purity_table(f, mask, name, min_n=1, bins=None):
    fv = f[mask].astype(np.int64); ov = ow[mask]
    if bins is not None:
        idx = np.digitize(fv, bins)                    # 0 .. len(bins)
        def lab(i):
            if i == 0: return f"<={bins[0]}"
            if i == len(bins): return f">{bins[-1]}"
            return f"{bins[i-1]+1}..{bins[i]}"
        ng = len(bins) + 1
    else:
        vals_u, idx = np.unique(fv, return_inverse=True)
        labels = [str(int(v)) for v in vals_u]
        ng = len(vals_u)
        def lab(i): return labels[i]
    rep(f"\n  contingency {name} x outcome-for-White:")
    rep("    value        n     White+   draw    Black+   purity")
    for i in range(ng):
        m2 = idx == i
        n = int(m2.sum())
        if n < min_n: continue
        cw = int((ov[m2] == 1).sum()); cd = int((ov[m2] == 3).sum()); cb = int((ov[m2] == 2).sum())
        rep(f"    {lab(i):>8} {n:>9} {cw:>9} {cd:>7} {cb:>8}   {max(cw,cd,cb)/n:.3f}")
    return idx

def best_partition_accuracy(f, mask):
    fv = f[mask].astype(np.int64); ov = ow[mask]
    vals = np.unique(fv)
    cnt = np.zeros((len(vals), 3), dtype=np.int64)
    vpos = {v: i for i, v in enumerate(vals)}
    for v, o in zip(fv.tolist(), ov.tolist()):
        cnt[vpos[v]][{1: 0, 2: 1, 3: 2}[o]] += 1
    tot = cnt.sum()
    K = len(vals)
    best, bt = 0.0, None
    cpre = np.zeros((K+1, 3), dtype=np.int64); cpre[1:] = np.cumsum(cnt, axis=0)
    for i in range(K+1):
        for j in range(i, K+1):
            a = cpre[i]; b = cpre[j]-cpre[i]; c = cpre[K]-cpre[j]
            acc = 0
            for seg in (a, b, c):
                if seg.sum(): acc += seg.max()
            if acc > best: best, bt = acc, (i, j)
    return best/tot, (int(vals[bt[0]]) if bt[0] < K else None, int(vals[bt[1]]) if bt[1] < K else None)

def examples(mask, k=3, title=""):
    ids = np.nonzero(mask)[0]
    rep(f"\n  [{title}]  total={len(ids)}")
    if len(ids) == 0: return
    step = max(1, len(ids)//k)
    for sid in ids[::step][:k]:
        rep("  " + diagram(int(sid)).replace("\n", "\n  "))

# ------------------------------------------------------------- global results
nw = int((ow[L] == 1).sum()); nd = int((ow[L] == 3).sum()); nb = int((ow[L] == 2).sum())
rep(f"\n== VALUE DISTRIBUTION ==  White wins {nw} ({100*nw/L.sum():.2f}%) | "
    f"draws {nd} ({100*nd/L.sum():.2f}%) | Black wins {nb} ({100*nb/L.sum():.2f}%)")

rep("\n== VALUE BY MATERIAL CLASS (white pawn count x black pawn count) ==")
rep("   WxB      n     White+     draw    Black+   draw%")
for a in (2, 1, 0):
    for b in (2, 1, 0):
        m = L & (sid_wcount == a) & (sid_bcount == b)
        n = int(m.sum())
        if n == 0: continue
        rep(f"   {a}x{b} {n:>9} {int((ow[m]==1).sum()):>9} {int((ow[m]==3).sum()):>8} "
            f"{int((ow[m]==2).sum()):>9}  {100*(ow[m]==3).mean():5.1f}%")

# ------------------------------------------------------------- zugzwang stats
bases = np.arange(0, NS, 2)
both = (VAL[bases] >= 1) & (VAL[bases+1] >= 1)
mz = bases[(VAL[bases] == 2) & (VAL[bases+1] == 2)]
fpw = bases[(VAL[bases] == 1) & (VAL[bases+1] == 1)]
ob0 = ow[bases]; ob1 = ow[bases+1]
ts = bases[both & (ob0 != ob1)]
rep(f"\n== TEMPO STRUCTURE (placements with both tempi legal: {int(both.sum())}) ==")
rep(f"  mutual zugzwang placements (mover LOSES with either tempo): {len(mz)}")
rep(f"  first-player-win placements (mover WINS with either tempo):  {len(fpw)}")
rep(f"  tempo-sensitive placements (outcome-for-White flips with tempo): {len(ts)}")
pairs = {}
for s_ in ts:
    key = (int(ow[s_]), int(ow[s_+1]))
    pairs[key] = pairs.get(key, 0) + 1
rep("  tempo-sensitive breakdown (outcome W-to-move, outcome B-to-move): "
    + str(sorted(pairs.items(), key=lambda x: -x[1])[:6]))

# ------------------------------------------------------------- candidate tests
# (falsifier/invariant labs are N-dependent semantics: skipped by default)
if not SKIP_INV:
    rep("\n== CANDIDATE A: race potential phi (N-dependent definition; not ported) ==")
    purity_table(PHI, L, "phi")
    acc, thr = best_partition_accuracy(PHI, L)
    rep(f"  best 3-interval partition accuracy: {acc:.4f} at thresholds {thr}")
    rep("  predicted failure class: phi=+3 (max) not pure -> blockade-zugzwang inversion")
    examples(L & (PHI == 3) & (ow != 1), 3, "falsifiers: phi=+3 but White does NOT win")

    rep("\n== CANDIDATE B: mobility differential mu = m_W - m_B ==")
    purity_table(MU, L, "mu", min_n=400, bins=[-8, -4, -1, 0, 3, 7])
    accb, thrb = best_partition_accuracy(MU, L)
    rep(f"  best 3-interval partition accuracy: {accb:.4f} at thresholds {thrb}")
    examples(L & (MU <= -6) & (ow == 1), 3, "falsifiers: mu<=-6 (White low mobility) but White WINS")

    rep("\n== CANDIDATE C (control): checker signature chi ==")
    purity_table(CHI, L, "chi")
    accc, thrc = best_partition_accuracy(CHI, L)
    rep(f"  best 3-interval partition accuracy: {accc:.4f}")

    # blocked-structure lab
    rep("\n== ZUGZWANG LAB: fully push-blocked structures (BLOCK=True) ==")
    mb = L & BLOCK
    rep(f"  n={int(mb.sum())}  White+ {int((ow[mb]==1).sum())}  draw {int((ow[mb]==3).sum())}  "
        f"Black+ {int((ow[mb]==2).sum())}")
    rep(f"  decided (non-draw) share: {100*(ow[mb]!=3).mean():.2f}%  vs  "
        f"{100*(ow[L]!=3).mean():.2f}% over all legal states")
    mz_pl = set(mz.tolist()) | set((mz+1).tolist())
    rep(f"  mutual-zugzwang states lying in blocked structures: "
        f"{sum(1 for s in mz_pl if BLOCK[s])} of {len(mz_pl)}")

# 1v0 promotion-race lab + parity teaser
one0 = L & (sid_wcount == 1) & (sid_bcount == 0)
rep(f"\n== LAB: K+P vs K (n={int(one0.sum())})  White+ {int((ow[one0]==1).sum())}  "
    f"draw {int((ow[one0]==3).sum())}  Black+ {int((ow[one0]==2).sum())}")
wmx = L & (sid_wcount == 1) & (sid_bcount == 0) & STMW
rep(f"  with White to move: White wins {100*(ow[wmx]==1).mean():.2f}%  "
    f"(n={int(wmx.sum())})")

# parity teaser: in the 1-pawn blockade class, does king-parity carry signal?
if not SKIP_INV:   # uses PHI (invariant layer)
    kpi_of = (np.arange(NS) // (2*NPP))
    wk_arr = np.array([KING_PAIRS[i][0] for i in range(NK)])
    bk_arr = np.array([KING_PAIRS[i][1] for i in range(NK)])
    wkv = wk_arr[kpi_of]; bkv = bk_arr[kpi_of]
    par = ((np.abs((wkv % N) - (bkv % N)) + np.abs((wkv // N) - (bkv // N))) % 2).astype(np.int8)
    lab2 = L & (sid_wcount == 1) & (sid_bcount == 0) & (PHI >= 2)
    rep("  parity teaser: outcome vs (king Manhattan distance mod 2), single white pawn, phi>=2")
    purity_table(par, lab2, "parity", min_n=1)

# ------------------------------------------------------------- start probes
if N == 4:   # 4x4 hand-picked probe diagrams (skip at other N)
    rep("\n== PROBE POSITIONS ==")
    for name, pargs in [("A  Kb1,Pa2,Pd2 vs kc4,pa3,pd3 (self-mirror, all pawns blocked)", (1, 14, (4, 7), (8, 11))),
                        ("B  Kb1,Pb2,Pc2 vs kc4,pb3,pc3 (self-mirror, mutual captures)", (1, 14, (5, 6), (9, 10))),
                        ("C  Kb2,Pb3 vs kb4 (1v0 blockade/stalemate probe)", (5, 13, (9,), ()))]:
        rep(f"  probe {name}")
        for stm in (0, 1):
            sid = sid_of(*pargs, stm)
            rep("  " + diagram(sid).replace("\n", "\n  "))

# ------------------------------------------------------------- DTC summary
dts = DTC[L & (VAL == 1)]
rep(f"\n== DTC (plies to conversion, optimal play) ==  White wins: max {dts.max()}, "
    f"mean {dts.mean():.2f};  deepest state:")
rep("  " + diagram(int(np.nonzero(L & (DTC == DTC[L].max()))[0][0])).replace("\n", "\n  "))

np.savez_compressed(OUT_NPZ, VAL=VAL, DTC=DTC, PHI=PHI, MU=MU, CHI=CHI, MAT=MAT,
                    BLOCK=BLOCK, MIR=MIR, STMW=STMW)
rep(f"\narrays saved -> {OUT_NPZ}")
rep(f"total runtime {time.time()-T0:.1f}s  |  python {platform.python_version()} numpy {np.__version__}")

with open(OUT_TXT, "w") as fh:
    fh.write("\n".join(R) + "\n")
rep(f"report saved -> {OUT_TXT}")
