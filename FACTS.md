# FACTS.md - claim-to-artifact traceability table

Every numeric claim made anywhere in this repository (papers, README,
supplementary notes) must appear in this table with the exact artifact file
and key path it comes from. Values in the **Value** column were extracted
programmatically from the artifacts by `scripts/build_facts.py` in the
authoring sandbox (2026-11-15); they are not hand-typed. Derived quantities
(ratios, sums, degradation factors, the growth exponent) are computed from
measured inputs with the formula named in the **Key path** column.

Evidence tiers:
- **MEASURED** - backed by an artifact file + key path (or by arithmetic on
  such values, with the formula given).
- **MEASURED (fitted)** - a fit over measured points; the fit method is stated.
- **MEASURED (re-run)** - original artifact lost in a sandbox outage,
  recomputed from durable oracle arrays on 2026-11-15 (provenance in the file).
- **MEASURED (conclusions; tables lost)** - qualitative conclusion recorded in
  the committed charter before the outage; underlying result tables lost.
- **EXTRAPOLATED** - backed by a trend over measured points, with the
  extrapolation stated as such; never presented as measured.
- **OPEN** - no evidence either way (not run / not attempted).
- **LOST** - artifact existed before a sandbox outage and is confirmed absent;
  the claim is NOT available in this archive.

| # | Claim | Value | Source file | Key path | Evidence tier |
|---|-------|-------|-------------|----------|---------------|
| F1 | N=3 legal states | 1,032 | artifacts/scaling_summary.json | 3.legal_states | MEASURED |
| F2 | N=4 legal states | 154,888 | artifacts/scaling_summary.json | 4.legal_states | MEASURED |
| F3 | N=5 legal states | 6,744,724 | artifacts/scaling_summary.json | 5.legal_states | MEASURED |
| F4 | Directed edges N=3/4/5 | 1,332 / 531,456 / 32,551,012 | artifacts/scaling_summary.json | 3|4|5.directed_edges | MEASURED |
| F5 | Oracle solver runtime N=3/4/5 (s) | 0.0 / 1.8 / 110.2 | artifacts/scaling_summary.json | 3|4|5.solver_runtime_s | MEASURED |
| F6 | Oracle wall time incl. startup N=3/4/5 (s) | 0.2 / 2.0 / 110.5 | artifacts/scaling_summary.json | 3|4|5.wall_s_incl_startup | MEASURED |
| F7 | Oracle peak RSS N=3/4/5 (MiB) | 36.4 / 87.5 / 2370.9 | artifacts/scaling_summary.json | 3|4|5.peak_rss_mib | MEASURED |
| F8 | Max DTC over decided states N=3/4/5 (plies) | 4 / 13 / 38 | artifacts/scaling_summary.json | 3|4|5.dtc_decided_max | MEASURED |
| F9 | Draw percentage N=3/4/5 | 28.1008 / 6.9237 / 4.9776 | artifacts/scaling_summary.json | 3|4|5.pct_draws | MEASURED |
| F10 | DTC sweeps N=3/4/5 | 4 / 13 / 38 | artifacts/scaling_summary.json | 3|4|5.dtc_sweeps | MEASURED |
| F11 | N=4 oracle validated against frozen K2P artifacts (VAL/DTC/MIR/STMW/MAT diffs) | 0 | artifacts/scaling_summary.json | meta.n4_validation | MEASURED |
| F12 | Track B independent enumeration predicted N=5 legal states | 6,744,724 | artifacts/scaling_summary.json | meta.n5_prediction_check | MEASURED |
| F13 | N=5 qualitative verdict vs N=4 (draw% 4.98 vs 6.92, decided 95.02%) | QUALITATIVELY SIMILAR (draw% 4.98 vs 6.92, decided 95.02%) | artifacts/scaling_summary.json | qualitative_assessment.n5_vs_n4 | MEASURED |
| F14 | State growth N=5/N=4 and N=4/N=3 | 43.5458 / 150.0853 | artifacts/scaling_summary.json | ratios_vs_n4.n5_over_n4_states|n4_over_n3_states | MEASURED |
| F15 | Edge growth N=5/N=4 and N=4/N=3 | 61.2487 / 398.991 | artifacts/scaling_summary.json | ratios_vs_n4.n5_over_n4_edges|n4_over_n3_edges | MEASURED |
| F16 | Runtime growth N=5/N=4 | 61.22 | artifacts/scaling_summary.json | ratios_vs_n4.n5_over_n4_runtime | MEASURED |
| F17 | Mutual-zugzwang placements N=3/4/5 (mover loses with either tempo) | 0 / 8 / 168 | artifacts/oracle_runs/out_n{3,4,5}/phase1_results.txt | TEMPO STRUCTURE block, 'mutual zugzwang placements' | MEASURED |
| C1 | N=4 duel: states / MTBDD nodes / depth / ratio (states per node) | 16,920 / 652 / 15 / 26.0 | artifacts/compression_summary.json | runs.n4_all.per_family.duel | MEASURED |
| C2 | N=4 asym_3p: states / nodes / depth / ratio | 74,340 / 2,050 / 19 / 36.3 | artifacts/compression_summary.json | runs.n4_all.per_family.asym_3p | MEASURED |
| C3 | N=4 four_pawn: states / nodes / depth / ratio | 63,628 / 2,183 / 21 / 29.1 | artifacts/compression_summary.json | runs.n4_all.per_family.four_pawn | MEASURED |
| C4 | N=4 routed total MTBDD nodes (three per-family MTBDDs) | 4,885 | artifacts/compression_summary.json | runs.n4_all.router_total_nodes | MEASURED |
| C5 | N=4 routed compression ratio (154,888 states / 4,885 nodes) | 1:31.7 | artifacts/compression_summary.json + arithmetic | runs.n4_all.router_total_nodes; scaling_summary.json 4.legal_states | MEASURED |
| C6 | N=5 duel: states / nodes / depth / ratio | 177,640 / 3,917 / 16 / 45.4 | artifacts/compression_summary.json | runs.n5_duel.result | MEASURED |
| C7 | N=5 asym_3p: states / nodes / depth / ratio | 1,909,806 / 23,034 / 22 / 82.9 | artifacts/compression_summary.json | runs.n5_asym_3p.result | MEASURED |
| C8 | N=5 four_pawn: states / nodes / depth / ratio | 4,657,278 / 57,667 / 24 / 80.8 | artifacts/compression_summary.json | runs.n5_four_pawn.result | MEASURED |
| C9 | N=5 routed total nodes (sum of the three per-family MTBDDs) and routed ratio | 84,618 nodes; 1:79.7 | artifacts/compression_summary.json + arithmetic | runs.n5_{duel,asym_3p,four_pawn}.result.mtbdd.nodes summed | MEASURED |
| C10 | N=5 unified single MTBDD (full space): nodes / paths / depth | 78,305 / 275,358 / 26 | artifacts/compression_summary.json | runs.n5_full.result.mtbdd | MEASURED |
| C11 | N=5 unified compression ratio (6,744,724 states / 78,305 nodes) | 1:86.1 | artifacts/compression_summary.json + arithmetic | runs.n5_full.result.{states,mtbdd.nodes} | MEASURED |
| C12 | Like-for-like board-size comparison is routed-to-routed: 1:31.7 (N=4) -> 1:79.7 (N=5) | 2.51x better | arithmetic on C5/C9 | router totals both N | MEASURED |
| C13 | Unified vs routed at N=5: node saving | 7.5% | arithmetic on C9/C10 | 78,305 vs 84,618 | MEASURED |
| C14 | N=4 generalized build vs frozen repo reference | 1 provenance header line each | artifacts/compression_summary.json | comparison.n4_generalized.byte_diff_vs_repo_emitted | MEASURED |
| C15 | N=3 duel: states / nodes / depth / ratio | 604 / 59 / 10 / 10.2 | artifacts/compression_summary.json | runs.n3_duel.result | MEASURED |
| C16 | Node growth exponent: nodes ~ states^k, pooled ordinary least squares over 10 family/total builds (N=3/4/5) | k = 0.775 (log-log OLS; per-family two-point k: duel 0.763, four_pawn 0.763, asym_3p 0.745, routed 0.756) | derived from artifacts/compression_summary.json | log10(nodes) vs log10(states) over runs {n3_duel,n4_duel,n5_duel,n4_asym_3p,n5_asym_3p,n4_four_pawn,n5_four_pawn} + routed totals + n5_full | MEASURED (fitted) |
| C17 | Depth N=4 -> N=5 per family (duel/asym_3p/four_pawn/full) | 15->16, 19->22, 21->24, (full unified) 26 | artifacts/compression_summary.json | runs.*.result.mtbdd.max_depth | MEASURED |
| C18 | Family-level semantic conflicts on canonical rows at N=4 and N=5 | 0 semantic conflicts on canonical rows for duel, asym_3p, four_pawn AND the full space (distinct semantic rows == distinct full rows in every build); tail coordinates needed: 0 | artifacts/compression_summary.json | questions.q1_feature_conflicts.n5 | MEASURED |
| F20 | Class kn_n3 (K+N vs K+N, N=3): states / orbits / MTBDD nodes / depth / ratio / verify | 2,112 / 528 / 47 / 13 / 1:44.94 / PASS (2,112 checked, 0 mismatches) | artifacts/class_compression/kn_n3/compression_results.json | states|canonical_orbits|mtbdd|ratio_states_per_node|verification | MEASURED |
| F21 | Class kn_n4 (K+N vs K+N, N=4): states / orbits / MTBDD nodes / depth / ratio / verify | 46,384 / 11,596 / 78 / 17 / 1:594.67 / PASS (46,384 checked, 0 mismatches) | artifacts/class_compression/kn_n4/compression_results.json | states|canonical_orbits|mtbdd|ratio_states_per_node|verification | MEASURED |
| F22 | Class kn_n5 (K+N vs K+N, N=5): states / orbits / MTBDD nodes / depth / ratio / verify | 391,072 / 97,804 / 139 / 16 / 1:2813.47 / PASS (391,072 checked, 0 mismatches) | artifacts/class_compression/kn_n5/compression_results.json | states|canonical_orbits|mtbdd|ratio_states_per_node|verification | MEASURED |
| F23 | Class kpn_n4 (K+P+N vs K, N=4): states / orbits / MTBDD nodes / depth / ratio / verify | 25,178 / 12,589 / 2,324 / 18 / 1:10.83 / PASS (25,178 checked, 0 mismatches) | artifacts/class_compression/kpn_n4/compression_results.json | states|canonical_orbits|mtbdd|ratio_states_per_node|verification | MEASURED |
| F24 | Class kpn_n5 (K+P+N vs K, N=5): states / orbits / MTBDD nodes / depth / ratio / verify | 249,728 / 124,912 / 11,252 / 21 / 1:22.19 / PASS (249,728 checked, 0 mismatches) | artifacts/class_compression/kpn_n5/compression_results.json | states|canonical_orbits|mtbdd|ratio_states_per_node|verification | MEASURED |
| F25 | Class mirror_n4 (K+P vs K+P+N, N=4): states / orbits / MTBDD nodes / depth / ratio / verify | 136,068 / 68,034 / 15,628 / 24 / 1:8.71 / PASS (136,068 checked, 0 mismatches) | artifacts/class_compression/mirror_n4/compression_results.json | states|canonical_orbits|mtbdd|ratio_states_per_node|verification | MEASURED |
| F26 | Class both_n4 (K+P+N vs K+P+N, N=4): states / orbits / MTBDD nodes / depth / ratio / verify | 1,358,808 / 339,702 / 73,013 / 28 / 1:18.61 / PASS_INPROCESS (339,702 checked, 0 mismatches) | artifacts/class_compression/both_n4/compression_results.json | states|canonical_orbits|mtbdd|ratio_states_per_node|verification | MEASURED |
| F27 | Symmetric-material degradation: K2P four_pawn 1:29.1 -> K+P+N vs K+P+N 1:18.6 | 1.57x worse | arithmetic on C3 and F25 | 63,628/2,183 vs 1,358,808/73,013 | MEASURED |
| F28 | Asymmetric-material degradation: K2P asym_3p 1:36.3 -> K+P+N vs K 1:10.8 | 3.35x worse | arithmetic on C2 and F23 | 74,340/2,050 vs 25,178/2,324 | MEASURED |
| F29 | Mirror class K+P vs K+P+N ratio (worst measured) | 1:8.71 | artifacts/class_compression/mirror_n4/compression_results.json | ratio_states_per_node | MEASURED |
| F30 | Knight-only classes are draw-saturated and structurally trivial (max DTC = 1) | kn ratios 1:44.9 / 1:594.7 / 1:2,813.5 at N=3/4/5; class_max_dtc = 1 | artifacts/class_compression/kn_n{3,4,5}/compression_results.json | ratio_states_per_node|class_max_dtc | MEASURED |
| F31 | Class max DTC (plies): kpn N=4/5, mirror N=4, both N=4 | 25 / 26 / 29 / 34 | artifacts/class_compression/*/compression_results.json | class_max_dtc | MEASURED |
| F32 | K2P+N board-size effect within the kpn class (N=4 -> N=5) | 1:10.83 -> 1:22.19 | artifacts/class_compression/kpn_n{4,5}/compression_results.json | ratio_states_per_node | MEASURED |
| F33 | Full K2P+N 4x4 ratio (17M-state build NOT run) | ~1:20-1:25 extrapolated from the pawn-bearing class band (1:8.7-1:22.2) - NOT measured | extrapolation documented in V2_CHARTER.md sec 8.6 (parent repo) | class band only | EXTRAPOLATED |
| F34 | Peak RSS across the 7 class runs, max | 813.9 MiB (both_n4) | artifacts/class_compression/both_n4/compression_results.json | peak_rss_mib | MEASURED |
| F35 | Z3 v1 conflict buckets per class (basis v1) | kn_nn3: 4, kn_nn4: 6, kn_nn5: 6, kpn_nn4: 518, kpn_nn5: 4004, mirror_nn4: 2946, both_nn4: 17892 | artifacts/z3_injectivity_v2.json | minimality_ladder.v1_conflicts | MEASURED |
| F36 | Z3 v2 conflict buckets per class (basis v2) | 0 on all 7 classes | artifacts/z3_injectivity_v2.json | classes.*.after_v2.conflict_buckets | MEASURED |
| F37 | Feature-basis sizes v1 -> v2 | knight classes 18 -> 28; pawn classes 32 -> 50 | artifacts/z3_injectivity_v2.json | basis_v1.feature_counts | basis_v2.feature_counts | MEASURED |
| F38 | Z3 full-class proof: kn N=3 (unsat) | 1.66 s over 2,112 states | artifacts/z3_injectivity_v2.json (per-class raw: artifacts/z3_classes/kn_n3/z3_injectivity_v2.json) | classes.kn_n3.after_v2.z3_full | MEASURED |
| F39 | Z3 bounded-subspace proofs (unsat) with subspace fraction | kn_n4: wk<2 (14.2%), 2.46 s; kn_n5: wk<1 (4.8%), 18.65 s; kpn_n4: wk<2 (14.5%), 1.86 s; kpn_n5: wk<2 (9.0%), 22.8 s; mirror_n4: wk<2 (14.8%), 18.81 s | artifacts/z3_injectivity_v2.json (raw per class in artifacts/z3_classes/*/z3_injectivity_v2.json) | classes.*.after_v2.z3_subspace | MEASURED |
| F40 | Z3 proof statuses | PROVED: kn_n3; PROVED_ON_SUBSPACE: kn_n4, kn_n5, kpn_n4, kpn_n5, mirror_n4; EMPIRICAL_ONLY: both_n4 (1,358,808 states -> 1,358,808 distinct vectors, proofs skipped above the 60,000-state array cap) | artifacts/z3_injectivity_v2.json | summary.proofs | MEASURED |
| F41 | Mirror-symmetry proof (phi commutes with V') | unsat in 0.25 s (VAL-free); v1-basis version unsat in 0.17 s | artifacts/z3_classes/mirror_n4/z3_injectivity_v2_mirror.json (aggregate: artifacts/z3_injectivity_v2.json) | classes.mirror_n4.mirror_proof_v2.z3_mirror_symmetry | MEASURED |
| F42 | Cross-oracle mirror VAL agreements | 136,068 states, 0 mismatches | artifacts/z3_classes/mirror_n4/z3_injectivity_v2_mirror.json (aggregate: artifacts/z3_injectivity_v2.json) | classes.mirror_n4.mirror_proof_v2.cross_oracle_mirror_val | MEASURED |
| F43 | Minimality ladder: signed knight offsets ALONE close no class | A-only, B-only, AB leave 4-16 buckets on knight classes and 441-8,192 on pawn classes | artifacts/z3_injectivity_v2.json | minimality_ladder.{A_only,B_only,AB}_conflicts | MEASURED |
| F44 | Minimality ladder: closing combinations | knight classes: {A,C} = {B,C} = 0 at N=3/4/5 (rank-edge REQUIRED: AB without C keeps 8); pawn classes: {A,B,D} = {A,B,E} = 0; opp-orientation split O redundant | artifacts/z3_injectivity_v2.json | minimality_ladder.findings | MEASURED |
| F45 | Z3 version used | 5.4.1 | artifacts/z3_injectivity_v2.json | z3_version | MEASURED |
| F46 | Z3-certified counterexamples under basis v1 (per class) | kn_n3: 4, kn_n4: 6, kn_n5: 6, kpn_n4: 12, kpn_n5: 12, mirror_n4: n/a (mirror class: verified symmetry only), both_n4: 12 | artifacts/z3_injectivity_v2.json | classes.*.before_v1.certified_counterexamples | MEASURED |
| D1 | E1: atlas closure at phase 7b - residual | 0 (residual_core 0, residual_leftover 0); psi_v7b_global 154,888 states at accuracy 1.0 | artifacts/e_diagnostics/phase7b_results.json | residual|residual_core|residual_leftover|psi_v7b_global|psi_v7b_acc | MEASURED |
| D2 | E1: the 93.84% (145,354 states) atlas figure was a phase-6c snapshot, superseded by 7b closure | correct framing documented in frozen repo README lines 5/18 and diagnostics meta | artifacts/diagnostics_summary.json | meta.durable_prior_results_used | MEASURED |
| D3 | E1: v7a baseline atlas 151,042 states + 3,846 repaired (578 + 3,268) -> 154,888 closure | 151,042 + 3846 | artifacts/e_diagnostics/phase7b_results.json | baseline_psi_v7a|delta|mandate1_tails.net|mandate2_eval_4p_2v2.net | MEASURED |
| D4 | E2 contact share (B) and non-contact race share (A), N=4 per family | duel: A 15.6974% / B 88.9835%; asym_3p: A 2.7764% / B 99.6341%; four_pawn: A 0.3395% / B 100.0%; all: A 3.1868% / B 98.6209% | artifacts/e_diagnostics/e2_contact_race.json | N4.families.*.{A_pct,B_pct} | MEASURED |
| D5 | E2 N=5 per family (A = non-contact race) | duel: A 28.4531% / B 80.7611%; asym_3p: A 11.4173% / B 97.3354%; four_pawn: A 4.1846% / B 99.9124%; all: A 6.8717% / B 98.6783% | artifacts/e_diagnostics/e2_contact_race.json | N5.families.*.{A_pct,B_pct} | MEASURED |
| D6 | E2 original artifact lost in sandbox outage; re-run 2026-11-15 from durable oracle arrays | Original e2_e4_contact_mzz.json lost in the sandbox outage; this re-run recomputes E2 from the durable oracle arrays. | artifacts/e_diagnostics/e2_contact_race.json | meta.note | MEASURED (re-run) |
| D7 | E3: deepest-path depth equals distinct-feature count on every trace; no feature repeats (ordered-MTBDD structural property) | null | artifacts/e_diagnostics/e3_trace_comparison.json | verdict (+ traces.*.{depth,n_distinct_features,any_feature_repeated}) | MEASURED |
| D8 | E3: N=6 depth prediction (duel/asym_3p/four_pawn/full) | 16-17 / 24-25 / 26-27 / 29-31 (point estimate 30) - extrapolated, not measured | artifacts/e_diagnostics/e3_trace_comparison.json (prediction section) | chain_analysis.prediction | EXTRAPOLATED |
| D9 | E4: N=4 mutual zugzwang = 8 placements / 16 states; 100% pure blockade wall | 8 placements, 16 states; pure_blockade_wall 100.0% | artifacts/e_diagnostics/e4_mzz_signature.json | N4.{mzz_placements,mzz_states,mechanism_distribution} | MEASURED |
| D10 | E4: N=5 mutual zugzwang = 168 placements; 0 counterexamples to the blocked-contact prediction at either N | pure_blockade_wall 154 (91.67%), adjacency_gridlock 12, push_blocked_only 2 | artifacts/e_diagnostics/e4_mzz_signature.json | N5.mechanism_distribution | MEASURED |
| D11 | E4 N=4 durable cross-check: phase 7b mutual_zugzwang_exact | 16 states = 8 placements x 2 tempos | artifacts/e_diagnostics/phase7b_results.json | mutual_zugzwang_exact | MEASURED |
| D12 | E5 surviving core: solver wall/RSS already in F5-F7; N=5 trace-mode walls (duel/asym_3p/four_pawn/full) | 4.2 / 51.0 / 123.5 / 163.8 s | artifacts/diagnostics_summary.json (lost_entries_not_restorable.e5_timing.durable_evidence) | v1_trace_mode_wall_s | MEASURED |
| D13 | E5 phase-level timing split (canon/features/walk %) | LOST - the pre-outage e5_timing.json was destroyed and the split was never re-run; only walls/RSS survive | artifacts/diagnostics_summary.json | lost_entries_not_restorable.e5_timing.status | LOST |
| D14 | E6 translation-invariant share of used features, per family, N=4 -> N=5 | duel 81.0 -> 90.0; asym_3p 80.0 -> 82.4; four_pawn 84.4 -> 87.5; full-space N=5 82.4 (percent of surviving features that are translation-invariant) | artifacts/diagnostics_summary.json (e6 section; raw counts in e_diagnostics/e6_feature_symmetry.json) | e6_feature_symmetry.survivor_level_ti.n{4,5}_*.pct | MEASURED |
| D15 | E6: only edge-folded file metrics (e_R/e_A/e_D at N=4; e_R/e_A at N=5) are absolute-coordinate among survivors; no raw absolute square in the semantic basis | {"duel_24": ["e_R", "e_A", "e_D", "e_p"], "d7_semantic_50": ["e_R", "e_A", "e_D", "e_p", "e_A2", "e_D2"], "d7_tail_6": ["cwk", "cbk", "cw1", "cw2", "cb1", "cb2" | artifacts/diagnostics_summary.json | e6_feature_symmetry.absolute_coordinate_features | MEASURED |
| D16 | Emitted evaluator speed vs dict baseline (K2P frozen repo benchmark, CPython 3.12, best-of-passes): routed full-space 4.45 us/state; four_pawn routed 4.73 vs dict 3.05; duel routed 3.04 vs dict 2.53 | the emitted evaluator is SLOWER than a dict lookup; accepted for verifiability | k2p-algebraic-closure@76ba614 README.md, speed table | metrics table rows 'End-to-end latency', per-family speed table | MEASURED |
| T1 | tuning_summary.json (Tracks A-D tuning tables) | LOST - verified absent by recursive search on 2026-11-15 (HANDOFF.md sec 4.3); variable-ordering and feature-elimination result tables are unreproducible from the archive | research/k2p/HANDOFF.md sec 4.3 (parent repo) | n/a - artifact absent | LOST |
| T2 | Feature-elimination result (652 -> 605 at N=4) and variable-ordering result (baseline 4,885 best) | UNVERIFIABLE - numbers appear only in the tasking notes, not in any surviving artifact; recorded here as OPEN | no artifact | n/a | OPEN |
| T3 | Surviving tuning conclusions recorded in the charter (pre-outage): baseline 'names' ordering wins on nodes; unified emission saves ~7.5% nodes; memoization is slower than lazy inlining | qualitative recommendations only (V2_CHARTER.md sec 9.2-9.3) | research/k2p/V2_CHARTER.md sec 9 (parent repo) | sections 9.2, 9.3 | MEASURED (conclusions; tables lost) |
| T4 | Track B (independent enumeration) is the one tuning-track artifact with a durable result | predicted 6,744,724 legal states at N=5 - exactly confirmed by the solver (see F12) | artifacts/scaling_summary.json | meta.n5_prediction_check | MEASURED |
| T5 | N=5 exhaustive evaluator verification (Track A re-run gate) | 6,744,724 states evaluated, 0 value mismatches, 0 absolute mismatches, 6.748 us/state, verdict PASS | artifacts/e_diagnostics/track_a_verify.json | legal_count|evaluated_count|value_mismatches|verdict | MEASURED |
| T6 | Class-run verification discipline | every one of the 7 class runs ends in an emitted-evaluator verification with 0 value mismatches (see F20-F26) | artifacts/class_compression/*/compression_results.json | verification.value_mismatches | MEASURED |
| T7 | K2P+N oracle ruleset scope | repo ruleset D1-D4 plus two knight-driven generalisations R1/R2; validated by 5 self-tests including an exact knight-free cross-check against the frozen K2P phase-1 npz at N=3/4/5 | research/k2p/V2_CHARTER.md sec 8.6 (parent repo); k2pn_classes.py header | header docstring | MEASURED (documented) |
| T8 | K2P+R (sliding piece) follow-up | NOT RUN - proposed as future work | research/k2p/PAPER_SCOPE.md sec 2 (parent repo) | sec 8 | OPEN |
| T9 | Lean formalization of the retrograde recursion / injectivity encoding | NOT DONE - deferred; Z3 certification is machine-checked today | research/k2p/PAPER_SCOPE.md sec 2 (parent repo) | sec 8 | OPEN |
| T10 | N=6 board build | NOT RUN - oracle scale ~2.9e8 states, out of scope by charter | research/k2p/PAPER_SCOPE.md sec 2 (parent repo) | sec 8 | OPEN |
