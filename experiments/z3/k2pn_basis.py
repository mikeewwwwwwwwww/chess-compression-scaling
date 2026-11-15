# scripts_general/k2pn_basis.py - shared K2P+N feature basis + orbit machinery.
#
# Single source of truth for the knight-extended feature basis used by:
#   - compress_family_general.py  (--feature-extension knights flag, PART 1)
#   - z3_injectivity.py           (symbolic feature encoding, PART 2/3)
#   - compress_class_k2pn.py      (class compressor, PART 4)
#   - k2pn_classes.py             (class oracle toolkit)
#
# State convention (identical to phase1_solver_general.py / the repo):
#   q = N*y + x, x = q % N, y = q // N; white advances +y (promotes y=N-1),
#   black advances -y (promotes y=0); pawn band y in 1..N-2; stm 0=White.
#   Uniform 7-coordinate state: (wk, bk, wp, bp, nw, nb, stm), -1 = piece absent.
#   VAL is MOVER-relative: 1 = mover wins, 2 = mover loses, 3 = draw.
#   MV labels: {0=draw, 1=win, 2=loss} (repo convention).
#
# Orbit group G = <H, V'> (repo semantics):
#   H  : file reflection x -> N-1-x, tau preserved
#   V' : rank reflection y -> N-1-y + W<->B colour swap + tau -> 1-tau
# The mover-relative value is invariant on orbits (checked, never assumed).
#
# TWO BASIS GENERATIONS live in this module:
#   v1  (5 king + 13 knight [+ 14 pawn]) - used by every COMMITTED compression
#       run (compress_family_general.py --feature-extension knights,
#       compress_class_k2pn.py); the ratio tables in V2_CHARTER 8.6 reflect v1.
#   v2  = v1 + signed knight offsets (piece->king, both kings) + king rank-edge
#       distances [+ signed pawn offsets] - added AFTER the v1 runs, in response
#       to the Z3 injectivity counterexamples (same-distance-different-square
#       mate-net geometry, and rank-translation ambiguity); tested by
#       z3_injectivity.py --basis v2 (default).  The v1 API below is unchanged;
#       v2 functions carry the _v2 suffix / *_V2_* / *_SIGNED_* names.

KNIGHT_NAMES = ["nW", "nB", "k_dist", "katt_w", "katt_b", "kchk_w", "kchk_b",
                "k_w_own", "k_b_own", "k_w_enemy", "k_b_enemy", "k_atk_w", "k_atk_b"]
KING_NAMES = ["tau", "d_AK", "opp", "e_w", "e_b"]
PAWN_NAMES = ["p_t_w", "p_t_b", "p_e_w", "p_e_b", "p_chk_w", "p_chk_b",
              "p_fwd_w", "p_fwd_b", "p_kdef_w", "p_kdef_b",
              "p_ndef_w", "p_ndef_b", "p_ncap_w", "p_ncap_b"]
TAIL_NAMES = ["cwk", "cbk", "cwp", "cbp", "cnw", "cnb"]
ABSENT = 99          # sentinel for "relation undefined" (repo uses 99 likewise)

# ---- v2 signed-offset extension (Z3 injectivity fix) ------------------------
# Signed per-axis deltas king - piece ("from piece to king"); the value is -1
# on BOTH axes when the piece is absent.  The -1 sentinel collides with a
# legitimate delta of -1, but presence is always decodable from the vector
# (nW/k_w_own/p_t_w etc. pin it), so vector-level equality stays unambiguous.
# Signed rank deltas are colour-swap ANTI-invariant (V' negates them) - the
# mirror-symmetry check in z3_injectivity.py handles this with a negation rule.
KING_V2_NAMES = ["re_w", "re_b"]           # min(y, N-1-y) of each king
KNIGHT_SIGNED_NAMES = ["k_dx_w", "k_dy_w",        # white knight -> OWN king
                       "k_dx_b", "k_dy_b",        # black knight -> OWN king
                       "k_dxe_w", "k_dye_w",       # white knight -> ENEMY king
                       "k_dxe_b", "k_dye_b"]       # black knight -> ENEMY king
PAWN_SIGNED_NAMES = ["p_dx_w", "p_dy_w",          # white pawn -> OWN king
                     "p_dx_b", "p_dy_b",          # black pawn -> OWN king
                     "p_dxe_w", "p_dye_w",        # white pawn -> ENEMY king
                     "p_dxe_b", "p_dye_b"]        # black pawn -> ENEMY king


def cheb(a, b, N):
    """Chebyshev distance; ABSENT if either endpoint is absent."""
    if a < 0 or b < 0:
        return ABSENT
    dx = a % N - b % N
    dy = a // N - b // N
    if dx < 0: dx = -dx
    if dy < 0: dy = -dy
    return dx if dx > dy else dy


def knight_att(a, b, N):
    """Does piece on square a attack square b with a KNIGHT move?"""
    if a < 0 or b < 0:
        return False
    dx = a % N - b % N
    dy = a // N - b // N
    if dx < 0: dx = -dx
    if dy < 0: dy = -dy
    return (dx == 1 and dy == 2) or (dx == 2 and dy == 1)


def w_pawn_att(pa, t, N):
    """Does a WHITE pawn on pa attack square t (diagonal forward +y)?"""
    if pa < 0 or t < 0:
        return False
    px, py = pa % N, pa // N
    ty = t // N
    return ty == py + 1 and (t % N == px - 1 or t % N == px + 1)


def b_pawn_att(pa, t, N):
    """Does a BLACK pawn on pa attack square t (diagonal forward -y)?"""
    if pa < 0 or t < 0:
        return False
    px, py = pa % N, pa // N
    ty = t // N
    return ty == py - 1 and (t % N == px - 1 or t % N == px + 1)


def k_atk_count(q, N):
    """Number of on-board squares attacked by a knight on q (0 if absent)."""
    if q < 0:
        return 0
    x, y = q % N, q // N
    n = 0
    for dx in (-2, -1, 1, 2):
        for dy in (-2, -1, 1, 2):
            if abs(dx) + abs(dy) != 3:
                continue
            nx, ny = x + dx, y + dy
            if 0 <= nx < N and 0 <= ny < N:
                n += 1
    return n


def king_feats(wk, bk, stm, N):
    """5 mover-neutral king-geometry features (semantically shared with the K2P
    basis: d_AK/opp are the repo's; e_w/e_b generalise e_A/e_D per side)."""
    d_AK = cheb(wk, bk, N)
    opp = int(d_AK == 2 and (wk % N == bk % N or wk // N == bk // N))
    e_w = min(wk % N, (N - 1) - wk % N)
    e_b = min(bk % N, (N - 1) - bk % N)
    return (stm, d_AK, opp, e_w, e_b)


def knight_feats(wk, bk, wp, bp, nw, nb, N):
    """The 13 PART-1 knight features. Absent knights -> constants
    (nW=nB=0, k_dist/k_*_own/k_*_enemy=ABSENT, katt/kchk=0, k_atk=0), so the
    extended basis reduces to the K2P basis at 0 knights."""
    nW = 1 if nw >= 0 else 0
    nB = 1 if nb >= 0 else 0
    if nw >= 0 and nb >= 0:
        k_dist = cheb(nw, nb, N)
    else:
        k_dist = ABSENT
    katt_w = int(nw >= 0 and (cheb(nw, bk, N) == 1            # black king
                              or knight_att(nb, nw, N)        # black knight
                              or b_pawn_att(bp, nw, N)))      # black pawn
    katt_b = int(nb >= 0 and (cheb(nb, wk, N) == 1
                              or knight_att(nw, nb, N)
                              or w_pawn_att(wp, nb, N)))
    kchk_w = int(nw >= 0 and knight_att(nw, bk, N))
    kchk_b = int(nb >= 0 and knight_att(nb, wk, N))
    k_w_own = cheb(nw, wk, N)
    k_b_own = cheb(nb, bk, N)
    k_w_enemy = cheb(nw, bk, N)
    k_b_enemy = cheb(nb, wk, N)
    k_atk_w = k_atk_count(nw, N)
    k_atk_b = k_atk_count(nb, N)
    return (nW, nB, k_dist, katt_w, katt_b, kchk_w, kchk_b,
            k_w_own, k_b_own, k_w_enemy, k_b_enemy, k_atk_w, k_atk_b)


def pawn_feats(wk, bk, wp, bp, nw, nb, N):
    """14 pawn-geometry features (sentinels when a side has no pawn)."""
    has_w = wp >= 0
    has_b = bp >= 0
    p_t_w = (N - 1) - (wp // N) if has_w else ABSENT
    p_t_b = (bp // N) if has_b else ABSENT
    p_e_w = min(wp % N, (N - 1) - wp % N) if has_w else ABSENT
    p_e_b = min(bp % N, (N - 1) - bp % N) if has_b else ABSENT
    p_chk_w = int(has_w and w_pawn_att(wp, bk, N))
    p_chk_b = int(has_b and b_pawn_att(bp, wk, N))

    def fwd_blocked(p, up):
        # 1 = pawn's push target is occupied by any piece (push impossible);
        # 0 = target empty or the pawn promotes with its next push.
        if p < 0:
            return 0
        ny = (p // N) + (1 if up else -1)
        if ny < 0 or ny > N - 1:
            return 0                      # next push = terminal promotion
        t = N * ny + (p % N)
        return int(t == wk or t == bk or t == wp or t == bp or t == nw or t == nb)

    p_fwd_w = fwd_blocked(wp, True)
    p_fwd_b = fwd_blocked(bp, False)
    p_kdef_w = int(has_w and cheb(wk, wp, N) == 1)
    p_kdef_b = int(has_b and cheb(bk, bp, N) == 1)
    p_ndef_w = int(has_w and nw >= 0 and knight_att(nw, wp, N))
    p_ndef_b = int(has_b and nb >= 0 and knight_att(nb, bp, N))
    p_ncap_w = int(nw >= 0 and has_b and knight_att(nw, bp, N))
    p_ncap_b = int(nb >= 0 and has_w and knight_att(nb, wp, N))
    return (p_t_w, p_t_b, p_e_w, p_e_b, p_chk_w, p_chk_b,
            p_fwd_w, p_fwd_b, p_kdef_w, p_kdef_b,
            p_ndef_w, p_ndef_b, p_ncap_w, p_ncap_b)


# ---- v2 basis API (see module header; NOT used by the committed compression
# runs - those call the v1 class_features above) ------------------------------
def king_feats_v2(wk, bk, stm, N):
    """king_feats (v1, 5) + rank-edge distances re_w/re_b = min(y, N-1-y)."""
    return king_feats(wk, bk, stm, N) + \
        (min(wk // N, (N - 1) - wk // N), min(bk // N, (N - 1) - bk // N))


def _signed_delta(piece, king, N):
    """Signed per-axis (king - piece); (-1, -1) when the piece is absent."""
    if piece < 0:
        return (-1, -1)
    return (king % N - piece % N, king // N - piece // N)


def knight_signed_feats(wk, bk, nw, nb, N):
    """The 8 v2 signed knight offsets, order = KNIGHT_SIGNED_NAMES."""
    dx, dy = _signed_delta(nw, wk, N)
    f = [dx, dy]
    dx, dy = _signed_delta(nb, bk, N)
    f += [dx, dy]
    dx, dy = _signed_delta(nw, bk, N)
    f += [dx, dy]
    dx, dy = _signed_delta(nb, wk, N)
    f += [dx, dy]
    return tuple(f)


def pawn_signed_feats(wk, bk, wp, bp, N):
    """The 8 v2 signed pawn offsets, order = PAWN_SIGNED_NAMES."""
    dx, dy = _signed_delta(wp, wk, N)
    f = [dx, dy]
    dx, dy = _signed_delta(bp, bk, N)
    f += [dx, dy]
    dx, dy = _signed_delta(wp, bk, N)
    f += [dx, dy]
    dx, dy = _signed_delta(bp, wk, N)
    f += [dx, dy]
    return tuple(f)


def class_semantic_names_v2(mat):
    """Feature-name list for a class under the v2 basis (order =
    class_features_v2): king block + rank-edge, knight block + signed offsets,
    pawn block + signed offsets (pawn block only when the class can hold pawns)."""
    wp, bp, wn, bn = mat
    names = list(KING_NAMES) + list(KING_V2_NAMES) + list(KNIGHT_NAMES) + \
        list(KNIGHT_SIGNED_NAMES)
    if wp or bp:
        names += list(PAWN_NAMES) + list(PAWN_SIGNED_NAMES)
    return names


def class_features_v2(wk, bk, wp, bp, nw, nb, stm, N, mat):
    """Full v2 semantic feature tuple for a class state (order =
    class_semantic_names_v2)."""
    wp_, bp_, wn_, bn_ = mat
    out = list(king_feats_v2(wk, bk, stm, N)) + \
        list(knight_feats(wk, bk, wp, bp, nw, nb, N)) + \
        list(knight_signed_feats(wk, bk, nw, nb, N))
    if wp_ or bp_:
        out += list(pawn_feats(wk, bk, wp, bp, nw, nb, N)) + \
            list(pawn_signed_feats(wk, bk, wp, bp, N))
    return tuple(out)


def material_key(wp, bp, nw, nb):
    """(white pawn count, black pawn count, white knight count, black knight count)."""
    return (1 if wp >= 0 else 0, 1 if bp >= 0 else 0,
            1 if nw >= 0 else 0, 1 if nb >= 0 else 0)


def class_semantic_names(mat):
    """Semantic feature-name list for a material class (king block always;
    knight block always per PART 1 - constants at 0 knights; pawn block only
    when the class can hold pawns)."""
    wp, bp, wn, bn = mat
    names = list(KING_NAMES) + list(KNIGHT_NAMES)
    if wp or bp:
        names += list(PAWN_NAMES)
    return names


def class_features(wk, bk, wp, bp, nw, nb, stm, N, mat):
    """Full semantic feature tuple for a class state (order = class_semantic_names)."""
    wp_, bp_, wn_, bn_ = mat
    out = list(king_feats(wk, bk, stm, N)) + list(knight_feats(wk, bk, wp, bp, nw, nb, N))
    if wp_ or bp_:
        out += list(pawn_feats(wk, bk, wp, bp, nw, nb, N))
    return tuple(out)


# ---------------------------------------------------------------- orbit machinery
def H_q(q, N):  return (q // N) * N + (N - 1 - q % N) if q >= 0 else -1
def V_q(q, N):  return (q % N) + N * (N - 1 - q // N) if q >= 0 else -1


def enc8(wk, bk, wp, bp, nw, nb, stm, N):
    """Total-order encoding of the 7-coordinate state (absent -1 sorts first).
    Every piece slot carries +1 for the absent sentinel, so pawn AND knight
    slots both need radix R = NN+1 (a knight can occupy every NN squares, so
    (nw+1) spans [0, NN] - radix NN would collide 'knight on last square' with
    'next digit 0')."""
    NN = N * N
    R = NN + 1
    return (((((((wk * NN + bk) * R + (wp + 1)) * R + (bp + 1)) * R + (nw + 1)) * R
              + (nb + 1)) * 2 + stm))


def dec8(c, N):
    NN = N * N
    R = NN + 1
    t = c
    stm = t % 2; t //= 2
    nb = t % R - 1; t //= R
    nw = t % R - 1; t //= R
    bp = t % R - 1; t //= R
    wp = t % R - 1; t //= R
    bk = t % NN; t //= NN
    return (t, bk, wp, bp, nw, nb, stm)


def t_H8(st, N):
    wk, bk, wp, bp, nw, nb, stm = st
    return (H_q(wk, N), H_q(bk, N), H_q(wp, N), H_q(bp, N), H_q(nw, N), H_q(nb, N), stm)


def t_V8(st, N):
    """Colour-swap mirror: W<->B, rank reflection, stm flip."""
    wk, bk, wp, bp, nw, nb, stm = st
    return (V_q(bk, N), V_q(wk, N), V_q(bp, N), V_q(wp, N), V_q(nb, N), V_q(nw, N), 1 - stm)


def canon8(st, N):
    """Canonical orbit representative: min encoding over {id, H, V', H V'}."""
    m1 = t_H8(st, N)
    m2 = t_V8(st, N)
    m3 = t_H8(m2, N)
    c = enc8(*st, N)
    for m in (m1, m2, m3):
        e = enc8(*m, N)
        if e < c:
            c = e
    return dec8(c, N)


def orbit_members(st, N):
    m1 = t_H8(st, N)
    m2 = t_V8(st, N)
    m3 = t_H8(m2, N)
    return (st, m1, m2, m3)


def mv_from_val(val_arr):
    """VAL{1=win,2=loss,3=draw} -> MV{0=draw,1=win,2=loss} (-1 illegal), repo convention."""
    import numpy as np
    v = np.asarray(val_arr)
    mv = np.where(v == 3, 0, np.where(v >= 1, v, -1)).astype(np.int8)
    return mv
