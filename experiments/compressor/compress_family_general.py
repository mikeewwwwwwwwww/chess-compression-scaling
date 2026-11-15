# scripts_general/compress_family_general.py - N-parameterized orbit-canonical
# MTBDD compressor for the K2P family evaluators, generalized from the repo's
# scripts/compress_1v1_duel.py / compress_asym3.py / compress_4p_2v2.py
# (commit 76ba614).  Lives OUTSIDE the repo; repo files are never written.
#
# Families (masks partition the legal space exactly, per repo gen_4p.py):
#   duel      : |W| <= 1 and |B| <= 1                (repo DUEL, 5-tuple states)
#   asym_3p   : (|W|,|B|) in {(1,2),(2,1),(2,0),(0,2)}  (repo F3, 7-tuple states)
#   four_pawn : |W| == 2 and |B| == 2                (repo F4P, 7-tuple states;
#   2x2         alias of four_pawn)
#   full      : ALL legal states in one MTBDD over the 7-tuple encoding, with the
#               memory fallback ladder  full -> 2x2-only -> stratified sample.
#   all       : per-family builds (duel, asym_3p, four_pawn) + router total.
#
# N-parameterization: every board literal of the 4x4 original is derived from N
# (--n).  The EMITTED evaluator gets N as hardcoded literals (no variables):
# feat_lines()/enc_expr()/the canonicalization block take N and substitute at
# emission time.  At N == 4 the emitted strings are byte-identical to the repo's
# emitters (the XOR/shift spellings q^3, &3, >>2 are exact at N=4); at N != 4 the
# general arithmetic ((q//N)*N + (N-1-q%N) etc.) is emitted with folded literals.
#
# Assert policy (per instruction): n_canon / bare / non-bare count asserts are
# REMOVED and REPORTED instead (orbit sizes < 4 are possible at N=5 because H
# fixes the middle file when N is odd).  'assert hom_bad == 0' (value
# homogeneity) and 'assert len(conf_full) == 0' (feature discriminativeness)
# are KEPT - they must hold at any N.
#
# K2P+N feature extension (--feature-extension knights): appends the shared 13-
# feature knight block (k2pn_basis.py, single source of truth) AFTER the semantic
# features and BEFORE the canonical-coordinate tail.  K2P family states contain
# no knights, so every extended feature is CONSTANT (nW=nB=0, k_dist=k_*_own=
# k_*_enemy=99, katt=kchk=k_atk=0); constant levels collapse in the MTBDD build
# and are pruned from emission, so nodes/rows/verification are IDENTICAL to the
# non-extension build - the extension is exercised end-to-end here and the same
# block carries real knight coordinates in the K2P+N class pipeline
# (k2pn_classes.py / z3_injectivity.py / compress_class_k2pn.py).
import argparse, gc, json, os, subprocess, sys, time
from bisect import bisect_right
from collections import defaultdict
from itertools import combinations

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import k2pn_basis

T0 = time.time()
R = []
def P(*a):
    s = " ".join(str(x) for x in a)
    R.append(s); print(s, flush=True)

ap = argparse.ArgumentParser(
    description="N-parameterized orbit-canonical MTBDD compressor for K2P families "
                "(generalized copy of the repo's compress_1v1_duel.py pipeline).")
ap.add_argument("--n", type=int, default=4, help="board edge N (board is NxN)")
ap.add_argument("--family", default="duel",
                choices=["duel", "asym_3p", "four_pawn", "2x2", "all", "full"],
                help="family to compile (2x2 = alias of four_pawn; all = the three "
                     "per-family builds + router total; full = single MTBDD over ALL "
                     "legal states with fallback ladder full -> 2x2-only -> sample)")
ap.add_argument("--labels-npz", default=None,
                help="npz holding the family mask and/or mover-relative labels "
                     "(default: repo download/ phase6c/7a/7b npz at N=4; "
                     "<script dir>/out_n{N}/phase1_values.npz at N!=4)")
ap.add_argument("--labels-key", default=None,
                help="array in labels-npz holding mover-relative labels "
                     "(default: DUEL_MV/ASYM3_MV/F4P_MV at N=4 per family, VAL otherwise)")
ap.add_argument("--out-dir", default=None, help="default ./compress_n{N}/")
ap.add_argument("--emit-dir", default=None, help="default ./compress_n{N}/")
ap.add_argument("--sample", type=int, default=500000,
                help="stratified sample size for the ladder's last resort")
ap.add_argument("--seed", type=int, default=7, help="sampling seed")
ap.add_argument("--tree-line-limit", type=int, default=200000)
ap.add_argument("--verify-limit", type=int, default=0,
                help="cap on states verified by the subprocess (0 = verify all; "
                     "a cap is reported as subset verification)")
ap.add_argument("--mem-ceiling-mib", type=int, default=3400,
                help="abort cleanly when VmRSS would exceed this (sandbox has 4 GB)")
ap.add_argument("--skip-winloss", action="store_true",
                help="skip the boolean win/loss BDD builds (auto for large row counts)")
ap.add_argument("--force-sampled", action="store_true",
                help="skip the full-family attempt; compile the stratified/uniform sample directly")
ap.add_argument("--no-ladder", action="store_true",
                help="--family full: attempt the full space only; report an abort instead of "
                     "falling back in-process (fallbacks are then driven as separate runs)")
ap.add_argument("--trace", action="store_true",
                help="E3 diagnostic: after the MTBDD build, walk the deepest root-to-leaf "
                     "path (deepest child, ties -> smallest branch value), emit "
                     "trace_<family>_<mode>.json, and skip emission/verification/"
                     "summary updates entirely")
ap.add_argument("--feature-extension", default="none",
                choices=["none", "knights"],
                help="append the 13-feature K2P+N knight block (k2pn_basis.py) after the "
                     "semantic features and before the coordinate tail; on the knight-free "
                     "K2P families every knight feature is constant, so the build must "
                     "degenerate to the plain K2P basis (checked)")
args = ap.parse_args()
if args.n < 2:
    ap.error("--n must be >= 2")
N = args.n
NN = N * N
RAD_P = NN + 1                    # pawn radix: pawn square + 1 (absent = 0)
FAM = args.family if args.family != "2x2" else "four_pawn"
if args.out_dir is None: args.out_dir = os.path.join(".", f"compress_n{N}")
if args.emit_dir is None: args.emit_dir = os.path.join(".", f"compress_n{N}")
os.makedirs(args.out_dir, exist_ok=True); os.makedirs(args.emit_dir, exist_ok=True)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
P(f"config: N={N} family={FAM} out_dir={args.out_dir} emit_dir={args.emit_dir} "
  f"feature_extension={args.feature_extension}")

# ---------------------------------------------------------------- K2P+N extension
EXT_KNIGHTS = (args.feature_extension == "knights")
# Knight features of a state with NO knights: must be state-independent (checked
# below over all king pairs / pawn placements), otherwise K2P families could not
# carry the block at all.
KNIGHT_BLOCK = tuple(int(v) for v in
                     k2pn_basis.knight_feats(0, 0, 0, 0, -1, -1, N))
KNIGHT_NAMES = list(k2pn_basis.KNIGHT_NAMES)
for _probe_wk, _probe_bk, _probe_wp, _probe_bp in ((0, NN - 1, -1, -1),
                                                   (NN - 1, 0, 1, 2),
                                                   (0, NN - 1, NN - 2, -1)):
    _pv = tuple(int(v) for v in
                k2pn_basis.knight_feats(_probe_wk, _probe_bk, _probe_wp, _probe_bp,
                                        -1, -1, N))
    assert _pv == KNIGHT_BLOCK, "knight feature block not constant at 0 knights"

def ext_names(base, tail):
    """feature names with the knight block inserted before the tail."""
    return (list(base) + KNIGHT_NAMES + list(tail)) if EXT_KNIGHTS else \
           (list(base) + list(tail))

def ext_sem(base_n):
    """semantic feature count under the extension."""
    return base_n + (len(KNIGHT_NAMES) if EXT_KNIGHTS else 0)

def ext_feat(f_sem, f_tail):
    """assemble (semantic ++ knight block ++ tail) for one canonical state."""
    if not EXT_KNIGHTS:
        return tuple(f_sem) + tuple(f_tail)
    return tuple(f_sem) + KNIGHT_BLOCK + tuple(f_tail)

def guard_feat_lines(fn, knight_idx, tag):
    def wrapped(used):
        bad = knight_idx & set(used)
        if bad:
            raise AssertionError(
                f"knight features {sorted(bad)} appear in `used` for a K2P family "
                f"({tag}) - they are constant and must have collapsed in the build")
        return fn(used)
    return wrapped

# ---------------------------------------------------------------- enumeration
# (N-parameterized 6a indexing block, same semantics as repo scripts/common_k2p.py)
NEI, ADJ = [], [0] * NN
for s in range(NN):
    x, y = s % N, s // N
    lst = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == dy == 0: continue
            nx, ny = x + dx, y + dy
            if 0 <= nx < N and 0 <= ny < N: lst.append(N * ny + nx)
    NEI.append(tuple(lst)); ADJ[s] = sum(1 << t for t in lst)
PAWN_SQS = tuple(N * y + x for y in range(1, N - 1) for x in range(N))
KING_PAIRS = [(wk, bk) for wk in range(NN) for bk in range(NN)
              if wk != bk and not ((ADJ[wk] >> bk) & 1)]
CFGS = [()]
for r in (1, 2): CFGS += list(combinations(PAWN_SQS, r))
CID = {cfg: i for i, cfg in enumerate(CFGS)}
PP_LIST = [(wi, bi) for wi, wc in enumerate(CFGS) for bi, bc in enumerate(CFGS)
           if not (set(wc) & set(bc))]
NPP = len(PP_LIST)
PPI = {pp: i for i, pp in enumerate(PP_LIST)}
KPI = {kp: i for i, kp in enumerate(KING_PAIRS)}
NS = len(KING_PAIRS) * NPP * 2
sid_arr = np.arange(NS, dtype=np.int64)
stm_of = (sid_arr % 2).astype(np.int8)
WK = np.array([k[0] for k in KING_PAIRS], dtype=np.int64)[sid_arr // (2 * NPP)]
BK = np.array([k[1] for k in KING_PAIRS], dtype=np.int64)[sid_arr // (2 * NPP)]
wi_slot = np.array([p[0] for p in PP_LIST], dtype=np.int64)[(sid_arr // 2) % NPP]
bi_slot = np.array([p[1] for p in PP_LIST], dtype=np.int64)[(sid_arr // 2) % NPP]
c1 = np.full(len(CFGS), -1, dtype=np.int8); c2 = np.full(len(CFGS), -1, dtype=np.int8)
for i, c in enumerate(CFGS):
    if len(c) >= 1: c1[i] = c[0]
    if len(c) == 2: c2[i] = c[1]
W1 = c1[wi_slot].astype(np.int64); W2 = c2[wi_slot].astype(np.int64)
B1 = c1[bi_slot].astype(np.int64); B2_ = c2[bi_slot].astype(np.int64)
wn_cnt = ((W1 >= 0).astype(np.int8) + (W2 >= 0).astype(np.int8))
bn_cnt = ((B1 >= 0).astype(np.int8) + (B2_ >= 0).astype(np.int8))
assert NS == len(KING_PAIRS) * NPP * 2

# fast arithmetic sid lookup: config index for the sort7/sort5 pawn conventions
PW2ID = {}
for ci, c in enumerate(CFGS):
    if len(c) == 0: PW2ID[(-1, -1)] = ci
    elif len(c) == 1: PW2ID[(-1, c[0])] = ci
    else: PW2ID[(c[0], c[1])] = ci
PPI2 = np.full((len(CFGS), len(CFGS)), -1, dtype=np.int32)
for (wi, bi), i in PPI.items(): PPI2[wi, bi] = i
KPI2 = np.full((NN, NN), -1, dtype=np.int32)
for (wk, bk), i in KPI.items(): KPI2[wk, bk] = i

def sid7(wk, bk, w1, w2, b1, b2, tau):
    """sid of a 7-tuple; pawn pairs sorted ascending (absent -1 sorts FIRST),
    matching the PW2ID convention regardless of caller order."""
    if w1 > w2: w1, w2 = w2, w1
    if b1 > b2: b1, b2 = b2, b1
    return (int(KPI2[wk, bk]) * NPP + int(PPI2[PW2ID[(w1, w2)], PW2ID[(b1, b2)]])) * 2 + int(tau)

def sid5(w, b, pw, pb, tau):
    """sid of a duel 5-tuple (-1 = absent pawn)."""
    wkey = (-1, pw) if pw >= 0 else (-1, -1)
    bkey = (-1, pb) if pb >= 0 else (-1, -1)
    return (int(KPI2[w, b]) * NPP + int(PPI2[PW2ID[wkey], PW2ID[bkey]])) * 2 + int(tau)

def unpack(s):
    return int(WK[s]), int(BK[s]), wset_of(s), bset_of(s), int(stm_of[s])
def wset_of(s): return frozenset(int(q) for q in (W1[s], W2[s]) if q >= 0)
def bset_of(s): return frozenset(int(q) for q in (B1[s], B2_[s]) if q >= 0)

def sort7(wk, bk, ws, bs, stm):
    """Ascending pawn pairs; absent (-1) sorts FIRST (canonical convention shared
    by t_H / t_V and the emitted evaluator's input sort)."""
    wl = sorted(ws); bl = sorted(bs)
    if len(wl) == 0:   w1 = w2 = -1
    elif len(wl) == 1: w1 = -1; w2 = wl[0]
    else:              w1 = wl[0]; w2 = wl[1]
    if len(bl) == 0:   b1 = b2 = -1
    elif len(bl) == 1: b1 = -1; b2 = bl[0]
    else:              b1 = bl[0]; b2 = bl[1]
    return (wk, bk, w1, w2, b1, b2, stm)

# ---------------------------------------------------------------- labels / masks
REPO_DL = "/home/z/my-project/research/k2p/k2p-algebraic-closure/download"
DEF_LBL = {4: {"duel": os.path.join(REPO_DL, "phase6c_duel_results.npz"),
               "asym_3p": os.path.join(REPO_DL, "phase7a_asym3_results.npz"),
               "four_pawn": os.path.join(REPO_DL, "phase7b_4p_results.npz")}}
DEF_MASK_KEY = {4: {"duel": "DUEL", "asym_3p": "F3", "four_pawn": "F4P"}}
DEF_MV_KEY = {4: {"duel": "DUEL_MV", "asym_3p": "ASYM3_MV", "four_pawn": "F4P_MV"}}
DEF_PHASE = {4: {"duel": "6c", "asym_3p": "7a", "four_pawn": "7b"}}

ORACLE_NPZ = os.path.join(SCRIPT_DIR, f"out_n{N}", "phase1_values.npz") if N != 4 \
    else os.path.join(REPO_DL, "phase1_values.npz")
_Z = np.load(ORACLE_NPZ)
VAL_ORACLE = _Z["VAL"]; STMW_ORACLE = _Z["STMW"]
LEGAL = VAL_ORACLE >= 1
FLIPV = np.array([-1, 0, 2, 1, 3], dtype=np.int8)
_OW = np.where(STMW_ORACLE, VAL_ORACLE, FLIPV[np.clip(VAL_ORACLE + 1, 0, 4)]).astype(np.int8)
OW3 = np.where(_OW == 1, 1, np.where(_OW == 2, -1, 0)).astype(np.int8); OW3[~LEGAL] = 0
PSI = None
_psi_path = os.path.join(REPO_DL, "phase7b_results.npz")
if N == 4 and os.path.exists(_psi_path):
    _pz = np.load(_psi_path)["PSI_V7B"]
    if _pz.shape == VAL_ORACLE.shape: PSI = _pz
P(f"oracle npz: {ORACLE_NPZ}  legal {int(LEGAL.sum()):,}  "
  f"Psi_v7b break-check: {'available' if PSI is not None else 'n/a (N!=4)'}")

def family_mask(fam, lbl=None):
    """Family mask: repo mask array when present, else derived from the material
    signature of each state (wn, bn pawn counts) over the legal space.
    Returns (mask, mask_key-or-None)."""
    if lbl is not None and fam in DEF_MASK_KEY.get(N, {}) and DEF_MASK_KEY[N][fam] in lbl.files:
        return lbl[DEF_MASK_KEY[N][fam]].astype(bool), DEF_MASK_KEY[N][fam]
    if fam == "full":
        return LEGAL, None
    legal = LEGAL
    if fam == "duel":      m = legal & (wn_cnt <= 1) & (bn_cnt <= 1)
    elif fam == "asym_3p": m = legal & (((wn_cnt == 1) & (bn_cnt == 2)) | ((wn_cnt == 2) & (bn_cnt == 1))
                                        | ((wn_cnt == 2) & (bn_cnt == 0)) | ((wn_cnt == 0) & (bn_cnt == 2)))
    elif fam == "four_pawn": m = legal & (wn_cnt == 2) & (bn_cnt == 2)
    else: raise ValueError(fam)
    return m, None

def load_labels(fam):
    path = args.labels_npz or DEF_LBL.get(N, {}).get(fam) or \
        os.path.join(SCRIPT_DIR, f"out_n{N}", "phase1_values.npz")
    key = args.labels_key or DEF_MV_KEY.get(N, {}).get(fam) or "VAL"
    lbl = np.load(path)
    mv = lbl[key]
    conv = "mv{0=draw,1=win,2=loss}"
    uniq = set(int(v) for v in np.unique(mv))
    if key == "VAL" or 3 in uniq:
        # VAL convention {1=win,2=loss,3=draw} -> MV convention {0=draw,1=win,2=loss}
        mv = np.where(mv == 3, 0, np.where(mv >= 1, mv, -1)).astype(np.int8)
        conv = "VAL{1=win,2=loss,3=draw} -> mv{0=draw,1=win,2=loss}"
    mask, mask_key = family_mask(fam, lbl)
    P(f"labels: {path} [{key}] -> {conv}; family mask [{mask_key or 'derived(wn,bn)'}] = {int(mask.sum()):,} states")
    return mask, mv.astype(np.int8), key, path, mask_key

# ---------------------------------------------------------------- RSS / stages
def rss_mib():
    d = {}
    for line in open("/proc/self/status"):
        if line.startswith(("VmRSS:", "VmHWM:")):
            k, v = line.split(":"); d[k.strip()] = int(v.strip().split()[0]) / 1024.0
    return round(d.get("VmRSS", 0.0), 1), round(d.get("VmHWM", 0.0), 1)

STAGES = []
def stage_mark(label):
    r, h = rss_mib()
    STAGES.append({"stage": label, "rss_mib": r, "peak_mib": h, "t_s": round(time.time() - T0, 1)})
    P(f"   [stage] {label:24} rss {r:7.1f} MiB  peak {h:7.1f} MiB  t={time.time()-T0:6.1f}s")
    return h

class MemoryCeiling(Exception):
    def __init__(self, stage): self.stage = stage; super().__init__(stage)

def mem_guard(stage):
    r, _ = rss_mib()
    if r > args.mem_ceiling_mib:
        raise MemoryCeiling(f"{stage} (rss {r:.0f} MiB > ceiling {args.mem_ceiling_mib} MiB)")

# ================================================================ orbit machinery
# H: file reflection x -> N-1-x (tau preserved);  V': rank reflection y -> N-1-y
# with W<->B color swap and tau -> 1-tau.  At N=4 H_q(q)=q^3 exactly; the general
# form is used at build time for every N (identical values at N=4).
def H_q(q):  return (q // N) * N + (N - 1 - q % N) if q >= 0 else -1
def V_q(q):  return (q % N) + N * (N - 1 - q // N) if q >= 0 else -1

def enc5(w, b, pw, pb, tau):
    return ((((w * NN + b) * RAD_P + (pw + 1)) * RAD_P + (pb + 1)) * 2 + tau)
def dec5(c):
    t = c
    ctau = t % 2; t //= 2
    cpb = t % RAD_P - 1; t //= RAD_P
    cpw = t % RAD_P - 1; t //= RAD_P
    cbk = t % NN; t //= NN
    return (t, cbk, cpw, cpb, ctau)
def t_H5(st):
    w, b, pw, pb, tau = st
    return (H_q(w), H_q(b), H_q(pw), H_q(pb), tau)
def t_V5(st):
    w, b, pw, pb, tau = st
    return (V_q(b), V_q(w), V_q(pb), V_q(pw), 1 - tau)

def enc7(wk, bk, w1, w2, b1, b2, tau):
    return ((((((wk * NN + bk) * RAD_P + (w1 + 1)) * RAD_P + (w2 + 1)) * RAD_P
              + (b1 + 1)) * RAD_P + (b2 + 1)) * 2 + tau)
def dec7(c):
    t = c
    ctau = t % 2; t //= 2
    cb2 = t % RAD_P - 1; t //= RAD_P
    cb1 = t % RAD_P - 1; t //= RAD_P
    cw2 = t % RAD_P - 1; t //= RAD_P
    cw1 = t % RAD_P - 1; t //= RAD_P
    cbk = t % NN; t //= NN
    return (t, cbk, cw1, cw2, cb1, cb2, ctau)
def t_H7(st):
    wk, bk, w1, w2, b1, b2, tau = st
    w1h, w2h = H_q(w1), H_q(w2)
    if w1h > w2h: w1h, w2h = w2h, w1h
    b1h, b2h = H_q(b1), H_q(b2)
    if b1h > b2h: b1h, b2h = b2h, b1h
    return (H_q(wk), H_q(bk), w1h, w2h, b1h, b2h, tau)
def t_V7(st):
    wk, bk, w1, w2, b1, b2, tau = st
    w1v, w2v = V_q(b1), V_q(b2)
    if w1v > w2v: w1v, w2v = w2v, w1v
    b1v, b2v = V_q(w1), V_q(w2)
    if b1v > b2v: b1v, b2v = b2v, b1v
    return (V_q(bk), V_q(wk), w1v, w2v, b1v, b2v, 1 - tau)

def canon5(st):
    m1 = t_H5(st); m2 = t_V5(st); m3 = t_H5(m2)
    c = enc5(*st)
    for m in (m1, m2, m3):
        e = enc5(*m)
        if e < c: c = e
    return dec5(c)
def canon7(st):
    m1 = t_H7(st); m2 = t_V7(st); m3 = t_H7(m2)
    c = enc7(*st)
    for m in (m1, m2, m3):
        e = enc7(*m)
        if e < c: c = e
    return dec7(c)

def N_general_line(r4, gen):
    """Repo-exact emitted string at N==4, N-folded general string otherwise."""
    return r4 if N == 4 else gen

# ================================================================ duel family
# (5-tuple states, 24-feature semantic basis + conditional 4-coordinate tail)
BASE_NAMES = ["tau", "blocked", "dt", "d_DPR", "d_DpR", "d_APD", "opp", "d_AK",
              "x_A_rel", "x_D_rel",                      # <- DeepSeek's mandated 10
              "d_APR", "d_ApR", "a_chk", "d_chk", "dy_A", "dy_D", "dx_p", "dy_p",
              "t_R", "rwhite", "e_R", "e_A", "e_D", "e_p"]   # <- refinement tail
TAIL_NAMES = ["cwk", "cbk", "cpw", "cpb"]                  # canonical-coordinate tail

def cheb(a, b): return max(abs(a % N - b % N), abs(a // N - b // N))

def features5(w, b, pw, pb, tau):
    """24-feature canonical basis of the given 5-tuple; None for bare kings.
    Runner = strictly-smaller promotion distance, ties (t_W == t_B) broken to
    the side to move.  Called ONLY on canonical orbit representatives."""
    has_w = pw >= 0; has_b = pb >= 0
    tW = (N - 1) - (pw // N) if has_w else None
    tB = (pb // N) if has_b else None
    if has_w and has_b:
        if tW < tB: rw = 1
        elif tB < tW: rw = 0
        else: rw = 1 - tau
    elif has_w: rw = 1
    elif has_b: rw = 0
    else: return None
    R  = pw if rw else pb
    Dp = pb if rw else pw
    K_A = w if rw else b
    K_D = b if rw else w
    tau_f = tau if rw else 1 - tau
    blocked = int(Dp >= 0 and R % N == Dp % N and abs((R // N) - (Dp // N)) == 1)
    if Dp >= 0:
        t_D = ((N - 1) - (Dp // N)) if rw == 0 else (Dp // N)
        dt = (tW if rw else tB) - t_D
    else:
        dt = (tW if rw else tB) - 99
    t_R = tW if rw else tB
    promo_R = (R % N) + N * (N - 1) if rw else (R % N)
    d_DPR = cheb(K_D, promo_R)
    d_DpR = cheb(K_D, R)
    d_APD = cheb(K_A, ((Dp % N) + N * (N - 1) if rw == 0 else (Dp % N))) if Dp >= 0 else 99
    d_AK = cheb(K_A, K_D)
    opp = int(d_AK == 2 and (K_A % N == K_D % N or K_A // N == K_D // N))
    x_A_rel = K_A % N - R % N
    x_D_rel = K_D % N - R % N
    d_APR = cheb(K_A, promo_R)
    d_ApR = cheb(K_A, R)
    def att_by(pa, pk, up):
        x, y = pa % N, pa // N
        yy = y + (1 if up else -1)
        return pk == (x - 1) + N * yy or pk == (x + 1) + N * yy
    a_chk = int(Dp >= 0 and att_by(Dp, K_A, rw == 0))
    d_chk = int(Dp >= 0 and att_by(R, K_D, rw == 1))
    dy_A = (K_A // N) - (R // N)
    dy_D = (K_D // N) - (R // N)
    dx_p = (Dp % N - R % N) if Dp >= 0 else 9
    dy_p = ((Dp // N) - (R // N)) if Dp >= 0 else 9
    e_R = min(R % N, (N - 1) - R % N)
    e_A = min(K_A % N, (N - 1) - K_A % N)
    e_D = min(K_D % N, (N - 1) - K_D % N)
    e_p = min(Dp % N, (N - 1) - Dp % N) if Dp >= 0 else 9
    return (tau_f, blocked, dt, d_DPR, d_DpR, d_APD, opp, d_AK, x_A_rel, x_D_rel,
            d_APR, d_ApR, a_chk, d_chk, dy_A, dy_D, dx_p, dy_p, t_R, rw,
            e_R, e_A, e_D, e_p)

def feat_lines5(used):
    """O(1) feature lines computed from the CANONICAL coordinates
    (cwk, cbk, cpw, cpb, ctau) - exactly features5(*canonical_tuple).
    Repo-exact strings at N=4 (byte-identity), N-folded literals otherwise."""
    L = []
    def need(i): return i in used
    L.append("    has_w = cpw >= 0")
    L.append("    has_b = cpb >= 0")
    L.append("    if has_w and has_b:")
    L.append(N_general_line("        tW = 3 - (cpw >> 2)",
                            f"        tW = {N - 1} - (cpw // {N})"))
    L.append(N_general_line("        tB = cpb >> 2",
                            f"        tB = cpb // {N}"))
    L.append("        if tW < tB:   rw = 1")
    L.append("        elif tB < tW: rw = 0")
    L.append("        else:         rw = 1 - ctau")
    L.append("    elif has_w:")
    L.append("        rw = 1")
    L.append("    else:")
    L.append("        rw = 0")
    L.append("    if rw:")
    L.append("        R = cpw; K_A = cwk; K_D = cbk; Dp = cpb")
    L.append("    else:")
    L.append("        R = cpb; K_A = cbk; K_D = cwk; Dp = cpw")
    L.append(N_general_line("    t_R = (3 - (R >> 2)) if rw else (R >> 2)",
                            f"    t_R = ({N - 1} - (R // {N})) if rw else (R // {N})"))
    if need(0): L.append("    f_tau = ctau if rw else 1 - ctau")
    if need(1):
        L.append(N_general_line(
            "    f_blocked = 1 if (Dp >= 0 and R % 4 == Dp % 4 "
            "and abs((R >> 2) - (Dp >> 2)) == 1) else 0",
            f"    f_blocked = 1 if (Dp >= 0 and R % {N} == Dp % {N} "
            f"and abs((R // {N}) - (Dp // {N})) == 1) else 0"))
    if need(2):
        L.append("    if Dp >= 0:")
        L.append(N_general_line(
            "        f_dt = t_R - ((3 - (Dp >> 2)) if rw == 0 else (Dp >> 2))",
            f"        f_dt = t_R - (({N - 1} - (Dp // {N})) if rw == 0 else (Dp // {N}))"))
        L.append("    else:")
        L.append("        f_dt = t_R - 99")
    if need(3) or need(10):
        L.append(N_general_line("    promo_R = (R % 4) + 12 if rw else (R % 4)",
                                f"    promo_R = (R % {N}) + {N * (N - 1)} if rw else (R % {N})"))
    if need(3):
        L.append(N_general_line(
            "    f_d_DPR = max(abs(K_D % 4 - promo_R % 4), abs((K_D >> 2) - (promo_R >> 2)))",
            f"    f_d_DPR = max(abs(K_D % {N} - promo_R % {N}), abs((K_D // {N}) - (promo_R // {N})))"))
    if need(4):
        L.append(N_general_line(
            "    f_d_DpR = max(abs(K_D % 4 - R % 4), abs((K_D >> 2) - (R >> 2)))",
            f"    f_d_DpR = max(abs(K_D % {N} - R % {N}), abs((K_D // {N}) - (R // {N})))"))
    if need(5):
        L.append("    if Dp >= 0:")
        L.append(N_general_line(
            "        promo_D = (Dp % 4) + 12 if rw == 0 else (Dp % 4)",
            f"        promo_D = (Dp % {N}) + {N * (N - 1)} if rw == 0 else (Dp % {N})"))
        L.append(N_general_line(
            "        f_d_APD = max(abs(K_A % 4 - promo_D % 4), abs((K_A >> 2) - (promo_D >> 2)))",
            f"        f_d_APD = max(abs(K_A % {N} - promo_D % {N}), abs((K_A // {N}) - (promo_D // {N})))"))
        L.append("    else:")
        L.append("        f_d_APD = 99")
    if need(6) or need(7):
        L.append(N_general_line("    dAKx = K_A % 4 - K_D % 4",
                                f"    dAKx = K_A % {N} - K_D % {N}"))
        L.append(N_general_line("    dAKy = (K_A >> 2) - (K_D >> 2)",
                                f"    dAKy = (K_A // {N}) - (K_D // {N})"))
        L.append("    aKx = dAKx if dAKx >= 0 else -dAKx")
        L.append("    aKy = dAKy if dAKy >= 0 else -dAKy")
        L.append("    f_d_AK = aKx if aKx > aKy else aKy")
    if need(6):
        L.append(N_general_line(
            "    f_opp = 1 if (f_d_AK == 2 and (K_A % 4 == K_D % 4 "
            "or (K_A >> 2) == (K_D >> 2))) else 0",
            f"    f_opp = 1 if (f_d_AK == 2 and (K_A % {N} == K_D % {N} "
            f"or (K_A // {N}) == (K_D // {N}))) else 0"))
    if need(8):
        L.append(N_general_line("    f_x_A_rel = K_A % 4 - R % 4",
                                f"    f_x_A_rel = K_A % {N} - R % {N}"))
    if need(9):
        L.append(N_general_line("    f_x_D_rel = K_D % 4 - R % 4",
                                f"    f_x_D_rel = K_D % {N} - R % {N}"))
    if need(10):
        L.append(N_general_line(
            "    f_d_APR = max(abs(K_A % 4 - promo_R % 4), abs((K_A >> 2) - (promo_R >> 2)))",
            f"    f_d_APR = max(abs(K_A % {N} - promo_R % {N}), abs((K_A // {N}) - (promo_R // {N})))"))
    if need(11):
        L.append(N_general_line(
            "    f_d_ApR = max(abs(K_A % 4 - R % 4), abs((K_A >> 2) - (R >> 2)))",
            f"    f_d_ApR = max(abs(K_A % {N} - R % {N}), abs((K_A // {N}) - (R // {N})))"))
    if need(12):
        L.append("    if Dp >= 0:")
        L.append(N_general_line("        pyc = (Dp >> 2) + (1 if rw == 0 else -1)",
                                f"        pyc = (Dp // {N}) + (1 if rw == 0 else -1)"))
        L.append(N_general_line(
            "        f_a_chk = 1 if (K_A == (Dp % 4) - 1 + 4 * pyc or "
            "K_A == (Dp % 4) + 1 + 4 * pyc) else 0",
            f"        f_a_chk = 1 if (K_A == (Dp % {N}) - 1 + {N} * pyc or "
            f"K_A == (Dp % {N}) + 1 + {N} * pyc) else 0"))
        L.append("    else:")
        L.append("        f_a_chk = 0")
    if need(13):
        L.append("    if Dp >= 0:")
        L.append(N_general_line("        ryc = (R >> 2) + (1 if rw else -1)",
                                f"        ryc = (R // {N}) + (1 if rw else -1)"))
        L.append(N_general_line(
            "        f_d_chk = 1 if (K_D == (R % 4) - 1 + 4 * ryc or "
            "K_D == (R % 4) + 1 + 4 * ryc) else 0",
            f"        f_d_chk = 1 if (K_D == (R % {N}) - 1 + {N} * ryc or "
            f"K_D == (R % {N}) + 1 + {N} * ryc) else 0"))
        L.append("    else:")
        L.append("        f_d_chk = 0")
    if need(14):
        L.append(N_general_line("    f_dy_A = (K_A >> 2) - (R >> 2)",
                                f"    f_dy_A = (K_A // {N}) - (R // {N})"))
    if need(15):
        L.append(N_general_line("    f_dy_D = (K_D >> 2) - (R >> 2)",
                                f"    f_dy_D = (K_D // {N}) - (R // {N})"))
    if need(16):
        L.append(N_general_line("    f_dx_p = (Dp % 4 - R % 4) if Dp >= 0 else 9",
                                f"    f_dx_p = (Dp % {N} - R % {N}) if Dp >= 0 else 9"))
    if need(17):
        L.append(N_general_line("    f_dy_p = ((Dp >> 2) - (R >> 2)) if Dp >= 0 else 9",
                                f"    f_dy_p = ((Dp // {N}) - (R // {N})) if Dp >= 0 else 9"))
    if need(18): L.append("    f_t_R = t_R")
    if need(19): L.append("    f_rwhite = rw")
    if need(20):
        L.append(N_general_line("    f_e_R = min(R % 4, 3 - R % 4)",
                                f"    f_e_R = min(R % {N}, {N - 1} - R % {N})"))
    if need(21):
        L.append(N_general_line("    f_e_A = min(K_A % 4, 3 - K_A % 4)",
                                f"    f_e_A = min(K_A % {N}, {N - 1} - K_A % {N})"))
    if need(22):
        L.append(N_general_line("    f_e_D = min(K_D % 4, 3 - K_D % 4)",
                                f"    f_e_D = min(K_D % {N}, {N - 1} - K_D % {N})"))
    if need(23):
        L.append(N_general_line("    f_e_p = min(Dp % 4, 3 - Dp % 4) if Dp >= 0 else 9",
                                f"    f_e_p = min(Dp % {N}, {N - 1} - Dp % {N}) if Dp >= 0 else 9"))
    if need(24): L.append("    f_cwk = cwk")
    if need(25): L.append("    f_cbk = cbk")
    if need(26): L.append("    f_cpw = cpw")
    if need(27): L.append("    f_cpb = cpb")
    return L

def enc_expr5(w_, b_, pw_, pb_, tau_):
    """Balanced, precedence-safe canonical encoding string (radices 16/17/2 at N=4)."""
    if N == 4:
        e = f"({w_}) * 16 + ({b_})"
        e = f"({e}) * 17 + ({pw_} + 1)"
        e = f"({e}) * 17 + ({pb_} + 1)"
    else:
        e = f"({w_}) * {NN} + ({b_})"
        e = f"({e}) * {RAD_P} + ({pw_} + 1)"
        e = f"({e}) * {RAD_P} + ({pb_} + 1)"
    e = f"({e}) * 2 + ({tau_})"
    return e

def canon_block5():
    """Emitted orbit-canonicalization block for duel (min over 4 images + decode)."""
    if N == 4:
        H_w, H_b = "(w ^ 3)", "(b ^ 3)"
        V_b, V_w = "(b & 3) + 4 * (3 - (b >> 2))", "(w & 3) + 4 * (3 - (w >> 2))"
        H_wv, H_bv = "(wkv ^ 3)", "(bkv ^ 3)"
    else:
        H_w = f"(w // {N}) * {N} + ({N - 1} - w % {N})"
        H_b = f"(b // {N}) * {N} + ({N - 1} - b % {N})"
        V_b = f"(b % {N}) + {N} * ({N - 1} - (b // {N}))"
        V_w = f"(w % {N}) + {N} * ({N - 1} - (w // {N}))"
        H_wv = f"(wkv // {N}) * {N} + ({N - 1} - wkv % {N})"
        H_bv = f"(bkv // {N}) * {N} + ({N - 1} - bkv % {N})"
    H1 = N_general_line("pw ^ 3", f"(pw // {N}) * {N} + ({N - 1} - pw % {N})")
    H2 = N_general_line("pb ^ 3", f"(pb // {N}) * {N} + ({N - 1} - pb % {N})")
    H3 = N_general_line("pwv ^ 3", f"(pwv // {N}) * {N} + ({N - 1} - pwv % {N})")
    H4 = N_general_line("pbv ^ 3", f"(pbv // {N}) * {N} + ({N - 1} - pbv % {N})")
    # pawn-image strings (pawn variable) and king-image strings (kings b/w for enc)
    V1 = N_general_line("(pb & 3) + 4 * (3 - (pb >> 2))",
                        f"(pb % {N}) + {N} * ({N - 1} - (pb // {N}))")
    V2 = N_general_line("(pw & 3) + 4 * (3 - (pw >> 2))",
                        f"(pw % {N}) + {N} * ({N - 1} - (pw // {N}))")
    KV = N_general_line("(b & 3) + 4 * (3 - (b >> 2)); bkv = (w & 3) + 4 * (3 - (w >> 2))",
                        f"(b % {N}) + {N} * ({N - 1} - (b // {N})); "
                        f"bkv = (w % {N}) + {N} * ({N - 1} - (w // {N}))")
    D1 = N_general_line("    cpb = t % 17 - 1; t //= 17", f"    cpb = t % {RAD_P} - 1; t //= {RAD_P}")
    D2 = N_general_line("    cpw = t % 17 - 1; t //= 17", f"    cpw = t % {RAD_P} - 1; t //= {RAD_P}")
    D3 = N_general_line("    cbk = t % 16; t //= 16", f"    cbk = t % {NN}; t //= {NN}")
    return [
        "    # ---- orbit canonicalization under G = <H, V'>: min over 4 images",
        f"    e0 = {enc_expr5('w', 'b', 'pw', 'pb', 'tau')}",
        f"    pwh = pw if pw < 0 else {H1}",
        f"    pbh = pb if pb < 0 else {H2}",
        f"    e1 = {enc_expr5(H_w, H_b, 'pwh', 'pbh', 'tau')}",
        f"    pwv = pb if pb < 0 else {V1}",
        f"    pbv = pw if pw < 0 else {V2}",
        f"    e2 = {enc_expr5(V_b, V_w, 'pwv', 'pbv', '(1 - tau)')}",
        f"    wkv = {KV}",
        f"    pwhv = pwv if pwv < 0 else {H3}",
        f"    pbhv = pbv if pbv < 0 else {H4}",
        f"    e3 = {enc_expr5(H_wv, H_bv, 'pwhv', 'pbhv', '(1 - tau)')}",
        "    c = e0",
        "    if e1 < c: c = e1",
        "    if e2 < c: c = e2",
        "    if e3 < c: c = e3",
        "    # ---- decode the canonical state",
        "    t = c",
        "    ctau = t % 2; t //= 2",
        D1, D2, D3,
        "    cwk = t",
    ]

# ================================================================ 7-tuple families
# (asym_3p / four_pawn: 2-pawn-per-side encoding, 50-feature semantic basis +
#  always-on 6-coordinate canonical tail cwk,cbk,cw1,cw2,cb1,cb2)
NAMES7 = [
    # -- structural / material
    "nW", "nB", "rwhite", "tau",
    # -- race block
    "t_R", "dt", "t_A2", "t_D2", "rnext", "A2next", "Dpnext",
    # -- 1v1 runner/defender core (generalized, sentineled)
    "blocked", "d_DPR", "d_DpR", "d_APD", "opp", "d_AK",
    "x_A_rel", "x_D_rel", "d_APR", "d_ApR", "a_chk", "d_chk",
    "dy_A", "dy_D", "dx_p", "dy_p", "e_R", "e_A", "e_D", "e_p",
    # -- second-pawn relations
    "d_KA_A2", "d_KD_A2", "d_KA_D2", "d_KD_D2",
    "dx_A2", "dy_A2", "dx_D2", "dy_D2",
    "blk_R_D2", "blk_A2_Dp", "blk_A2_D2",
    "cap_A2", "cap_D2", "Rcap_D2", "Dpcap_R",
    "pass_R", "pass_Dp", "e_A2", "e_D2",
    # -- canonical coordinate tail (orbit closure)
    "cwk", "cbk", "cw1", "cw2", "cb1", "cb2",
]
NSEM7 = 50
assert len(NAMES7) == 56 and NSEM7 == 50

def features7(cwk, cbk, cw1, cw2, cb1, cb2, ctau):
    """56-feature vector of the canonical state; None for bare kings (0 pawns/side)."""
    nw = (1 if cw1 >= 0 else 0) + (1 if cw2 >= 0 else 0)
    nb = (1 if cb1 >= 0 else 0) + (1 if cb2 >= 0 else 0)
    if nw == 0:
        wA = -1; wB = -1
    elif nw == 1:
        wA = cw1 if cw1 >= 0 else cw2
        wB = -1
    else:
        t1 = (N - 1) - (cw1 // N); t2 = (N - 1) - (cw2 // N)
        if t2 < t1: wA = cw2; wB = cw1
        else:       wA = cw1; wB = cw2
    if nb == 0:
        bA = -1; bB = -1
    elif nb == 1:
        bA = cb1 if cb1 >= 0 else cb2
        bB = -1
    else:
        t1 = cb1 // N; t2 = cb2 // N
        if t2 < t1: bA = cb2; bB = cb1
        else:       bA = cb1; bB = cb2
    if wA < 0 and bA < 0:
        return None
    if wA < 0:   rw = 0
    elif bA < 0: rw = 1
    else:
        tW = (N - 1) - (wA // N); tB = bA // N
        if tW < tB:   rw = 1
        elif tB < tW: rw = 0
        else:         rw = 1 - ctau
    if rw:
        R = wA; A2 = wB; K_A = cwk; K_D = cbk; Dp = bA; D2 = bB; tau_f = ctau
    else:
        R = bA; A2 = bB; K_A = cbk; K_D = cwk; Dp = wA; D2 = wB; tau_f = 1 - ctau
    hasDp = 1 if Dp >= 0 else 0
    hasD2 = 1 if D2 >= 0 else 0
    hasA2 = 1 if A2 >= 0 else 0
    t_R = ((N - 1) - (R // N)) if rw else (R // N)
    t_Dp = ((Dp // N) if rw else ((N - 1) - (Dp // N))) if hasDp else 99
    t_A2 = (((N - 1) - (A2 // N)) if rw else (A2 // N)) if hasA2 else 99
    t_D2 = ((D2 // N) if rw else ((N - 1) - (D2 // N))) if hasD2 else 99
    rn = R + N if rw else R - N
    f_rnext = 1 if (rn == cwk or rn == cbk or rn == cw1 or rn == cw2
                    or rn == cb1 or rn == cb2) else 0
    if hasA2:
        an = A2 + N if rw else A2 - N
        f_A2next = 1 if (an == cwk or an == cbk or an == cw1 or an == cw2
                         or an == cb1 or an == cb2) else 0
    else:
        f_A2next = 0
    if hasDp:
        dn = Dp + N if rw == 0 else Dp - N
        f_Dpnext = 1 if (dn == cwk or dn == cbk or dn == cw1 or dn == cw2
                         or dn == cb1 or dn == cb2) else 0
    else:
        f_Dpnext = 0
    f_blocked = 0
    if hasDp and (R % N) == (Dp % N) and ((Dp // N) - (R // N)) == (1 if rw else -1):
        f_blocked = 1
    promo_R = (R % N) + N * (N - 1) if rw else (R % N)
    f_d_DPR = max(abs((K_D % N) - (promo_R % N)), abs((K_D // N) - (promo_R // N)))
    f_d_DpR = 99 if hasDp == 0 else max(abs((K_D % N) - (R % N)), abs((K_D // N) - (R // N)))
    if hasDp:
        promo_Dp = (Dp % N) + N * (N - 1) if rw == 0 else (Dp % N)
        f_d_APD = max(abs((K_A % N) - (promo_Dp % N)), abs((K_A // N) - (promo_Dp // N)))
    else:
        f_d_APD = 99
    dAKx = (K_A % N) - (K_D % N); dAKy = (K_A // N) - (K_D // N)
    aKx = dAKx if dAKx >= 0 else -dAKx
    aKy = dAKy if dAKy >= 0 else -dAKy
    f_d_AK = aKx if aKx > aKy else aKy
    f_opp = 1 if (f_d_AK == 2 and ((K_A % N) == (K_D % N)
                                   or (K_A // N) == (K_D // N))) else 0
    f_x_A_rel = (K_A % N) - (R % N)
    f_x_D_rel = (K_D % N) - (R % N)
    f_d_APR = max(abs((K_A % N) - (promo_R % N)), abs((K_A // N) - (promo_R // N)))
    f_d_ApR = max(abs((K_A % N) - (R % N)), abs((K_A // N) - (R // N)))
    f_a_chk = 0
    if hasDp:
        dyc = (Dp // N) + (1 if rw == 0 else -1)
        if 0 <= dyc <= N - 1:
            dxc = Dp % N
            s1 = dxc - 1 + N * dyc if dxc >= 1 else -1
            s2 = dxc + 1 + N * dyc if dxc <= N - 2 else -1
            if K_A == s1 or K_A == s2: f_a_chk = 1
    f_d_chk = 0
    ryc = (R // N) + (1 if rw else -1)
    if 0 <= ryc <= N - 1:
        rxc = R % N
        s1 = rxc - 1 + N * ryc if rxc >= 1 else -1
        s2 = rxc + 1 + N * ryc if rxc <= N - 2 else -1
        if K_D == s1 or K_D == s2: f_d_chk = 1
    f_dy_A = (K_A // N) - (R // N)
    f_dy_D = (K_D // N) - (R // N)
    f_dx_p = ((Dp % N) - (R % N)) if hasDp else 9
    f_dy_p = ((Dp // N) - (R // N)) if hasDp else 9
    f_e_R = min(R % N, (N - 1) - (R % N))
    f_e_A = min(K_A % N, (N - 1) - (K_A % N))
    f_e_D = min(K_D % N, (N - 1) - (K_D % N))
    f_e_p = min(Dp % N, (N - 1) - (Dp % N)) if hasDp else 9
    f_d_KA_A2 = 99 if hasA2 == 0 else max(abs((K_A % N) - (A2 % N)), abs((K_A // N) - (A2 // N)))
    f_d_KD_A2 = 99 if hasA2 == 0 else max(abs((K_D % N) - (A2 % N)), abs((K_D // N) - (A2 // N)))
    f_d_KA_D2 = 99 if hasD2 == 0 else max(abs((K_A % N) - (D2 % N)), abs((K_A // N) - (D2 // N)))
    f_d_KD_D2 = 99 if hasD2 == 0 else max(abs((K_D % N) - (D2 % N)), abs((K_D // N) - (D2 // N)))
    f_dx_A2 = ((A2 % N) - (R % N)) if hasA2 else 9
    f_dy_A2 = ((A2 // N) - (R // N)) if hasA2 else 9
    f_dx_D2 = ((D2 % N) - (R % N)) if hasD2 else 9
    f_dy_D2 = ((D2 // N) - (R // N)) if hasD2 else 9
    def blkf(p, q, up):
        return 1 if (p >= 0 and q >= 0 and (p % N) == (q % N)
                     and ((q // N) - (p // N)) == (1 if up else -1)) else 0
    f_blk_R_D2 = blkf(R, D2, rw)
    f_blk_A2_Dp = blkf(A2, Dp, rw)
    f_blk_A2_D2 = blkf(A2, D2, rw)
    f_cap_A2 = 0
    if hasA2:
        ayc = (A2 // N) + (1 if rw else -1)
        if 0 <= ayc <= N - 1:
            axc = A2 % N
            s1 = axc - 1 + N * ayc if axc >= 1 else -1
            s2 = axc + 1 + N * ayc if axc <= N - 2 else -1
            if (hasDp and (Dp == s1 or Dp == s2)) or (hasD2 and (D2 == s1 or D2 == s2)):
                f_cap_A2 = 1
    f_cap_D2 = 0
    if hasD2:
        dyc2 = (D2 // N) + (1 if rw == 0 else -1)
        if 0 <= dyc2 <= N - 1:
            dxc2 = D2 % N
            s1 = dxc2 - 1 + N * dyc2 if dxc2 >= 1 else -1
            s2 = dxc2 + 1 + N * dyc2 if dxc2 <= N - 2 else -1
            if R == s1 or R == s2 or (hasA2 and (A2 == s1 or A2 == s2)):
                f_cap_D2 = 1
    f_Rcap_D2 = 0
    if hasD2:
        ryc2 = (R // N) + (1 if rw else -1)
        if 0 <= ryc2 <= N - 1:
            rxc2 = R % N
            s1 = rxc2 - 1 + N * ryc2 if rxc2 >= 1 else -1
            s2 = rxc2 + 1 + N * ryc2 if rxc2 <= N - 2 else -1
            if D2 == s1 or D2 == s2: f_Rcap_D2 = 1
    f_Dpcap_R = 0
    if hasDp:
        dycp = (Dp // N) + (1 if rw == 0 else -1)
        if 0 <= dycp <= N - 1:
            dxcp = Dp % N
            s1 = dxcp - 1 + N * dycp if dxcp >= 1 else -1
            s2 = dxcp + 1 + N * dycp if dxcp <= N - 2 else -1
            if R == s1 or R == s2: f_Dpcap_R = 1
    f_pass_R = 1
    for q in (Dp, D2):
        if q >= 0 and abs((q % N) - (R % N)) <= 1 and \
           (((q // N) > (R // N)) if rw else ((q // N) < (R // N))):
            f_pass_R = 0
            break
    f_pass_Dp = 0
    if hasDp:
        f_pass_Dp = 1
        for q in (R, A2):
            if q >= 0 and abs((q % N) - (Dp % N)) <= 1 and \
               (((q // N) > (Dp // N)) if rw == 0 else ((q // N) < (Dp // N))):
                f_pass_Dp = 0
                break
    f_e_A2 = min(A2 % N, (N - 1) - (A2 % N)) if hasA2 else 9
    f_e_D2 = min(D2 % N, (N - 1) - (D2 % N)) if hasD2 else 9
    return (nw, nb, rw, tau_f, t_R, t_R - t_Dp, t_A2, t_D2,
            f_rnext, f_A2next, f_Dpnext, f_blocked, f_d_DPR, f_d_DpR, f_d_APD,
            f_opp, f_d_AK, f_x_A_rel, f_x_D_rel, f_d_APR, f_d_ApR, f_a_chk, f_d_chk,
            f_dy_A, f_dy_D, f_dx_p, f_dy_p, f_e_R, f_e_A, f_e_D, f_e_p,
            f_d_KA_A2, f_d_KD_A2, f_d_KA_D2, f_d_KD_D2,
            f_dx_A2, f_dy_A2, f_dx_D2, f_dy_D2,
            f_blk_R_D2, f_blk_A2_Dp, f_blk_A2_D2,
            f_cap_A2, f_cap_D2, f_Rcap_D2, f_Dpcap_R,
            f_pass_R, f_pass_Dp, f_e_A2, f_e_D2,
            cwk, cbk, cw1, cw2, cb1, cb2)

def feat_lines7(used):
    """O(1) feature lines from the CANONICAL 7-tuple; repo-exact at N=4."""
    L = []
    def need(i): return i in used
    L.append("    # ---- per-side semantic order: best pawn = smaller (promotion distance, square)")
    L.append("    f_nW = (1 if cw1 >= 0 else 0) + (1 if cw2 >= 0 else 0)")
    L.append("    f_nB = (1 if cb1 >= 0 else 0) + (1 if cb2 >= 0 else 0)")
    L.append("    if f_nW == 0:")
    L.append("        wA = -1; wB = -1")
    L.append("    elif f_nW == 1:")
    L.append("        wA = cw1 if cw1 >= 0 else cw2")
    L.append("        wB = -1")
    L.append("    else:")
    L.append(N_general_line("        t1 = 3 - (cw1 >> 2); t2 = 3 - (cw2 >> 2)",
                            f"        t1 = {N - 1} - (cw1 // {N}); t2 = {N - 1} - (cw2 // {N})"))
    L.append("        if t2 < t1: wA = cw2; wB = cw1")
    L.append("        else:       wA = cw1; wB = cw2")
    L.append("    if f_nB == 0:")
    L.append("        bA = -1; bB = -1")
    L.append("    elif f_nB == 1:")
    L.append("        bA = cb1 if cb1 >= 0 else cb2")
    L.append("        bB = -1")
    L.append("    else:")
    L.append(N_general_line("        t1 = cb1 >> 2; t2 = cb2 >> 2",
                            f"        t1 = cb1 // {N}; t2 = cb2 // {N}"))
    L.append("        if t2 < t1: bA = cb2; bB = cb1")
    L.append("        else:       bA = cb1; bB = cb2")
    L.append("    if wA < 0 and bA < 0:")
    L.append("        return 0")
    L.append("    if wA < 0:   rw = 0")
    L.append("    elif bA < 0: rw = 1")
    L.append("    else:")
    L.append(N_general_line("        tW = 3 - (wA >> 2); tB = bA >> 2",
                            f"        tW = {N - 1} - (wA // {N}); tB = bA // {N}"))
    L.append("        if tW < tB:   rw = 1")
    L.append("        elif tB < tW: rw = 0")
    L.append("        else:         rw = 1 - ctau")
    L.append("    if rw:")
    L.append("        R = wA; A2 = wB; K_A = cwk; K_D = cbk; Dp = bA; D2 = bB; taf = ctau")
    L.append("    else:")
    L.append("        R = bA; A2 = bB; K_A = cbk; K_D = cwk; Dp = wA; D2 = wB; taf = 1 - ctau")
    L.append("    hasDp = 1 if Dp >= 0 else 0")
    L.append("    hasD2 = 1 if D2 >= 0 else 0")
    L.append("    hasA2 = 1 if A2 >= 0 else 0")
    if need(2): L.append("    f_rwhite = rw")
    if need(3): L.append("    f_tau = taf")
    if need(4) or need(5):
        L.append(N_general_line("    t_R = (3 - (R >> 2)) if rw else (R >> 2)",
                                f"    t_R = ({N - 1} - (R // {N})) if rw else (R // {N})"))
    if need(4): L.append("    f_t_R = t_R")
    if need(5):
        L.append(N_general_line("    t_Dp = ((Dp >> 2) if rw else (3 - (Dp >> 2))) if hasDp else 99",
                                f"    t_Dp = ((Dp // {N}) if rw else ({N - 1} - (Dp // {N}))) if hasDp else 99"))
        L.append("    f_dt = t_R - t_Dp")
    if need(6):
        L.append(N_general_line("    f_t_A2 = ((3 - (A2 >> 2)) if rw else (A2 >> 2)) if hasA2 else 99",
                                f"    f_t_A2 = (({N - 1} - (A2 // {N})) if rw else (A2 // {N})) if hasA2 else 99"))
    if need(7):
        L.append(N_general_line("    f_t_D2 = ((D2 >> 2) if rw else (3 - (D2 >> 2))) if hasD2 else 99",
                                f"    f_t_D2 = ((D2 // {N}) if rw else ({N - 1} - (D2 // {N}))) if hasD2 else 99"))
    if need(8):
        L.append(N_general_line("    rn = R + 4 if rw else R - 4",
                                f"    rn = R + {N} if rw else R - {N}"))
        L.append("    f_rnext = 1 if (rn == cwk or rn == cbk or rn == cw1 or rn == cw2 "
                 "or rn == cb1 or rn == cb2) else 0")
    if need(9):
        L.append("    if hasA2:")
        L.append(N_general_line("        an = A2 + 4 if rw else A2 - 4",
                                f"        an = A2 + {N} if rw else A2 - {N}"))
        L.append("        f_A2next = 1 if (an == cwk or an == cbk or an == cw1 or an == cw2 "
                 "or an == cb1 or an == cb2) else 0")
        L.append("    else:")
        L.append("        f_A2next = 0")
    if need(10):
        L.append("    if hasDp:")
        L.append(N_general_line("        dn = Dp + 4 if rw == 0 else Dp - 4",
                                f"        dn = Dp + {N} if rw == 0 else Dp - {N}"))
        L.append("        f_Dpnext = 1 if (dn == cwk or dn == cbk or dn == cw1 or dn == cw2 "
                 "or dn == cb1 or dn == cb2) else 0")
        L.append("    else:")
        L.append("        f_Dpnext = 0")
    if need(11):
        L.append("    f_blocked = 0")
        L.append(N_general_line(
            "    if hasDp and (R & 3) == (Dp & 3) and ((Dp >> 2) - (R >> 2)) == (1 if rw else -1):",
            f"    if hasDp and (R % {N}) == (Dp % {N}) and ((Dp // {N}) - (R // {N})) == (1 if rw else -1):"))
        L.append("        f_blocked = 1")
    if need(12) or need(19):
        L.append(N_general_line("    promo_R = (R & 3) + 12 if rw else (R & 3)",
                                f"    promo_R = (R % {N}) + {N * (N - 1)} if rw else (R % {N})"))
    if need(12):
        L.append(N_general_line(
            "    f_d_DPR = max(abs((K_D & 3) - (promo_R & 3)), abs((K_D >> 2) - (promo_R >> 2)))",
            f"    f_d_DPR = max(abs((K_D % {N}) - (promo_R % {N})), abs((K_D // {N}) - (promo_R // {N})))"))
    if need(13):
        L.append(N_general_line(
            "    f_d_DpR = 99 if hasDp == 0 else max(abs((K_D & 3) - (R & 3)), "
            "abs((K_D >> 2) - (R >> 2)))",
            f"    f_d_DpR = 99 if hasDp == 0 else max(abs((K_D % {N}) - (R % {N})), "
            f"abs((K_D // {N}) - (R // {N})))"))
    if need(14):
        L.append("    if hasDp:")
        L.append(N_general_line("        promo_Dp = (Dp & 3) + 12 if rw == 0 else (Dp & 3)",
                                f"        promo_Dp = (Dp % {N}) + {N * (N - 1)} if rw == 0 else (Dp % {N})"))
        L.append(N_general_line(
            "        f_d_APD = max(abs((K_A & 3) - (promo_Dp & 3)), "
            "abs((K_A >> 2) - (promo_Dp >> 2)))",
            f"        f_d_APD = max(abs((K_A % {N}) - (promo_Dp % {N})), "
            f"abs((K_A // {N}) - (promo_Dp // {N})))"))
        L.append("    else:")
        L.append("        f_d_APD = 99")
    if need(15) or need(16):
        L.append(N_general_line("    dAKx = (K_A & 3) - (K_D & 3); dAKy = (K_A >> 2) - (K_D >> 2)",
                                f"    dAKx = (K_A % {N}) - (K_D % {N}); dAKy = (K_A // {N}) - (K_D // {N})"))
        L.append("    aKx = dAKx if dAKx >= 0 else -dAKx")
        L.append("    aKy = dAKy if dAKy >= 0 else -dAKy")
        L.append("    f_d_AK = aKx if aKx > aKy else aKy")
    if need(15):
        L.append(N_general_line(
            "    f_opp = 1 if (f_d_AK == 2 and ((K_A & 3) == (K_D & 3) "
            "or (K_A >> 2) == (K_D >> 2))) else 0",
            f"    f_opp = 1 if (f_d_AK == 2 and ((K_A % {N}) == (K_D % {N}) "
            f"or (K_A // {N}) == (K_D // {N}))) else 0"))
    if need(17):
        L.append(N_general_line("    f_x_A_rel = (K_A & 3) - (R & 3)",
                                f"    f_x_A_rel = (K_A % {N}) - (R % {N})"))
    if need(18):
        L.append(N_general_line("    f_x_D_rel = (K_D & 3) - (R & 3)",
                                f"    f_x_D_rel = (K_D % {N}) - (R % {N})"))
    if need(19):
        L.append(N_general_line(
            "    f_d_APR = max(abs((K_A & 3) - (promo_R & 3)), abs((K_A >> 2) - (promo_R >> 2)))",
            f"    f_d_APR = max(abs((K_A % {N}) - (promo_R % {N})), abs((K_A // {N}) - (promo_R // {N})))"))
    if need(20):
        L.append(N_general_line(
            "    f_d_ApR = max(abs((K_A & 3) - (R & 3)), abs((K_A >> 2) - (R >> 2)))",
            f"    f_d_ApR = max(abs((K_A % {N}) - (R % {N})), abs((K_A // {N}) - (R // {N})))"))
    if need(21):
        L.append("    f_a_chk = 0")
        L.append("    if hasDp:")
        L.append(N_general_line("        dyc = (Dp >> 2) + (1 if rw == 0 else -1)",
                                f"        dyc = (Dp // {N}) + (1 if rw == 0 else -1)"))
        L.append(N_general_line("        if 0 <= dyc <= 3:", f"        if 0 <= dyc <= {N - 1}:"))
        L.append("            dxc = Dp & 3" if N == 4 else f"            dxc = Dp % {N}")
        L.append("            s1 = dxc - 1 + 4 * dyc if dxc >= 1 else -1"
                 if N == 4 else f"            s1 = dxc - 1 + {N} * dyc if dxc >= 1 else -1")
        L.append("            s2 = dxc + 1 + 4 * dyc if dxc <= 2 else -1"
                 if N == 4 else f"            s2 = dxc + 1 + {N} * dyc if dxc <= {N - 2} else -1")
        L.append("            if K_A == s1 or K_A == s2: f_a_chk = 1")
    if need(22):
        L.append("    f_d_chk = 0")
        L.append(N_general_line("    ryc = (R >> 2) + (1 if rw else -1)",
                                f"    ryc = (R // {N}) + (1 if rw else -1)"))
        L.append(N_general_line("    if 0 <= ryc <= 3:", f"    if 0 <= ryc <= {N - 1}:"))
        L.append("        rxc = R & 3" if N == 4 else f"        rxc = R % {N}")
        L.append("        s1 = rxc - 1 + 4 * ryc if rxc >= 1 else -1"
                 if N == 4 else f"        s1 = rxc - 1 + {N} * ryc if rxc >= 1 else -1")
        L.append("        s2 = rxc + 1 + 4 * ryc if rxc <= 2 else -1"
                 if N == 4 else f"        s2 = rxc + 1 + {N} * ryc if rxc <= {N - 2} else -1")
        L.append("        if K_D == s1 or K_D == s2: f_d_chk = 1")
    if need(23):
        L.append(N_general_line("    f_dy_A = (K_A >> 2) - (R >> 2)",
                                f"    f_dy_A = (K_A // {N}) - (R // {N})"))
    if need(24):
        L.append(N_general_line("    f_dy_D = (K_D >> 2) - (R >> 2)",
                                f"    f_dy_D = (K_D // {N}) - (R // {N})"))
    if need(25):
        L.append(N_general_line("    f_dx_p = ((Dp & 3) - (R & 3)) if hasDp else 9",
                                f"    f_dx_p = ((Dp % {N}) - (R % {N})) if hasDp else 9"))
    if need(26):
        L.append(N_general_line("    f_dy_p = ((Dp >> 2) - (R >> 2)) if hasDp else 9",
                                f"    f_dy_p = ((Dp // {N}) - (R // {N})) if hasDp else 9"))
    if need(27):
        L.append(N_general_line("    f_e_R = min(R & 3, 3 - (R & 3))",
                                f"    f_e_R = min(R % {N}, {N - 1} - (R % {N}))"))
    if need(28):
        L.append(N_general_line("    f_e_A = min(K_A & 3, 3 - (K_A & 3))",
                                f"    f_e_A = min(K_A % {N}, {N - 1} - (K_A % {N}))"))
    if need(29):
        L.append(N_general_line("    f_e_D = min(K_D & 3, 3 - (K_D & 3))",
                                f"    f_e_D = min(K_D % {N}, {N - 1} - (K_D % {N}))"))
    if need(30):
        L.append(N_general_line("    f_e_p = min(Dp & 3, 3 - (Dp & 3)) if hasDp else 9",
                                f"    f_e_p = min(Dp % {N}, {N - 1} - (Dp % {N})) if hasDp else 9"))
    if need(31):
        L.append(N_general_line(
            "    f_d_KA_A2 = 99 if hasA2 == 0 else max(abs((K_A & 3) - (A2 & 3)), "
            "abs((K_A >> 2) - (A2 >> 2)))",
            f"    f_d_KA_A2 = 99 if hasA2 == 0 else max(abs((K_A % {N}) - (A2 % {N})), "
            f"abs((K_A // {N}) - (A2 // {N})))"))
    if need(32):
        L.append(N_general_line(
            "    f_d_KD_A2 = 99 if hasA2 == 0 else max(abs((K_D & 3) - (A2 & 3)), "
            "abs((K_D >> 2) - (A2 >> 2)))",
            f"    f_d_KD_A2 = 99 if hasA2 == 0 else max(abs((K_D % {N}) - (A2 % {N})), "
            f"abs((K_D // {N}) - (A2 // {N})))"))
    if need(33):
        L.append(N_general_line(
            "    f_d_KA_D2 = 99 if hasD2 == 0 else max(abs((K_A & 3) - (D2 & 3)), "
            "abs((K_A >> 2) - (D2 >> 2)))",
            f"    f_d_KA_D2 = 99 if hasD2 == 0 else max(abs((K_A % {N}) - (D2 % {N})), "
            f"abs((K_A // {N}) - (D2 // {N})))"))
    if need(34):
        L.append(N_general_line(
            "    f_d_KD_D2 = 99 if hasD2 == 0 else max(abs((K_D & 3) - (D2 & 3)), "
            "abs((K_D >> 2) - (D2 >> 2)))",
            f"    f_d_KD_D2 = 99 if hasD2 == 0 else max(abs((K_D % {N}) - (D2 % {N})), "
            f"abs((K_D // {N}) - (D2 // {N})))"))
    if need(35):
        L.append(N_general_line("    f_dx_A2 = ((A2 & 3) - (R & 3)) if hasA2 else 9",
                                f"    f_dx_A2 = ((A2 % {N}) - (R % {N})) if hasA2 else 9"))
    if need(36):
        L.append(N_general_line("    f_dy_A2 = ((A2 >> 2) - (R >> 2)) if hasA2 else 9",
                                f"    f_dy_A2 = ((A2 // {N}) - (R // {N})) if hasA2 else 9"))
    if need(37):
        L.append(N_general_line("    f_dx_D2 = ((D2 & 3) - (R & 3)) if hasD2 else 9",
                                f"    f_dx_D2 = ((D2 % {N}) - (R % {N})) if hasD2 else 9"))
    if need(38):
        L.append(N_general_line("    f_dy_D2 = ((D2 >> 2) - (R >> 2)) if hasD2 else 9",
                                f"    f_dy_D2 = ((D2 // {N}) - (R // {N})) if hasD2 else 9"))
    if need(39):
        L.append(N_general_line(
            "    f_blk_R_D2 = 1 if (R >= 0 and D2 >= 0 and (R & 3) == (D2 & 3) "
            "and ((D2 >> 2) - (R >> 2)) == (1 if rw else -1)) else 0",
            f"    f_blk_R_D2 = 1 if (R >= 0 and D2 >= 0 and (R % {N}) == (D2 % {N}) "
            f"and ((D2 // {N}) - (R // {N})) == (1 if rw else -1)) else 0"))
    if need(40):
        L.append(N_general_line(
            "    f_blk_A2_Dp = 1 if (A2 >= 0 and Dp >= 0 and (A2 & 3) == (Dp & 3) "
            "and ((Dp >> 2) - (A2 >> 2)) == (1 if rw else -1)) else 0",
            f"    f_blk_A2_Dp = 1 if (A2 >= 0 and Dp >= 0 and (A2 % {N}) == (Dp % {N}) "
            f"and ((Dp // {N}) - (A2 // {N})) == (1 if rw else -1)) else 0"))
    if need(41):
        L.append(N_general_line(
            "    f_blk_A2_D2 = 1 if (A2 >= 0 and D2 >= 0 and (A2 & 3) == (D2 & 3) "
            "and ((D2 >> 2) - (A2 >> 2)) == (1 if rw else -1)) else 0",
            f"    f_blk_A2_D2 = 1 if (A2 >= 0 and D2 >= 0 and (A2 % {N}) == (D2 % {N}) "
            f"and ((D2 // {N}) - (A2 // {N})) == (1 if rw else -1)) else 0"))
    if need(42):
        L.append("    f_cap_A2 = 0")
        L.append("    if hasA2:")
        L.append(N_general_line("        ayc = (A2 >> 2) + (1 if rw else -1)",
                                f"        ayc = (A2 // {N}) + (1 if rw else -1)"))
        L.append(N_general_line("        if 0 <= ayc <= 3:", f"        if 0 <= ayc <= {N - 1}:"))
        L.append("            axc = A2 & 3" if N == 4 else f"            axc = A2 % {N}")
        L.append("            s1 = axc - 1 + 4 * ayc if axc >= 1 else -1"
                 if N == 4 else f"            s1 = axc - 1 + {N} * ayc if axc >= 1 else -1")
        L.append("            s2 = axc + 1 + 4 * ayc if axc <= 2 else -1"
                 if N == 4 else f"            s2 = axc + 1 + {N} * ayc if axc <= {N - 2} else -1")
        L.append("            if (hasDp and (Dp == s1 or Dp == s2)) or "
                 "(hasD2 and (D2 == s1 or D2 == s2)):")
        L.append("                f_cap_A2 = 1")
    if need(43):
        L.append("    f_cap_D2 = 0")
        L.append("    if hasD2:")
        L.append(N_general_line("        dyc2 = (D2 >> 2) + (1 if rw == 0 else -1)",
                                f"        dyc2 = (D2 // {N}) + (1 if rw == 0 else -1)"))
        L.append(N_general_line("        if 0 <= dyc2 <= 3:", f"        if 0 <= dyc2 <= {N - 1}:"))
        L.append("            dxc2 = D2 & 3" if N == 4 else f"            dxc2 = D2 % {N}")
        L.append("            s1 = dxc2 - 1 + 4 * dyc2 if dxc2 >= 1 else -1"
                 if N == 4 else f"            s1 = dxc2 - 1 + {N} * dyc2 if dxc2 >= 1 else -1")
        L.append("            s2 = dxc2 + 1 + 4 * dyc2 if dxc2 <= 2 else -1"
                 if N == 4 else f"            s2 = dxc2 + 1 + {N} * dyc2 if dxc2 <= {N - 2} else -1")
        L.append("            if R == s1 or R == s2 or (hasA2 and (A2 == s1 or A2 == s2)):")
        L.append("                f_cap_D2 = 1")
    if need(44):
        L.append("    f_Rcap_D2 = 0")
        L.append("    if hasD2:")
        L.append(N_general_line("        ryc2 = (R >> 2) + (1 if rw else -1)",
                                f"        ryc2 = (R // {N}) + (1 if rw else -1)"))
        L.append(N_general_line("        if 0 <= ryc2 <= 3:", f"        if 0 <= ryc2 <= {N - 1}:"))
        L.append("            rxc2 = R & 3" if N == 4 else f"            rxc2 = R % {N}")
        L.append("            s1 = rxc2 - 1 + 4 * ryc2 if rxc2 >= 1 else -1"
                 if N == 4 else f"            s1 = rxc2 - 1 + {N} * ryc2 if rxc2 >= 1 else -1")
        L.append("            s2 = rxc2 + 1 + 4 * ryc2 if rxc2 <= 2 else -1"
                 if N == 4 else f"            s2 = rxc2 + 1 + {N} * ryc2 if rxc2 <= {N - 2} else -1")
        L.append("            if D2 == s1 or D2 == s2: f_Rcap_D2 = 1")
    if need(45):
        L.append("    f_Dpcap_R = 0")
        L.append("    if hasDp:")
        L.append(N_general_line("        dycp = (Dp >> 2) + (1 if rw == 0 else -1)",
                                f"        dycp = (Dp // {N}) + (1 if rw == 0 else -1)"))
        L.append(N_general_line("        if 0 <= dycp <= 3:", f"        if 0 <= dycp <= {N - 1}:"))
        L.append("            dxcp = Dp & 3" if N == 4 else f"            dxcp = Dp % {N}")
        L.append("            s1 = dxcp - 1 + 4 * dycp if dxcp >= 1 else -1"
                 if N == 4 else f"            s1 = dxcp - 1 + {N} * dycp if dxcp >= 1 else -1")
        L.append("            s2 = dxcp + 1 + 4 * dycp if dxcp <= 2 else -1"
                 if N == 4 else f"            s2 = dxcp + 1 + {N} * dycp if dxcp <= {N - 2} else -1")
        L.append("            if R == s1 or R == s2: f_Dpcap_R = 1")
    if need(46):
        L.append("    f_pass_R = 1")
        L.append(N_general_line(
            "    if Dp >= 0 and abs((Dp & 3) - (R & 3)) <= 1 and "
            "(((Dp >> 2) > (R >> 2)) if rw else ((Dp >> 2) < (R >> 2))):",
            f"    if Dp >= 0 and abs((Dp % {N}) - (R % {N})) <= 1 and "
            f"(((Dp // {N}) > (R // {N})) if rw else ((Dp // {N}) < (R // {N}))):"))
        L.append("        f_pass_R = 0")
        L.append(N_general_line(
            "    elif D2 >= 0 and abs((D2 & 3) - (R & 3)) <= 1 and "
            "(((D2 >> 2) > (R >> 2)) if rw else ((D2 >> 2) < (R >> 2))):",
            f"    elif D2 >= 0 and abs((D2 % {N}) - (R % {N})) <= 1 and "
            f"(((D2 // {N}) > (R // {N})) if rw else ((D2 // {N}) < (R // {N}))):"))
        L.append("        f_pass_R = 0")
    if need(47):
        L.append("    f_pass_Dp = 0")
        L.append("    if hasDp:")
        L.append("        f_pass_Dp = 1")
        L.append(N_general_line(
            "        if R >= 0 and abs((R & 3) - (Dp & 3)) <= 1 and "
            "(((R >> 2) > (Dp >> 2)) if rw == 0 else ((R >> 2) < (Dp >> 2))):",
            f"        if R >= 0 and abs((R % {N}) - (Dp % {N})) <= 1 and "
            f"(((R // {N}) > (Dp // {N})) if rw == 0 else ((R // {N}) < (Dp // {N}))):"))
        L.append("            f_pass_Dp = 0")
        L.append(N_general_line(
            "        elif A2 >= 0 and abs((A2 & 3) - (Dp & 3)) <= 1 and "
            "(((A2 >> 2) > (Dp >> 2)) if rw == 0 else ((A2 >> 2) < (Dp >> 2))):",
            f"        elif A2 >= 0 and abs((A2 % {N}) - (Dp % {N})) <= 1 and "
            f"(((A2 // {N}) > (Dp // {N})) if rw == 0 else ((A2 // {N}) < (Dp // {N}))):"))
        L.append("            f_pass_Dp = 0")
    if need(48):
        L.append(N_general_line("    f_e_A2 = min(A2 & 3, 3 - (A2 & 3)) if hasA2 else 9",
                                f"    f_e_A2 = min(A2 % {N}, {N - 1} - (A2 % {N})) if hasA2 else 9"))
    if need(49):
        L.append(N_general_line("    f_e_D2 = min(D2 & 3, 3 - (D2 & 3)) if hasD2 else 9",
                                f"    f_e_D2 = min(D2 % {N}, {N - 1} - (D2 % {N})) if hasD2 else 9"))
    if need(50): L.append("    f_cwk = cwk")
    if need(51): L.append("    f_cbk = cbk")
    if need(52): L.append("    f_cw1 = cw1")
    if need(53): L.append("    f_cw2 = cw2")
    if need(54): L.append("    f_cb1 = cb1")
    if need(55): L.append("    f_cb2 = cb2")
    return L

def enc_expr7(wk_, bk_, w1_, w2_, b1_, b2_, tau_):
    if N == 4:
        e = f"({wk_}) * 16 + ({bk_})"
        for x in (w1_, w2_, b1_, b2_):
            e = f"({e}) * 17 + ({x} + 1)"
    else:
        e = f"({wk_}) * {NN} + ({bk_})"
        for x in (w1_, w2_, b1_, b2_):
            e = f"({e}) * {RAD_P} + ({x} + 1)"
    e = f"({e}) * 2 + ({tau_})"
    return e

def canon_block7():
    """Emitted orbit-canonicalization block for the 7-tuple families."""
    if N == 4:
        H_w, H_b = "(w ^ 3)", "(b ^ 3)"
        V_b, V_w = "(b & 3) + 4 * (3 - (b >> 2))", "(w & 3) + 4 * (3 - (w >> 2))"
        H_wv, H_bv = "(wkv ^ 3)", "(bkv ^ 3)"
    else:
        H_w = f"(w // {N}) * {N} + ({N - 1} - w % {N})"
        H_b = f"(b // {N}) * {N} + ({N - 1} - b % {N})"
        V_b = f"(b % {N}) + {N} * ({N - 1} - (b // {N}))"
        V_w = f"(w % {N}) + {N} * ({N - 1} - (w // {N}))"
        H_wv = f"(wkv // {N}) * {N} + ({N - 1} - wkv % {N})"
        H_bv = f"(bkv // {N}) * {N} + ({N - 1} - bkv % {N})"
    D = []
    for nm in ("cb2", "cb1", "cw2", "cw1"):
        D.append(N_general_line(f"    {nm} = t % 17 - 1; t //= 17",
                                f"    {nm} = t % {RAD_P} - 1; t //= {RAD_P}"))
    D.append(N_general_line("    cbk = t % 16; t //= 16", f"    cbk = t % {NN}; t //= {NN}"))
    if N == 4:
        HV = ["    w1h = pw1 if pw1 < 0 else pw1 ^ 3",
              "    w2h = pw2 if pw2 < 0 else pw2 ^ 3",
              "    b1h = pb1 if pb1 < 0 else pb1 ^ 3",
              "    b2h = pb2 if pb2 < 0 else pb2 ^ 3"]
        VV = ["    w1v = pb1 if pb1 < 0 else (pb1 & 3) + 4 * (3 - (pb1 >> 2))",
              "    w2v = pb2 if pb2 < 0 else (pb2 & 3) + 4 * (3 - (pb2 >> 2))",
              "    b1v = pw1 if pw1 < 0 else (pw1 & 3) + 4 * (3 - (pw1 >> 2))",
              "    b2v = pw2 if pw2 < 0 else (pw2 & 3) + 4 * (3 - (pw2 >> 2))"]
        HVR = ["    w1hv = w1v if w1v < 0 else w1v ^ 3",
               "    w2hv = w2v if w2v < 0 else w2v ^ 3",
               "    b1hv = b1v if b1v < 0 else b1v ^ 3",
               "    b2hv = b2v if b2v < 0 else b2v ^ 3"]
        KV = "(b & 3) + 4 * (3 - (b >> 2)); bkv = (w & 3) + 4 * (3 - (w >> 2))"
    else:
        HV = [f"    w1h = pw1 if pw1 < 0 else (pw1 // {N}) * {N} + ({N - 1} - pw1 % {N})",
              f"    w2h = pw2 if pw2 < 0 else (pw2 // {N}) * {N} + ({N - 1} - pw2 % {N})",
              f"    b1h = pb1 if pb1 < 0 else (pb1 // {N}) * {N} + ({N - 1} - pb1 % {N})",
              f"    b2h = pb2 if pb2 < 0 else (pb2 // {N}) * {N} + ({N - 1} - pb2 % {N})"]
        VV = [f"    w1v = pb1 if pb1 < 0 else (pb1 % {N}) + {N} * ({N - 1} - (pb1 // {N}))",
              f"    w2v = pb2 if pb2 < 0 else (pb2 % {N}) + {N} * ({N - 1} - (pb2 // {N}))",
              f"    b1v = pw1 if pw1 < 0 else (pw1 % {N}) + {N} * ({N - 1} - (pw1 // {N}))",
              f"    b2v = pw2 if pw2 < 0 else (pw2 % {N}) + {N} * ({N - 1} - (pw2 // {N}))"]
        HVR = [f"    w1hv = w1v if w1v < 0 else (w1v // {N}) * {N} + ({N - 1} - w1v % {N})",
               f"    w2hv = w2v if w2v < 0 else (w2v // {N}) * {N} + ({N - 1} - w2v % {N})",
               f"    b1hv = b1v if b1v < 0 else (b1v // {N}) * {N} + ({N - 1} - b1v % {N})",
               f"    b2hv = b2v if b2v < 0 else (b2v // {N}) * {N} + ({N - 1} - b2v % {N})"]
        KV = (f"(b % {N}) + {N} * ({N - 1} - (b // {N})); "
              f"bkv = (w % {N}) + {N} * ({N - 1} - (w // {N}))")
    S = "    if %s > %s: %s, %s = %s, %s"
    return ([
        "    # ---- order-canonical pawn input",
        "    if pw1 > pw2: pw1, pw2 = pw2, pw1",
        "    if pb1 > pb2: pb1, pb2 = pb2, pb1",
        "    # ---- orbit canonicalization under G = <H, V'>: min over 4 images",
        f"    e0 = {enc_expr7('w', 'b', 'pw1', 'pw2', 'pb1', 'pb2', 'tau')}",
        HV[0], HV[1], S % ("w1h", "w2h", "w1h", "w2h", "w2h", "w1h"),
        HV[2], HV[3], S % ("b1h", "b2h", "b1h", "b2h", "b2h", "b1h"),
        f"    e1 = {enc_expr7(H_w, H_b, 'w1h', 'w2h', 'b1h', 'b2h', 'tau')}",
        VV[0], VV[1], S % ("w1v", "w2v", "w1v", "w2v", "w2v", "w1v"),
        VV[2], VV[3], S % ("b1v", "b2v", "b1v", "b2v", "b2v", "b1v"),
        f"    e2 = {enc_expr7(V_b, V_w, 'w1v', 'w2v', 'b1v', 'b2v', '(1 - tau)')}",
        f"    wkv = {KV}",
        HVR[0], HVR[1], S % ("w1hv", "w2hv", "w1hv", "w2hv", "w2hv", "w1hv"),
        HVR[2], HVR[3], S % ("b1hv", "b2hv", "b1hv", "b2hv", "b2hv", "b1hv"),
        f"    e3 = {enc_expr7(H_wv, H_bv, 'w1hv', 'w2hv', 'b1hv', 'b2hv', '(1 - tau)')}",
        "    c = e0",
        "    if e1 < c: c = e1",
        "    if e2 < c: c = e2",
        "    if e3 < c: c = e3",
        "    # ---- decode the canonical state",
        "    t = c",
        "    ctau = t % 2; t //= 2",
    ] + D + [
        "    cwk = t",
    ])

# ================================================================ MTBDD engine
# (repo algorithm verbatim: contiguous-range recursion over lexicographically
#  sorted rows, hash-consing on (block, children), constant-subtree /
#  single-child reduction; memory-lean storage: numpy columns + integer CTX keys)
class Compressor:
    def __init__(self, names, nsem):
        self.NAMES = list(names); self.NSEM = nsem; self.NB = len(names)
        self._ctr = 0

    def load_rows(self, pairs, tag):
        """pairs: list of (feature_tuple, label).  Sorts, checks semantic/full
        feature-group conflicts (repo semantics), builds column storage."""
        stage_mark(f"sort rows [{tag}]")
        pairs.sort(key=lambda p: p[0])
        NB, NSEM = self.NB, self.NSEM
        # pass 1: count distinct rows
        R = 0; prev = None
        for p in pairs:
            if p[0] != prev: R += 1; prev = p[0]
        mat = np.empty((R, NB), dtype=np.int16)
        lab = np.empty(R, dtype=np.int8)
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
                if l != lab[ri]: full_conf += 1
            if sem != prev_sem:
                if prev_sem is not None and not block_ok: sem_conflicting += 1
                sem_blocks += 1
                block_first_lab = l; block_ok = True
            else:
                if l != block_first_lab: block_ok = False
            prev_t = t; prev_sem = sem
        if prev_sem is not None and not block_ok: sem_conflicting += 1
        del pairs; gc.collect()
        self.conf = {"distinct_semantic_rows": sem_blocks,
                     "semantic_conflicting_groups": sem_conflicting,
                     "distinct_full_rows": R, "full_conflicting_groups": full_conf}
        self.R = R
        self.COLS = [np.ascontiguousarray(mat[:, bi]) for bi in range(NB)]
        self.LAB0 = lab
        del mat; gc.collect()
        stage_mark(f"rows ready [{tag}] ({R:,} rows)")

    def reset_build(self):
        self.NODES = {}; self.CTX = {}; self._ctr = 0

    CTX_CAP = 1_500_000   # memo entries; the interval memo never hits (each level's
    # intervals partition the rows, so every (bi,i0,i1) is reached once) - the cap
    # only bounds memory at large row counts and cannot change the built tree.

    def mk(self, bi, ch):
        key = ("N", bi, tuple(ch))
        return self.NODES.setdefault(key, key)

    def build(self, i0, i1, bi):
        if i0 >= i1:
            return ("T", 0)                                # unreachable on data
        if bi == self.NB:
            assert i1 - i0 == 1, "row class not singleton at full depth"
            return ("T", int(self.LABV[i0]))
        key = (i0 * (self.R + 1) + i1) * self.NB + bi
        if key in self.CTX: return self.CTX[key]
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
        if self._ctr % 250_000 == 0: mem_guard("build")
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
                for _, c in k[2]: collect(c)
        collect(root)
        memo_p = {}; memo_d = {}
        def paths(k):
            if k[0] == "T": return 1
            if k in memo_p: return memo_p[k]
            p = sum(paths(c) for _, c in k[2]); memo_p[k] = p; return p
        def depth(k):
            if k[0] == "T": return 0
            if k in memo_d: return memo_d[k]
            d = 1 + max(depth(c) for _, c in k[2]); memo_d[k] = d; return d
        return len(seen), paths(root), depth(root)

    def used_feats(self, root):
        u = set()
        def walk(k):
            if k[0] == "N":
                u.add(k[1])
                for _, c in k[2]: walk(c)
        walk(root)
        return u

    # ---- emission machinery (repo verbatim)
    def emit(self, root, feat_lines_fn, header_lines, out_path, tree_line_limit):
        REFC = {}
        def count_refs(k):
            if k in REFC: REFC[k] += 1; return
            REFC[k] = 1
            if k[0] == "N":
                for _, c in k[2]: count_refs(c)
        count_refs(root)
        NEED = {}
        def need_of(k):
            if k in NEED: return NEED[k]
            if k[0] == "T": NEED[k] = frozenset(); return NEED[k]
            s = {k[1]}
            for _, c in k[2]: s |= need_of(c)
            NEED[k] = frozenset(s); return s
        need_of(root)
        HNAME = {}; order = []
        _seen = set()
        def topo(k):
            if k[0] != "N" or k in _seen: return
            _seen.add(k)
            for _, c in k[2]: topo(c)
            if REFC[k] > 1:
                HNAME[k] = f"_n{len(HNAME)}"
                order.append(k)
        topo(root)
        NAMES = self.NAMES
        EMIT_VISITS = {}
        def emit_sub(k, ind):
            EMIT_VISITS[k] = EMIT_VISITS.get(k, 0) + 1
            pad = " " * ind
            if k[0] == "T":
                return [f"{pad}return {k[1]}"]
            if REFC[k] > 1:
                args = ", ".join("f_" + NAMES[i] for i in sorted(need_of(k)))
                return [f"{pad}return {HNAME[k]}({args})"]
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
            args = ", ".join("f_" + NAMES[i] for i in sorted(need_of(k)))
            helper_lines.append(f"def {HNAME[k]}({args}):")
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
          f"emit visits {len(EMIT_VISITS)} nodes / {sum(EMIT_VISITS.values())} total, "
          f"shared helpers {len(HNAME)}")
        if total_tree_lines > tree_line_limit:
            return {"emitted": False, "helpers": len(HNAME), "tree_lines": total_tree_lines,
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

# ================================================================ family specs
FAMS = {
    "duel": dict(kind="d5", file="pawn_duel_algebraic.py",
                 eval="eval_pawn_duel_algebraic", mv="DUEL_MV", phase_tag="6c" if N == 4 else "phase-1-oracle",
                 desc=None),
    "asym_3p": dict(kind="d7", file="asym_3p_algebraic.py",
                    eval="eval_asym_3p_algebraic", mv="ASYM3_MV",
                    phase_tag="7a" if N == 4 else "phase-1-oracle",
                    desc=[f"# Zero-lookup algebraic evaluator for the {N}x{N} K2P 3-pawn asymmetric family",
                          "# ((1,2)/(2,1) + closed tails (2,0)/(0,2)), {n:,} legal states."]),
    "four_pawn": dict(kind="d7", file="four_pawn_algebraic.py",
                      eval="eval_four_pawn_algebraic", mv="F4P_MV",
                      phase_tag="7b" if N == 4 else "phase-1-oracle",
                      desc=[f"# Zero-lookup algebraic evaluator for the {N}x{N} K2P (2,2) four-pawn family",
                            "# {n:,} legal states."]),
}
FAMS["full"] = dict(kind="d7", file="full_space_algebraic.py",
                    eval="eval_full_space_algebraic", mv="VAL",
                    phase_tag="phase-1-oracle",
                    desc=[f"# Zero-lookup algebraic evaluator for the {N}x{N} K2P FULL legal space",
                          "# (all material classes 0-2 pawns per side), {n:,} legal states."])

def header5(spec, n_legal, n_canon, n_bare_orbits, n_non_bare, n_bare_states, tail_used, key):
    return [
        f"# {spec['file']} - AUTO-GENERATED by scripts_general/compress_family_general.py",
        f"# Zero-lookup algebraic evaluator for the {N}x{N} K2P 1v1 pawn duel family (|W|<=1, |B|<=1).",
        "#",
        f"# Compiled from the exact {spec['phase_tag']} retrograde sub-game ({n_legal:,} legal states) via a",
        f"# multi-way MTBDD over the ORBIT-CANONICAL feature rows: {n_legal:,} raw states ->",
        f"# {n_canon:,} canonical orbits under G = <H, V'>; {n_bare_orbits:,} orbits are bare kings (all",
        f"# draws, early return 0), leaving {n_non_bare:,} non-bare canonical orbit representatives",
        "# over which the 24-feature basis" + (f" + {len(TAIL_NAMES)}-coordinate canonical tail" if tail_used else "") + " is exact.",
        "#",
        "# The input is canonicalized internally by pure integer arithmetic (min over",
        "# the 4 orbit images enc(id), enc(H), enc(V'), enc(HV')), so orbit-equivalent",
        "# inputs give one verdict.  Pure integer arithmetic, Chebyshev distances and",
        "# nested if/then/else only: NO dictionary lookups, NO numpy arrays, NO tables.",
        "#",
        f"# Signature: {spec['eval']}(w, b, pw, pb, tau)",
        f"#   w, b  : white / black king squares 0..{NN - 1} (file = q % {N}, rank = q // {N})",
        "#   pw, pb: white / black pawn squares, -1 if absent",
        "#   tau   : side to move (0 = White, 1 = Black)",
        "# Returns : mover-relative value, 1 = mover win, 2 = mover loss, 0 = draw",
        f"#           (equals {key}[sid] of the exact tablebase on every legal family state).",
        f"# Bare-king inputs (pw < 0 and pb < 0) return 0: all {n_bare_states:,} such states are draws.",
        "# Behavior on inputs outside the legal family is unspecified (garbage in, garbage out).",
        "",
        "",
        f"def {spec['eval']}(w, b, pw, pb, tau):",
        "    if pw < 0 and pb < 0:",
        "        return 0",
    ]

def header7(spec, n_legal, key):
    desc = [d.replace("{n:,}", f"{n_legal:,}") for d in spec["desc"]]
    return [
        f"# {spec['file']} - AUTO-GENERATED by scripts_general/compress_family_general.py",
    ] + desc + [
        "#",
        f"# Compiled from the exact {spec['phase_tag']} retrograde {'sub-game' if N == 4 else 'oracle'} via a multi-way MTBDD over the",
        "# canonical 56-feature basis (50-feature O(1) semantic geometry + canonical-",
        "# coordinate tail).  Pure integer arithmetic, Chebyshev distances and nested",
        "# if/then/else only: NO dictionary lookups, NO numpy arrays, NO precomputed tables.",
        "#",
        f"# Signature: {spec['eval']}(w, b, pw1, pw2, pb1, pb2, tau)",
        f"#   w, b        : white / black king squares 0..{NN - 1} (file = q % {N}, rank = q // {N})",
        "#   pw1, pw2    : white pawn squares (any order), -1 if absent",
        "#   pb1, pb2    : black pawn squares (any order), -1 if absent",
        "#   tau         : side to move (0 = White, 1 = Black)",
        "# Returns      : mover-relative value, 1 = mover win, 2 = mover loss, 0 = draw",
        f"#                (equals {key}[sid] on every legal family state).",
        "# The input is canonicalized internally under G = <H, V'> (file mirror; rank",
        "# mirror + color swap + tau flip), so orbit-equivalent inputs give one verdict.",
        "# Behavior on inputs outside the legal family is unspecified (garbage in, out).",
        "",
        "",
        f"def {spec['eval']}(w, b, pw1, pw2, pb1, pb2, tau):",
    ]

# ================================================================ core build
# ---------------------------------------------------------------- E3 trace
def trace_deepest(comp, root):
    """E3 critical-path trace: walk the deepest root-to-leaf path of the built
    MTBDD.  At each node follow the child whose subtree has the greatest depth
    (tie-break: smallest branch value).  Feature indices STRICTLY INCREASE along
    any path (children are built at bi+1), so a feature can appear at most once
    per path - the walk measures WHICH and HOW MANY distinct features the
    deepest path visits, not repeats.  Row intervals are recovered by
    re-partitioning each node's column exactly as build() does, so
    rows_before/rows_after show where the path actually discriminates."""
    memo_d = {}
    def depth(k):
        if k[0] == "T": return 0
        if k in memo_d: return memo_d[k]
        d = 1 + max(depth(c) for _, c in k[2]); memo_d[k] = d; return d
    path = []
    i0, i1 = 0, comp.R
    k = root
    while k[0] == "N":
        bip = k[1]; col = comp.COLS[bip]
        ch = {v: c for v, c in k[2]}
        best = None
        j = i0
        while j < i1:
            v = int(col[j]); j2 = bisect_right(col, v, j, i1)
            c = ch[v]          # node was built over this interval: branch
                               # values match this partition exactly
            d = depth(c)
            if best is None or d > best[0] or (d == best[0] and v < best[1]):
                best = (d, v, c, j, j2)
            j = j2
        d, v, c, a, b = best
        path.append({"step": len(path) + 1, "feature": comp.NAMES[bip],
                     "value_taken": v, "rows_before": int(i1 - i0),
                     "rows_after": int(b - a), "subtree_depth": int(d)})
        i0, i1 = a, b
        k = c
    label = int(k[1])
    feats = sorted({p["feature"] for p in path})
    return {"depth": len(path), "terminal_label": label,
            "terminal": {0: "draw", 1: "win", 2: "loss"}.get(label, str(label)),
            "distinct_features": feats,
            "n_distinct_features": len(feats),
            "feature_counts": {f: sum(1 for p in path if p["feature"] == f)
                               for f in feats},
            "path": path}

def core_build(fam, ids, mode, MV, key, lpath, mask_key=None, mask=None, emit=True):
    """One compile attempt over `ids` (np.int64 array of state slots)."""
    spec = FAMS[fam]; kind = spec["kind"]
    d5 = (kind == "d5")
    stage_mark(f"load/orbit start [{fam}/{mode}] ({len(ids):,} states)")
    from array import array as pyarray
    encs = pyarray('q')
    orbit_hist = defaultdict(int)
    hom_bad = 0
    n_bare_states = 0
    ids_list = ids.tolist()
    if d5:
        for s in ids_list:
            wk, bk, ws, bs, stm = unpack(s)
            pw = next(iter(ws)) if ws else -1
            pb = next(iter(bs)) if bs else -1
            if pw < 0 and pb < 0: n_bare_states += 1
            st = (wk, bk, pw, pb, stm)
            members = (st, t_H5(st), t_V5(st), t_H5(t_V5(st)))
            vals = set()
            for m in members:
                ms = sid5(*m)
                assert mask[ms], f"orbit member {m} of state {s} outside family"
                vals.add(int(MV[ms]))
            if len(vals) != 1: hom_bad += 1
            orbit_hist[len(set(members))] += 1
            encs.append(enc5(*canon5(st)))
            if len(encs) % 1_000_000 == 0: mem_guard("orbit quotient")
    else:
        for s in ids_list:
            st = sort7(*unpack(s))
            members = (st, t_H7(st), t_V7(st), t_H7(t_V7(st)))
            vals = set()
            for m in members:
                ms = sid7(*m)
                assert mask[ms], f"orbit member {m} of state {s} outside family"
                vals.add(int(MV[ms]))
            if len(vals) != 1: hom_bad += 1
            orbit_hist[len(set(members))] += 1
            encs.append(enc7(*canon7(st)))
            if len(encs) % 1_000_000 == 0: mem_guard("orbit quotient")
    assert hom_bad == 0, f"value homogeneity violated in {hom_bad} states"
    del ids_list; gc.collect()   # 6.7M-element Python int list is dead weight from here on
    enc_u = np.unique(np.frombuffer(encs, dtype=np.int64))
    n_canon = len(enc_u)
    n_orbit_sizes = {str(k): v for k, v in sorted(orbit_hist.items())}
    P(f"1. orbit quotient G=<H,V'> [{fam}/{mode}]: legal states {len(ids):,}, canonical orbits {n_canon:,}, "
      f"orbit size histogram {n_orbit_sizes}, value-homogeneity violations {hom_bad}")
    del encs; gc.collect()
    stage_mark(f"orbit quotient done [{fam}/{mode}]")

    # ---- feature rows over canonical orbit representatives
    pairs = []
    n_bare_canon = 0
    tail_used = False
    if d5:
        cst = []
        non_bare = 0
        for e in enc_u.tolist():
            st = dec5(e)
            if st[2] < 0 and st[3] < 0:
                n_bare_canon += 1; continue
            # knight block inserted after the semantic features, before any tail
            pairs.append((ext_feat(features5(*st), ()), int(MV[sid5(*st)])))
            cst.append(st)
            non_bare += 1
            if non_bare % 500_000 == 0: mem_guard("feature extraction")
        n_non_bare = non_bare
        P(f"   bare-king states {n_bare_states:,}: all ground-truth draws (early return 0); "
          f"bare-king canonical orbits {n_bare_canon:,}; non-bare rows {n_non_bare:,}")
        # repo duel flow: semantic-only scan first; conditional 4-coordinate tail
        comp_sem = Compressor(ext_names(BASE_NAMES, []), ext_sem(24))
        if pairs:
            comp_sem.load_rows(pairs, f"{fam}/{mode} semantic-only")
        else:
            comp_sem.R = 0; comp_sem.COLS = []; comp_sem.LAB0 = np.empty(0, dtype=np.int8)
            comp_sem.conf = {"distinct_semantic_rows": 0, "semantic_conflicting_groups": 0,
                             "distinct_full_rows": 0, "full_conflicting_groups": 0}
        tail_used = comp_sem.conf["full_conflicting_groups"] > 0
        del pairs; gc.collect()
        if tail_used:
            pairs = [(ext_feat(features5(*st), st[:4]), int(MV[sid5(*st)])) for st in cst]
            comp = Compressor(ext_names(BASE_NAMES, TAIL_NAMES), ext_sem(24))
            comp.load_rows(pairs, f"{fam}/{mode} full+tail")
        else:
            comp = comp_sem
        del cst; gc.collect()
        conf_sem = comp_sem.conf
    else:
        for e in enc_u.tolist():
            st = dec7(e)
            f = features7(*st)
            if f is None:
                n_bare_canon += 1; continue
            # knight block inserted after the 50 semantic features, before the
            # 6-coordinate tail (features7 = semantic ++ tail, NSEM7 = 50)
            pairs.append((ext_feat(f[:NSEM7], f[NSEM7:]), int(MV[sid7(*st)])))
            if len(pairs) % 500_000 == 0: mem_guard("feature extraction")
        n_non_bare = len(pairs)
        if n_bare_canon:
            P(f"   bare-king canonical orbits excluded from rows: {n_bare_canon:,} (early return 0)")
        comp = Compressor(ext_names(NAMES7[:NSEM7], NAMES7[NSEM7:]), ext_sem(NSEM7))
        if pairs:
            comp.load_rows(pairs, f"{fam}/{mode}")
        else:
            comp.R = 0; comp.COLS = []; comp.LAB0 = np.empty(0, dtype=np.int8)
            comp.conf = {"distinct_semantic_rows": 0, "semantic_conflicting_groups": 0,
                         "distinct_full_rows": 0, "full_conflicting_groups": 0}
        conf_sem = comp.conf
    stage_mark(f"feature extraction done [{fam}/{mode}] ({comp.R:,} rows)")
    nsem_d = ext_sem(24) if d5 else ext_sem(NSEM7)
    P(f"2. feature basis [{fam}/{mode}]: {comp.NB} features "
      f"{'(knight extension: +13 constant knight features) ' if EXT_KNIGHTS else ''}"
      f"(semantic {nsem_d} + coordinate tail {comp.NB - nsem_d}"
      f"{', tail used' if (d5 and tail_used) else (', semantic basis sufficient (no tail)' if d5 else '')}); "
      f"non-bare canonical rows {n_non_bare:,}; "
      f"distinct semantic rows {(conf_sem['distinct_full_rows'] if d5 else conf_sem['distinct_semantic_rows']):,} -> conflicting "
      f"{(conf_sem['full_conflicting_groups'] if d5 else conf_sem['semantic_conflicting_groups']):,}; "
      f"distinct full rows {comp.conf['distinct_full_rows']:,} -> conflicting "
      f"{comp.conf['full_conflicting_groups']:,} (must be 0)")
    assert comp.conf["full_conflicting_groups"] == 0, "feature basis not discriminative on canonical rows"
    if comp.R == 0:
        P("   (no non-bare rows: nothing to compile)")
        return {"mode": mode, "states": len(ids), "canonical": n_canon,
                "rows": 0, "nodes": 0, "paths": 0, "depth": 0, "note": "all bare"}

    # ---- MTBDD (+ boolean win/loss BDDs unless skipped)
    skip_wl = args.skip_winloss or comp.R > 300_000
    stage_mark(f"mtbdd build start [{fam}/{mode}]")
    mt_root = comp.build_tree(comp.LAB0)
    mn, mp, md = comp.stats(mt_root)
    NODES_TOTAL_WL = 0
    if skip_wl:
        wn = ln = wp = lp = wd = ld = None
        P(f"3. ROBDD/MTBDD [{fam}/{mode}]: rows {comp.R:,}, blocks {comp.NB} "
          f"(win/loss BDDs skipped: rows > 300k or --skip-winloss)")
        P(f"   MTBDD   : nodes {mn:6d}, paths {mp:6d}, max depth {md} "
          f"(3 terminals: 1=win, 2=loss, 0=draw)")
    else:
        comp.reset_build()
        win_root = comp.build_label(1)
        wn, wp, wd = comp.stats(win_root)
        comp.reset_build()
        loss_root = comp.build_label(2)
        ln, lp, ld = comp.stats(loss_root)
        comp.reset_build()
        P(f"3. ROBDD/MTBDD [{fam}/{mode}]: rows {comp.R:,}, blocks {comp.NB}")
        P(f"   win-BDD : nodes {wn:6d}, paths {wp:6d}, max depth {wd}")
        P(f"   loss-BDD: nodes {ln:6d}, paths {lp:6d}, max depth {ld}")
        P(f"   MTBDD   : nodes {mn:6d}, paths {mp:6d}, max depth {md} "
          f"(3 terminals: 1=win, 2=loss, 0=draw)")
        NODES_TOTAL_WL = wn + ln
        del win_root, loss_root
    stage_mark(f"mtbdd build done [{fam}/{mode}]")
    gc.collect()
    # crash-resilient partial dump (stats through the build, before verify)
    with open(os.path.join(args.out_dir, f"compression_{fam}_{mode}_partial.json"), "w") as fh:
        json.dump({"mode": mode, "family": fam, "states": int(len(ids)),
                   "canonical_orbits": int(n_canon), "non_bare_rows": int(n_non_bare),
                   "mtbdd": {"nodes": mn, "paths": mp, "max_depth": md},
                   "win_loss_bdds": None if skip_wl else
                        {"win": {"nodes": wn, "paths": wp, "depth": wd},
                         "loss": {"nodes": ln, "paths": lp, "depth": ld}},
                   "stages": STAGES[-12:]}, fh, indent=1)

    # ---- E3 trace mode: dump the deepest-path trace and skip emission/verify
    if args.trace:
        tr = trace_deepest(comp, mt_root)
        tpath = os.path.join(args.out_dir, f"trace_{fam}_{mode}.json")
        with open(tpath, "w") as fh:
            json.dump({"family": fam, "mode": mode, "n": N, "kind": kind,
                       "states": int(len(ids)), "canonical_orbits": int(n_canon),
                       "non_bare_rows": int(n_non_bare), "features_total": comp.NB,
                       "feature_names": list(comp.NAMES),
                       "mtbdd": {"nodes": mn, "paths": mp, "max_depth": md},
                       "trace": tr}, fh, indent=1)
        P(f"4. E3 trace [{fam}/{mode}]: deepest path depth {tr['depth']} "
          f"({tr['n_distinct_features']} distinct features, terminal {tr['terminal']}) "
          f"-> {tpath}")
        return {"mode": mode, "family": fam, "kind": kind, "states": int(len(ids)),
                "canonical_orbits": int(n_canon), "non_bare_rows": int(n_non_bare),
                "mtbdd": {"nodes": mn, "paths": mp, "max_depth": md},
                "trace_file": tpath, "trace": tr}

    # ---- emission + verification
    res = {"mode": mode, "family": fam, "kind": kind, "states": int(len(ids)),
           "canonical_orbits": int(n_canon), "bare_canonical_orbits": int(n_bare_canon),
           "non_bare_rows": int(n_non_bare),
           "orbit_size_histogram": n_orbit_sizes,
           "homogeneity_violations": hom_bad,
           "feature_basis": {
               "semantic_features": nsem_d,
               "tail": comp.NB - nsem_d,
               "tail_used": (bool(tail_used) if d5 else True),
               "distinct_semantic_rows": (conf_sem["distinct_full_rows"] if d5
                                          else conf_sem["distinct_semantic_rows"]),
               "semantic_conflicting_groups": (conf_sem["full_conflicting_groups"] if d5
                                               else conf_sem["semantic_conflicting_groups"]),
               "distinct_full_rows": comp.conf["distinct_full_rows"],
               "full_conflicting_groups": comp.conf["full_conflicting_groups"],
               "names": comp.NAMES},
           "mtbdd": {"nodes": mn, "paths": mp, "max_depth": md},
           "win_loss_bdds": None if skip_wl else
                {"win": {"nodes": wn, "paths": wp, "depth": wd},
                 "loss": {"nodes": ln, "paths": lp, "depth": ld},
                 "total_nodes": NODES_TOTAL_WL + mn},
           "stages": STAGES[-12:]}
    if emit:
        enc_head = (header5(spec, len(ids), n_canon, n_bare_canon, n_non_bare,
                            n_bare_states, comp.NB > ext_sem(24), key)
                    if d5 else header7(spec, len(ids), key))
        out_path = os.path.join(args.emit_dir, spec["file"])
        em = comp.emit(mt_root,
                       guard_feat_lines(feat_lines5,
                                        set(range(ext_sem(24), ext_sem(24) + len(KNIGHT_NAMES)))
                                        if EXT_KNIGHTS else set(), "d5")
                       if d5 else
                       guard_feat_lines(feat_lines7,
                                        set(range(ext_sem(NSEM7), ext_sem(NSEM7) + len(KNIGHT_NAMES)))
                                        if EXT_KNIGHTS else set(), "d7"),
                       enc_head + (canon_block5() if d5 else canon_block7()) +
                       ["    # ---- O(1) geometric features of the canonical state"],
                       out_path, args.tree_line_limit)
        res["emission"] = em
        # release the build state before forking the verifier (4 GB sandbox)
        comp.COLS = None; comp.CTX = None; comp.NODES = None
        comp.LAB0 = None; comp.LABV = None
        mt_root = None; MV = None
        gc.collect()
        stage_mark(f"build memory released [{fam}/{mode}]")
        if em.get("emitted"):
            vres = run_verify(spec, out_path, lpath, key, ids, fam, mode, mask_key)
            res["verification"] = vres
        else:
            P(f"   emission over line budget ({em['tree_lines']:,} > {args.tree_line_limit:,}); "
              f"evaluator NOT written; verification n/a")
            res["verification"] = None
    del mt_root; gc.collect()
    return res

# ================================================================ verification
def run_verify(spec, emit_path, lpath, key, ids, fam, mode, mask_key=None):
    """Independent subprocess: fresh import of the emitted evaluator, compare
    against the labels on the compiled state set, absolute check vs the exact
    oracle OW3, break check vs frozen Psi_v7b (N=4 only), plus benchmarks."""
    d5 = spec["kind"] == "d5"
    sample_path = ""
    if mode == "sampled":
        sample_path = os.path.join(args.out_dir, f"sample_ids_{fam}.npy")
        np.save(sample_path, ids)
    vpath = os.path.join(args.out_dir, f"verify_{fam}_algebraic.py")
    enum = []
    enum.append("import sys, json, time, importlib.util")
    enum.append("import numpy as np")
    enum.append("from itertools import combinations")
    enum.append(f"N = {N}; NN = {N*N}; RAD = {NN + 1}")
    enum.append(f"KPI2 = np.full(({NN}, {NN}), -1, dtype=np.int32)")
    enum.append("_NEI = []")
    enum.append("_ADJ = [0]*NN")
    enum.append("for _s in range(NN):")
    enum.append("    _x, _y = _s % N, _s // N")
    enum.append("    _l = []")
    enum.append("    for _dx in (-1, 0, 1):")
    enum.append("        for _dy in (-1, 0, 1):")
    enum.append("            if _dx == _dy == 0: continue")
    enum.append("            _nx, _ny = _x + _dx, _y + _dy")
    enum.append("            if 0 <= _nx < N and 0 <= _ny < N: _l.append(N*_ny + _nx)")
    enum.append("    _NEI.append(tuple(_l)); _ADJ[_s] = sum(1 << t for t in _l)")
    enum.append("_KP = [(a, b) for a in range(NN) for b in range(NN) if a != b and not ((_ADJ[a] >> b) & 1)]")
    enum.append("_PS = tuple(N*y + x for y in range(1, N-1) for x in range(N))")
    enum.append("_CF = [()]")
    enum.append("for _r in (1, 2): _CF += list(combinations(_PS, _r))")
    enum.append("_PP = [(wi, bi) for wi, wc in enumerate(_CF) for bi, bc in enumerate(_CF) if not (set(wc) & set(bc))]")
    enum.append("for _i, _k in enumerate(_KP): KPI2[_k] = _i")
    enum.append("PPI2 = np.full((len(_CF), len(_CF)), -1, dtype=np.int32)")
    enum.append("for _i, _p in enumerate(_PP): PPI2[_p] = _i")
    enum.append("NSV = len(_KP) * len(_PP) * 2")
    enum.append("_sid = np.arange(NSV, dtype=np.int64)")
    enum.append("_stm = (_sid % 2).astype(np.int8)")
    enum.append("_WK = np.array([k[0] for k in _KP], dtype=np.int32)[_sid // (2*len(_PP))]")
    enum.append("_BK = np.array([k[1] for k in _KP], dtype=np.int32)[_sid // (2*len(_PP))]")
    enum.append("_c1 = np.full(len(_CF), -1, dtype=np.int8); _c2 = np.full(len(_CF), -1, dtype=np.int8)")
    enum.append("for _i, _c in enumerate(_CF):")
    enum.append("    if len(_c) >= 1: _c1[_i] = _c[0]")
    enum.append("    if len(_c) == 2: _c2[_i] = _c[1]")
    enum.append("_wis = np.array([p[0] for p in _PP], dtype=np.int32)[(_sid // 2) % len(_PP)]")
    enum.append("_bis = np.array([p[1] for p in _PP], dtype=np.int32)[(_sid // 2) % len(_PP)]")
    enum.append("W1 = _c1[_wis].astype(np.int32); W2 = _c2[_wis].astype(np.int32)")
    enum.append("B1 = _c1[_bis].astype(np.int32); B2 = _c2[_bis].astype(np.int32)")
    enum.append(f"PW2ID = {{}}")
    enum.append("for _i, _c in enumerate(_CF):")
    enum.append("    if len(_c) == 0: PW2ID[(-1, -1)] = _i")
    enum.append("    elif len(_c) == 1: PW2ID[(-1, _c[0])] = _i")
    enum.append("    else: PW2ID[(_c[0], _c[1])] = _i")
    enum.append("def sid7(wk, bk, w1, w2, b1, b2, tau):")
    enum.append("    if w1 > w2: w1, w2 = w2, w1")
    enum.append("    if b1 > b2: b1, b2 = b2, b1")
    enum.append("    return (int(KPI2[wk, bk]) * len(_PP) + int(PPI2[PW2ID[(w1, w2)], PW2ID[(b1, b2)]])) * 2 + int(tau)")
    lines = []
    A = lines.append
    A(f"spec = importlib.util.spec_from_file_location('alg', {emit_path!r})")
    A("mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)")
    A(f"ev = mod.{spec['eval']}")
    A(f"LBL_NPZ = np.load({lpath!r})")
    A(f"_mv = LBL_NPZ[{key!r}]")
    A("if int(_mv.max()) >= 3:")
    A("    _mv = np.where(_mv == 3, 0, np.where(_mv >= 1, _mv, -1)).astype(np.int8)")
    A(f"ORC = np.load({ORACLE_NPZ!r})")
    A("_VAL = ORC['VAL']; _STM = ORC['STMW']")
    A("_FLIP = np.array([-1, 0, 2, 1, 3], dtype=np.int8)")
    A("_ow = np.where(_STM, _VAL, _FLIP[np.clip(_VAL + 1, 0, 4)]).astype(np.int8)")
    A("_legal = _VAL >= 1")
    A("OW3 = np.where(_ow == 1, 1, np.where(_ow == 2, -1, 0)).astype(np.int8); OW3[~_legal] = 0")
    if PSI is not None:
        A(f"PSI = np.load({REPO_DL + '/phase7b_results.npz'!r})['PSI_V7B']")
    else:
        A("PSI = None")
    if mode == "sampled":
        A(f"ids = np.load({sample_path!r}).tolist()")
    else:
        if mask_key is not None:
            A(f"MASK = LBL_NPZ[{mask_key!r}].astype(bool)")
        else:
            A("_wn = ((W1 >= 0).astype(np.int8) + (W2 >= 0).astype(np.int8))")
            A("_bn = ((B1 >= 0).astype(np.int8) + (B2 >= 0).astype(np.int8))")
            A(f"MASK = {fam_mask_expr(fam)}")
        A("ids = np.nonzero(MASK)[0].tolist()")
    A(f"VL = {int(args.verify_limit)}; SEED = {args.seed}")
    A("if VL and len(ids) > VL:")
    A("    _rg = np.random.default_rng(SEED)")
    A("    _ix = np.sort(_rg.choice(len(ids), VL, replace=False))")
    A("    ids = [ids[i] for i in _ix]")
    A("MV_ = _mv")
    A("m_val = 0; m_abs = 0; brk = 0")
    A("KIND = 'd5'" if d5 else "KIND = 'd7'")
    A("for s in ids:")
    A("    s = int(s)")
    A("    wk = int(_WK[s]); bk = int(_BK[s]); stm = int(_stm[s])")
    A("    if KIND == 'd5':")
    A("        pw = max(int(W1[s]), int(W2[s])); pb = max(int(B1[s]), int(B2[s]))")
    A("        v = ev(wk, bk, pw, pb, stm)")
    A("    else:")
    A("        v = ev(wk, bk, int(W1[s]), int(W2[s]), int(B1[s]), int(B2[s]), stm)")
    A("    if v != int(MV_[s]): m_val += 1; continue")
    A("    if v != 0:")
    A("        a = (1 if stm == 0 else -1) if v == 1 else (-1 if stm == 0 else 1)")
    A("        if a != int(OW3[s]): m_abs += 1")
    A("        if PSI is not None and a != int(PSI[s]) and int(PSI[s]) == int(OW3[s]): brk += 1")
    A("# benchmark")
    A("DICT = {}")
    A("for s in ids[:2000]:")
    A("    s = int(s)")
    A("    if KIND == 'd5':")
    A("        DICT[s] = sid7(int(_WK[s]), int(_BK[s]), -1 if W1[s] < 0 and W2[s] < 0 else -1,")
    A("                       max(int(W1[s]), int(W2[s])), -1, max(int(B1[s]), int(B2[s])), int(_stm[s]))")
    A("    else:")
    A("        DICT[s] = sid7(int(_WK[s]), int(_BK[s]), int(W1[s]), int(W2[s]), int(B1[s]), int(B2[s]), int(_stm[s]))")
    A("args_ = []")
    A("for s in ids[:2000]:")
    A("    s = int(s)")
    A("    wk = int(_WK[s]); bk = int(_BK[s]); stm = int(_stm[s])")
    A("    if KIND == 'd5':")
    A("        args_.append((wk, bk, max(int(W1[s]), int(W2[s])), max(int(B1[s]), int(B2[s])), stm))")
    A("    else:")
    A("        args_.append((wk, bk, int(W1[s]), int(W2[s]), int(B1[s]), int(B2[s]), stm))")
    A("NREP = 30")
    A("t0 = time.perf_counter()")
    A("for _ in range(NREP):")
    A("    for a in args_: ev(*a)")
    A("t_alg = (time.perf_counter() - t0) / (NREP * len(args_)) * 1e6")
    A("t0 = time.perf_counter()")
    A("for _ in range(NREP):")
    A("    for s in list(DICT)[:2000]: DICT[s]")
    A("t_dic = (time.perf_counter() - t0) / (NREP * min(2000, len(DICT))) * 1e6")
    A("print(json.dumps({'verified_states': len(ids), 'value_mismatches': m_val,")
    A("    'absolute_mismatches': m_abs, 'breaks_vs_frozen_psi': brk,")
    A("    'us_per_state_algebraic': round(t_alg, 3), 'us_per_state_dict_raw': round(t_dic, 3)}))")
    with open(vpath, "w") as fh:
        fh.write("\n".join(enum + lines) + "\n")
    out = subprocess.run([sys.executable, vpath], capture_output=True, text=True, timeout=3600)
    if out.returncode != 0:
        P("VERIFICATION SUBPROCESS FAILED:"); P(out.stdout[-3000:]); P(out.stderr[-3000:])
        raise SystemExit(1)
    V = json.loads(out.stdout.strip().splitlines()[-1])
    P("5. verification (independent subprocess, fresh import):")
    if args.verify_limit:
        P(f"   SUBSET verification cap: {args.verify_limit:,} of the compiled state set (seeded)")
    P(f"   states {V['verified_states']}, value mismatches {V['value_mismatches']} (must be 0), "
      f"absolute mismatches {V['absolute_mismatches']} (must be 0), "
      f"breaks vs frozen Psi_v7b {V['breaks_vs_frozen_psi']} (must be 0 where checked)")
    assert V["value_mismatches"] == 0 and V["absolute_mismatches"] == 0, "verification failed"
    if PSI is not None:
        assert V["breaks_vs_frozen_psi"] == 0, "break vs frozen Psi_v7b"
    P(f"   benchmark us/state: algebraic {V['us_per_state_algebraic']}, raw dict[sid] {V['us_per_state_dict_raw']}")
    return V

# ================================================================ drivers
def fam_mask_expr(fam):
    if fam == "full": return "_legal"
    if fam == "duel": return "_legal & (_wn <= 1) & (_bn <= 1)"
    if fam == "asym_3p":
        return ("_legal & (((_wn == 1) & (_bn == 2)) | ((_wn == 2) & (_bn == 1))"
                " | ((_wn == 2) & (_bn == 0)) | ((_wn == 0) & (_bn == 2)))")
    if fam == "four_pawn": return "_legal & (_wn == 2) & (_bn == 2)"
    raise ValueError(fam)

def run_family(fam):
    """One per-family compile: full-family mode, sampled fallback on memory abort."""
    STAGES.clear()
    mask, MV, key, lpath, mask_key = load_labels(fam)
    ids = np.nonzero(mask)[0]
    P(f"== loads: {fam} family {len(ids):,} legal states ==")
    if args.force_sampled:
        take = min(args.sample, len(ids))
        rng = np.random.default_rng(args.seed)
        sids = np.sort(rng.choice(ids, size=take, replace=False))
        P(f"   --force-sampled: uniform sample {len(sids):,} of {len(ids):,}")
        res = core_build(fam, sids, "sampled", MV, key, lpath, mask_key, mask)
        res["extrapolation"] = {
            "note": "SAMPLED MODE - node count is an extrapolation input, not a full-family result",
            "sample_states": int(len(sids)), "family_states": int(len(ids)),
            "scaled_nodes": int(round(res["mtbdd"]["nodes"] * len(ids) / max(1, len(sids))))}
        return res
    try:
        return core_build(fam, ids, "full-family", MV, key, lpath, mask_key, mask)
    except MemoryCeiling as e:
        if args.trace:
            raise   # a sampled MTBDD would give a fake trace - fail loudly instead
        P(f"   MEMORY CEILING: {e} -> fallback to SAMPLED mode ({args.sample:,} states)")
        gc.collect()
        take = min(args.sample, len(ids))
        rng = np.random.default_rng(args.seed)
        sids = np.sort(rng.choice(ids, size=take, replace=False))
        res = core_build(fam, sids, "sampled", MV, key, lpath, mask_key, mask)
        res["extrapolation"] = {
            "note": "SAMPLED MODE - node count is an extrapolation input, not a full-family result",
            "sample_states": int(len(sids)), "family_states": int(len(ids)),
            "scaled_nodes": int(round(res["mtbdd"]["nodes"] * len(ids) / max(1, len(sids))))}
        return res

def stratified_sample(k):
    """Proportional-to-family-size sample across duel/asym_3p/four_pawn."""
    fams = {}
    legal = LEGAL
    for fam in ("duel", "asym_3p", "four_pawn"):
        m, _ = family_mask(fam, None)
        fams[fam] = np.nonzero(m)[0]
    tot = sum(len(v) for v in fams.values())
    rng = np.random.default_rng(args.seed)
    out = []
    for fam, arr in fams.items():
        take = round(k * len(arr) / tot)
        idx = np.sort(rng.choice(arr, size=min(take, len(arr)), replace=False))
        out.append(idx)
        P(f"   sample[{fam}]: {len(idx):,} of {len(arr):,} (proportional)")
    return np.concatenate(out)

def write_family_json(fam, mode, res):
    p = os.path.join(args.out_dir, f"compression_{fam}_{mode}_results.json")
    with open(p, "w") as fh:
        json.dump(res, fh, indent=1)
    P(f"   json -> {p}")

def update_summary(entry_key, entry):
    if args.trace:
        P("   (trace mode: compression_summary.json left untouched)")
        return
    sp = f"/home/z/my-project/research/k2p/compression_summary.json"
    try:
        summ = json.load(open(sp))
    except Exception:
        summ = {"runs": {}}
    summ.setdefault("runs", {})[entry_key] = entry
    with open(sp, "w") as fh:
        json.dump(summ, fh, indent=1)
    P(f"   summary updated -> {sp}")

def main():
    grand = {"n": N, "family_cli": args.family, "mem_ceiling_mib": args.mem_ceiling_mib}
    if FAM == "all":
        per = {}
        for fam in ("duel", "asym_3p", "four_pawn"):
            res = run_family(fam)
            write_family_json(fam, res["mode"], res)
            per[fam] = res
        # partition checks (repo gen_4p.py verbatim semantics)
        masks = []
        for fam in ("duel", "asym_3p", "four_pawn"):
            m, _ = family_mask(fam, None)
            masks.append(m.astype(np.int8))
        stack = masks[0] + masks[1] + masks[2]
        assert bool((stack <= 1).all()), "family masks overlap"
        assert bool(((masks[0] | masks[1] | masks[2]).astype(bool) == LEGAL).all()), \
            "families do not cover the legal space"
        P("   partition check: duel + asym_3p + four_pawn are pairwise disjoint and "
          "cover the legal space: OK")
        total_nodes = sum(r["mtbdd"]["nodes"] for r in per.values())
        grand["per_family"] = {f: {"mode": r["mode"], "states": r["states"],
                                   "canonical_orbits": r["canonical_orbits"],
                                   "rows": r.get("non_bare_rows"),
                                   "semantic_conflicts": r["feature_basis"]["semantic_conflicting_groups"],
                                   "nodes": r["mtbdd"]["nodes"],
                                   "depth": r["mtbdd"]["max_depth"],
                                   "ratio": round(r["states"] / max(1, r["mtbdd"]["nodes"]), 1)}
                               for f, r in per.items()}
        grand["router_total_nodes"] = total_nodes
        P(f"== TOTAL (material router) ==  nodes {total_nodes}  "
          f"ratio 1:{sum(r['states'] for r in per.values()) / max(1, total_nodes):.1f}")
        update_summary(f"n{N}_all", grand)
    elif FAM == "full":
        lpath_full = os.path.join(SCRIPT_DIR, f"out_n{N}", "phase1_values.npz") if N != 4 \
            else os.path.join(REPO_DL, "phase1_values.npz")
        lbl = np.load(lpath_full)
        MV_full = np.where(lbl["VAL"] == 3, 0, np.where(lbl["VAL"] >= 1, lbl["VAL"], -1)).astype(np.int8)
        legal_ids = np.nonzero(LEGAL)[0]
        mode = "full"
        if args.trace:
            # E3 trace mode: single full-space build + deepest-path trace only;
            # no ladder, no per-family re-builds, no summary updates.
            res = core_build("full", legal_ids, "full", MV_full, "VAL", lpath_full, None, LEGAL)
            write_family_json("full", "full", res)
            P(f"total runtime {time.time() - T0:.1f}s (trace mode: ladder/per-family/emission skipped)")
            R.append("")  # keep transcript writer shape consistent
            with open(os.path.join(args.out_dir, f"compression_{FAM}_transcript.txt"), "w") as fh:
                fh.write("\n".join(R) + "\n")
            return
        try:
            res = core_build("full", legal_ids, "full", MV_full, "VAL", lpath_full, None, LEGAL)
        except MemoryCeiling as e:
            P(f"== LADDER step 1 (full space) ABORTED: {e}")
            if args.no_ladder:
                res = {"mode": "full", "family": "full", "aborted": True,
                       "abort_stage": str(e),
                       "note": "full-space attempt aborted at the memory ceiling; "
                               "ladder steps 2/3 are driven as separate runs",
                       "states": int(len(legal_ids))}
            elif args.force_sampled:
                P(f"== LADDER step 3: stratified sample of {args.sample:,} states")
                gc.collect()
                sids = stratified_sample(args.sample)
                res = core_build("full", sids, "sampled", MV_full, "VAL", lpath_full, None, LEGAL)
                res["extrapolation"] = {
                    "note": "SAMPLED MODE - node count is an extrapolation input, not a full-space result",
                    "sample_states": int(len(sids)), "space_states": int(LEGAL.sum()),
                    "scaled_nodes": int(round(res["mtbdd"]["nodes"] * int(LEGAL.sum()) / max(1, len(sids))))}
            else:
                P("== LADDER step 2: 2x2 family only (four_pawn mask)")
                gc.collect()
                m4, mk4 = family_mask("four_pawn", None)
                ids4 = np.nonzero(m4)[0]
                mode = "2x2-only"
                try:
                    res = core_build("four_pawn", ids4, "2x2-only", MV_full, "VAL", lpath_full, mk4, m4)
                except MemoryCeiling as e2:
                    P(f"== LADDER step 2 ABORTED: {e2}")
                    P(f"== LADDER step 3: stratified sample of {args.sample:,} states")
                    gc.collect()
                    sids = stratified_sample(args.sample)
                    res = core_build("full", sids, "sampled", MV_full, "VAL", lpath_full, None, LEGAL)
                    res["extrapolation"] = {
                        "note": "SAMPLED MODE - node count is an extrapolation input, not a full-space result",
                        "sample_states": int(len(sids)), "space_states": int(LEGAL.sum()),
                        "scaled_nodes": int(round(res["mtbdd"]["nodes"] * int(LEGAL.sum()) / max(1, len(sids))))}
        write_family_json("full", mode, res)
        grand["mode"] = mode
        grand["result"] = res
        update_summary(f"n{N}_full", grand)
        # per-family breakdown (per-family mode)
        P("== per-family builds (duel / asym_3p / four_pawn) for the router total ==")
        per = {}
        for fam in ("duel", "asym_3p", "four_pawn"):
            r = run_family(fam)
            write_family_json(fam, r["mode"], r)
            per[fam] = r
        grand["per_family"] = {f: {"mode": r["mode"], "states": r["states"],
                                   "nodes": r["mtbdd"]["nodes"],
                                   "depth": r["mtbdd"]["max_depth"],
                                   "ratio": round(r["states"] / max(1, r["mtbdd"]["nodes"]), 1)}
                               for f, r in per.items()}
        grand["router_total_nodes"] = sum(r["mtbdd"]["nodes"] for r in per.values())
        update_summary(f"n{N}_full", grand)
    else:
        res = run_family(FAM)
        write_family_json(FAM, res["mode"], res)
        grand["result"] = {k: v for k, v in res.items() if k != "feature_basis"}
        update_summary(f"n{N}_{FAM}", grand)
    with open(os.path.join(args.out_dir, f"compression_{FAM}_transcript.txt"), "w") as fh:
        fh.write("\n".join(R) + "\n")
    P(f"total runtime {time.time() - T0:.1f}s")

main()




