# The balance-law connection

## Status: measured instance, not theorem

This note connects the repository's measured class-by-class degradation to
an independently asserted qualitative claim — "complexity concentrates at
material balance" — that originated outside this project. The claim is
ATTRIBUTED and NON-PEER-REVIEWED (see ai_analyses.md); what is measured is
one instance of the pattern it predicts. This repository does not claim,
and cannot claim, a balance law as a theorem.

## What was measured (MEASURED, artifacts/class_compression/)

At fixed board size N=4, with the identical compilation pipeline:

| material | balanced? | pieces/side | ratio | vs K2P baseline |
|---|---|---|---|---|
| K+2P vs K+2P (four_pawn) | yes | 3 | 1:29.1 | baseline |
| K+P+N vs K+P+N | yes | 3 | 1:18.6 | 1.57x worse |
| K+2P vs K+P (asym_3p) | no | 2-3 | 1:36.3 | baseline |
| K+P+N vs K | no | 3 vs 1 | 1:10.8 | 3.35x worse |
| K+P vs K+P+N | no | 2 vs 3 | 1:8.7 | 4.17x worse |

Reading: (i) adding a knight per side at fixed balance costs 1.57x — real
but modest; (ii) at comparable piece counts, imbalance costs 3.35x-4.17x;
(iii) depth grows most in the unbalanced classes (24-28 vs 21), i.e. more
distinct features are in play, not just more states. The original
interpretation of the degradation ("piece count hurts") was revised to
"material balance is the operative variable" AFTER these measurements; the
revision is documented in Paper 1 Sec. 5.4 as a revision, with the earlier
reading quoted.

## Why this is consistent with a "balance law"

The independently asserted claim is qualitative: as material approaches
balance, the structural complexity of the value function (here: MTBDD size
per state, distinct-feature count, conflicting semantic groups) grows
disproportionately. The mechanism this repository can actually see is:

- the orbit quotient amortises *symmetric* structure (colour swap, board
  reflection); balanced material is exactly the case where the two sides'
  kings play exchangeable roles, so the quotient merges most;
- imbalance assigns the kings qualitatively different roles (attacker vs
  defender), which splits role-dependent features and multiplies distinct
  feature vectors faster than the quotient can merge — visible directly in
  the per-class conflicting-group counts (e.g. K+P+N vs K: 477 at N=4) and
  in depth growth;
- board size, by contrast, feeds the quotient exponentially more states
  sharing the same relative geometry — hence the opposite sign on that
  axis.

Nothing here proves that this pattern persists at higher material
complexity; K2P+R (sliding piece) is proposed as the next stress test, not
run. And the 8x8 initial position sits at the balance extreme — the
pattern, if it generalises, is a caution for compression approaches at
full-chess scale, not an obstacle measured there.

## What would count as more evidence

1. more material axes at N=4 (K+2N vs K, K+R vs K, K+B vs K) to separate
   "knight" from "imbalance";
2. the full K2P+N 4x4 build (17M states) to replace the extrapolated
   full-space ratio with a measured row;
3. the same class protocol at N=5 for the balanced class (only kpn was run
   at N=5);
4. an independent replication of the class protocol by a second
   implementation.

None of these are done. The honest current statement is: one fragment
family, seven classes, exact values, one measured instance of a pattern
that independent (non-peer-reviewed) analyses predicted qualitatively.
