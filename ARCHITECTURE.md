# ARCHITECTURE.md

This repository studies one architecture end-to-end: an exact retrograde
oracle for a family of N x N chess fragments, a semantic MTBDD compiler
that turns the oracle's value function into a zero-lookup evaluator, and a
Z3 certification layer that proves the compiler's silent assumption (that
the feature basis is value-sufficient) before results are trusted.

```
                            CONSTRUCTION PATH (uses enumeration/search)
  +-----------------------------------------------------------------------------------+
  | ORACLE (experiments/oracle/, experiments/class/)                                  |
  |   enumerate king pairs x piece configs x pawn configs on NxN                      |
  |   -> legality filter -> directed game graph                                       |
  |   -> retrograde fixpoint (VAL: 1 mover-wins / 2 mover-loses / 3 draw)             |
  |   -> DTC sweeps (plies to conversion)                                             |
  |   -> self-tests: mirror symmetry, anti-symmetry, K-vs-K, cross-checks             |
  |   N=3: 1,032 states / 0.2s    N=4: 154,888 / 2.0s    N=5: 6,744,724 / 110.5s      |
  +------------------------------------+----------------------------------------------+
                                       | phase1_values.npz (VAL, DTC, ...)
                                       v
  +-----------------------------------------------------------------------------------+
  | COMPILER (experiments/compressor/, experiments/class/)                            |
  |   orbit quotient (colour-swap x board reflection)  -> canonical rows              |
  |   semantic feature extraction per orbit (tau, distances, alignments,              |
  |     attacks/checks, material counts; K2P+N adds knight/pawn offsets)              |
  |   ordered MTBDD over features (+ conditional 6-coordinate tail                    |
  |     only on rows the features cannot separate)                                    |
  |   EMISSION: pure-integer if/else evaluator, no arrays/dicts on the                |
  |     evaluation path                                                               |
  |   VERIFY: evaluate every legal state against the oracle (exhaustive)              |
  +------------------------------------+----------------------------------------------+
                                       | compression_results.json
                                       v
  +-----------------------------------------------------------------------------------+
  | CERTIFICATION (experiments/z3/)                                                   |
  |   Z3 query: exists s1,s2 legal with phi(s1)=phi(s2) and VAL differs               |
  |   empirical layer (Python bucketing) -> symbolic refutation (certified pairs)     |
  |     -> full-class unsat | bounded-subspace unsat | empirical-only                 |
  |   mirror proof: phi commutes with colour-swap V' (VAL-free)                       |
  |   minimality ladder: which feature subsets close which classes                    |
  +-----------------------------------------------------------------------------------+

                            EVALUATION PATH (no lookups, no search)
  emitted evaluator: pure-integer branching program over the feature basis
  (slower than a dict: 4.73 vs 3.05 us/state on four_pawn routed — verifiability
   is the goal, not speed)
```

## Key facts the diagram encodes

1. **Construction vs evaluation.** The construction path enumerates states
   and runs retrograde search; the evaluation path does no lookups at all.
   The original repo's "zero-lookup, no search" slogan is true only of the
   second path, and this diagram separates them explicitly.
2. **Atlas closure.** In the frozen K2P artifact the analytic atlas reached
   exact closure at phase 7b (residual = 0 over 154,888 states). The MTBDD
   is a parallel compilation of the same closed value function — not a
   residual handler for an incomplete atlas. See
   supplementary/architectural_correction.md.
3. **Two build modes.** *Routed* = one MTBDD per material family, routed by
   family (N=4: duel 652 + asym_3p 2,050 + four_pawn 2,183 = 4,885 nodes).
   *Unified* = a single MTBDD over all families (N=5: 78,305 nodes, 7.5%
   fewer than the routed N=5 total of 84,618). Cross-methodology ratio
   comparisons (routed N=4 vs unified N=5) are invalid and never made in
   this repository's papers.
4. **The tail.** Where semantic features cannot separate value classes, the
   compiler appends six canonical coordinates conditionally. This restores
   exactness at node cost. On the seven K2P+N classes (v1 basis) the tail
   discharged every conflict exactly (0 mismatches after emit+verify); the
   Z3 v2 basis would make these classes tail-free, but compression has not
   been re-run under v2 (Paper 2, Sec. 5.3).
5. **Verification is exhaustive, not sampled.** Every published build ends
   with an emitted-evaluator verification over all legal states of its
   scope (at N=5: all 6,744,724 states, 0 mismatches).
6. **Trust gates.** The N=4 generalized build is byte-identical to the
   frozen artifact's emitted evaluators (one provenance header line
   difference each), and the N=5 state count was predicted independently by
   a standalone enumeration program (Track B: 6,744,724) before the solver
   ran. The self-contained CI gate re-runs the smallest class end-to-end
   and asserts the published values.

## Scaling findings (summary)

- **Board size (N=3 -> 5):** states x150 / x43.5; routed nodes 4,885 ->
  84,618; ratios 1:31.7 -> 1:79.7 routed, 1:86.1 unified at N=5;
  per-family routed depth 15->16, 19->22, 21->24 (unified N=5 build: 26);
  nodes ~ states^0.775 (pooled log-log OLS). Mechanisms: E3
  (path depth = distinct-feature count; features activate slowly), E6
  (used features 80-90% translation-invariant, rising with N).
- **Material balance (K2P+N, N=4):** balanced material +1 knight/side:
  1:29.1 -> 1:18.6 (1.57x worse). Unbalanced: 1:36.3 -> 1:10.8 (3.35x),
  mirror class 1:8.7 (4.17x). The architecture amortises symmetric
  structure; balance injects asymmetric structure it cannot amortise.
