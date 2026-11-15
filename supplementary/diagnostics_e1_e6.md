# Diagnostics E1-E6 (mechanism experiments)

Consolidated record: `artifacts/diagnostics_summary.json`; raw re-runs:
`artifacts/e_diagnostics/*.json`. Provenance caveat that applies to the
whole set: a sandbox outage destroyed part of the original diagnostics
directory; items re-run from durable oracle arrays on 2026-11-15 are marked
RE-RUN, items re-grounded in durable repo artifacts are marked RE-GROUNDED,
and items with no surviving artifact are marked LOST. Nothing was invented
to fill gaps.

## E1 — core check / architectural correction (RE-GROUNDED)

The pre-outage CORE sequence-array claim was falsified; the durable
correction is that the atlas reaches full closure at phase 7b:
`phase7b_results.json` has `residual = 0`, `residual_core = 0`,
`residual_leftover = 0`, `psi_v7b_global = 154,888` at accuracy `1.0`
(151,042-state v7a baseline + 3,846 repaired). The README's 93.84%
(145,354 states) was a phase-6c snapshot. See
supplementary/architectural_correction.md.

## E2 — contact vs race share (RE-RUN 2026-11-15)

Share of legal states that are non-contact race (A) vs contact (B), per
family. From `e2_contact_race.json` (recomputed from the durable oracle
arrays; the original artifact was lost):

| family | N=4 A% | N=4 B% | N=5 A% | N=5 B% |
|---|---|---|---|---|
| duel | 15.70 | 88.98 | (see file) | (see file) |
| asym_3p | 2.78 | 99.63 | 11.42 | (see file) |
| four_pawn | 0.34 | 100.0 | (see file) | (see file) |
| all | 3.19 | 98.62 | (see file) | (see file) |

(Exact N=5 values for every family are in the JSON; the asym_3p race share
rises 2.78% -> 11.42%, +8.64 pp, from N=4 to N=5.) The original causal
hypothesis — that growing non-contact race share drives compression —
remains UNVERIFIED: the re-run supplies shares, not causes. Reported as an
honest open gap in the papers.

## E3 — deepest-path traces: depth = distinct features (REGENERATED N=4, MEASURED N=5)

On an ordered MTBDD, each feature can be tested at most once per
root-to-leaf path, so the deepest path's length equals its distinct-feature
count — a structural property, not an empirical accident. All seven traces
(4/duel, 4/asym_3p, 4/four_pawn, 5/duel, 5/asym_3p, 5/four_pawn, 5/full)
confirm depth = n_distinct_features with zero repeated features:

| trace | depth | distinct features |
|---|---|---|
| 4/duel | 15 | 15 |
| 4/asym_3p | 19 | 19 |
| 4/four_pawn | 21 | 21 |
| 5/duel | 16 | 16 |
| 5/asym_3p | 22 | 22 |
| 5/four_pawn | 24 | 24 |
| 5/full | 26 | 26 |

The N=4 traces were regenerated after the outage and byte-match the v1
stats in compression_summary.json (nodes/paths/depth). E3 also carries the
N=6 depth prediction (EXTRAPOLATED): duel 16-17, asym_3p 24-25, four_pawn
26-27, full 29-31 (point estimate 30), under the assumption that 3-5
never-yet-essential features activate at N=6 (the mechanism that activated
dy_p / d_ApR / nW / nB at N=5).

## E4 — mutual zugzwang signature (RE-RUN 2026-11-15)

MZZ = placements where the mover loses with either tempo. Counts: 8
placements (16 states) at N=4, 168 placements (336 states) at N=5 —
matching the pre-outage expectation exactly, and cross-checked at N=4
against `phase7b_results.json mutual_zugzwang_exact = 16`. Mechanism
distribution: N=4 — pure_blockade_wall 8/8 (100%); N=5 — pure_blockade_wall
154 (91.67%), adjacency_gridlock 12 (7.14%), push_blocked_only 2 (1.19%).
Counterexamples (neither push-blocked nor king-pawn adjacent): NONE at
either N — every MZZ placement is a blocked-contact structure. A compact
semantic handle that survives scaling.

## E5 — timing (partially LOST)

The pre-outage e5_timing.json was destroyed; the phase-level split
(canonicalisation / feature-extraction / walk percentages) was never
re-run and is NOT available anywhere in this archive. Surviving core
evidence: solver walls 0.2 / 2.0 / 110.5 s (N=3/4/5, incl. startup), peak
RSS 36.4 / 87.5 / 2,370.9 MiB, N=5 trace-mode walls 4.2 / 51.0 / 123.5 /
163.8 s (duel/asym_3p/four_pawn/full). The split percentages are quoted
nowhere in this repository.

## E6 — translation invariance of used features (MEASURED)

Method: features extracted via AST from the compressor and executed per N;
40k random canonical states per family per N; file-shift (+1) and
rank-shift (+1) probes on square positions (tau excluded) plus a
single-square move probe to detect non-spatial features. Survivor-level
translation-invariant share of used features:

| family | N=4 | N=5 |
|---|---|---|
| duel | 81.0% | 90.0% |
| asym_3p | 80.0% | 82.4% |
| four_pawn | 84.4% | 87.5% |
| full space | — | 82.4% |

The only absolute-coordinate survivors are edge-folded file metrics
(e_R/e_A/e_D at N=4; e_R/e_A at N=5) — no raw absolute square appears in
the semantic basis. Compression improves with N partly because the
effective feature space is translation-invariant, and increasingly so.
