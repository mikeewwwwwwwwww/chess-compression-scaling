# HONESTY.md — what this repository does NOT prove

This file is the negative-space record. Everything here is a statement of
what was **not** done, **not** shown, or **not** claimable, so that no
reader has to infer the boundaries from silence. The positive-space
traceability is [FACTS.md](FACTS.md).

## 1. Measured vs extrapolated

- Every number in the papers and README resolves to an artifact JSON and a
  key path (FACTS.md, 88 rows). Claims are tagged MEASURED, EXTRAPOLATED,
  OPEN, or LOST. There are 80 MEASURED rows (including arithmetic derived
  from measured inputs with the formula stated), 2 EXTRAPOLATED, 2 LOST,
  and 4 OPEN.
- The only EXTRAPOLATED headline-adjacent numbers are: the full K2P+N 4x4
  ratio (~1:20-1:25, from the pawn-bearing class band 1:8.7-1:22.2) and the
  N=6 depth prediction (29-31 plies). Neither is measured. The 17M-state,
  ~6 GB full K2P+N build was deliberately **not** run; running it would be
  a paper decision (one measured row), not a science one — the class data
  already establish the finding.
- The node growth exponent (0.775 pooled OLS) is a fit over ten measured
  builds on the range N=3..5. It is a regularity of that range, not a law
  beyond it.

## 2. The routed/unified distinction (learned the hard way)

The board-size improvement must be quoted routed-to-routed (1:31.7 ->
1:79.7). The N=5 unified build (1:86.1) also benefits from unification
itself (7.5% node saving over the routed N=5 total), and no unified N=4
build exists. An earlier draft of the underlying charter quoted "nodes
4,885 -> 78,305" across methodologies; that comparison is invalid and is
corrected here and in Paper 1 Sec. 2.3.

## 3. The architectural correction

The frozen K2P repo's README presents "93.84% atlas + 6.16% MTBDD residual"
as the architecture. That is a phase-6c snapshot. The atlas reached exact
closure at phase 7b (residual = 0 over all 154,888 states). The MTBDD is a
parallel zero-lookup compilation of the same closed value function, not a
residual handler. Additionally: "zero-lookup, no search" is true of the
evaluation path only — the construction path is enumeration + retrograde
search. See supplementary/architectural_correction.md.

## 4. Speed is not the contribution

The emitted evaluator is SLOWER than a dictionary lookup: 4.73 vs 3.05
us/state (four_pawn family, routed; CPython 3.12, best-of-passes; frozen
repo benchmark). Routed full-space latency is 4.45 us/state. We accept the
cost because the goal is verifiability: a pure-integer evaluator whose every
branch can be audited against the oracle, with zero mismatches on every
run. Nothing in this repository should be read as a speed claim.

## 5. Z3 proves adequacy, nothing else

- Z3 certifies **value-sufficiency of the feature basis** — a soundness
  precondition for tail-free compilation. It does NOT prove the basis
  minimal (the minimality ladder is measured, not proved), does NOT bound
  or predict compression ratios, and does NOT transfer across material
  classes.
- Proof tiers are per class and budget-bounded: 1 full-class unsat (kn
  N=3), 5 bounded-subspace unsat (4.7-14.8% of each class, capped by a
  60,000-state array axiomatisation budget), 1 empirical-only (both N=4,
  1.36M states). The tier system exists precisely so that a budget
  artifact cannot masquerade as a theorem.
- The legality predicate and the feature encoding are hand-written
  re-implementations, guarded by 500-state exact self-tests per class and
  by the protocol's SAT-unexpected alarm — not by an independent proof.
- Compression has NOT been re-run under the v2 basis; the published class
  compression numbers were built with the v1 basis + conditional
  coordinate tail (and are exact: 0 mismatches). That "v2 enables tail-free
  compilation" is a supported expectation is stated as such in Paper 2.

## 6. Lost artifacts (reported, not reconstructed)

A sandbox outage destroyed part of the underlying project's diagnostics
directory. In this repository:

- **E5 phase-level timing split** (canonicalisation / feature-extraction /
  walk percentages): LOST. Only solver wall times, peak RSS, and trace-mode
  walls survive. The percentages are not quoted anywhere in this repo.
- **Tuning result tables (Tracks A-D)**: LOST
  (tuning_summary.json confirmed absent by recursive search; see the
  underlying HANDOFF.md Sec. 4.3). The charter's qualitative conclusions
  survive (baseline "names" variable ordering wins on nodes; unified
  emission saves ~7.5% nodes; memoization is slower than lazy inlining)
  and are cited as such in FACTS.md (tier: MEASURED (conclusions; tables
  lost)). The specific numbers that appear in some tasking notes
  (652 -> 605 feature elimination; "baseline 4,885 best") have **no
  surviving artifact** and are marked OPEN/unverifiable, not used.
- E2 and the N=5 half of E4 were re-run from the durable oracle arrays
  after the outage; their provenance is inside the files
  (artifacts/e_diagnostics/*.json).

## 7. Knight-only classes are not a success story

K+N vs K+N compresses at 1:595-1:2,814 — but those classes are
draw-saturated with max DTC = 1 (every decided state converts immediately).
The high ratios reflect a trivially simple value structure. The papers
exclude them from degradation claims rather than presenting them as
compression successes.

## 8. Balance law: measured instance, not theorem

Two independent AI analyses (Z.ai GLM; Google Gemini; non-peer-reviewed,
transcripts not archived — see supplementary/ai_analyses.md) arrive at a
qualitative "complexity concentrates at balance" claim from different
starting points. Our class-by-class data are consistent with it
(unbalanced classes degrade 3.35x-4.17x vs 1.57x balanced). We do NOT
claim a balance law as a theorem, do NOT claim novelty for it, and do NOT
claim generalization beyond this fragment family. The reframe
(piece-count -> material balance as the operative variable) is a
measurement-supported revision, documented as a revision.

## 9. No claims about the full game

Nothing here claims progress toward solving chess. The 8x8 initial
position sits at the material-balance extreme, where this architecture is
expected to fare worst, and no measurement contradicts the classical
exponential bounds (Fraenkel-Lichtenstein 1983). N=6 is out of scope by
charter (oracle scale ~2.9e8 states). K2P+R (sliding piece) is proposed as
future work, not run.

## 10. Not formal verification

The retrograde recursion, the legality predicate, and the compressor are
empirically validated (self-tests, independent-enumeration cross-check,
exhaustive emitted-evaluator verification, byte-identical N=4
reproduction), not formally verified. A Lean formalization is future work
(Paper 2, Sec. 7.3).

## 11. Authorship and provenance

All authorship, commit authorship, and citation fields in this repository
are attributed to the repository owner (mikeewwwwwwwwww). The two AI
analyses referenced in Sec. 8 are attributed as tool-generated,
non-peer-reviewed context, kept out of the author lists by design.
scripts/build_facts.py generates FACTS.md from artifacts/ so the
traceability table cannot drift from the data.
