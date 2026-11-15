# Two-Axis Scaling of Chess Value Function Compression: Board Size Helps, Balance Hurts

**mikeewwwwwwwwww** — Independent Research — mikeewwwwwwwwww@users.noreply.github.com

*Markdown mirror of `paper/scaling/main.tex` (same content, same tables, same figure captions; the PDF is the artifact of record).*

## Abstract

We study how two scaling axes affect the compressibility of exact game value functions, using a solved 4x4 chess fragment (kings, pawns; oracle solved by retrograde analysis) whose value function is compiled into a zero-lookup multi-terminal binary decision diagram (MTBDD). First, we port the compressor to an N-parameterized form and measure N=3,4,5 (1,032 to 6,744,724 legal states). Board size *helps*: the routed compression ratio improves from 1:31.7 at N=4 to 1:79.7 at N=5 (1:86.1 for the unified single-MTBDD build), with node growth sub-linear in states (log-log OLS exponent 0.775) and routed MTBDD depth growing only +1 to +3 per family (the unified N=5 build: depth 26). Second, we add one knight per side (K2P+N) and measure compression class-by-class across seven (material, N) combinations. Balance *hurts*: adding a knight at fixed material balance degrades the ratio 1.57x (1:29.1 to 1:18.6), and unbalanced material degrades it 3.35x-4.17x (1:36.3 to 1:10.8; worst measured class 1:8.7); we revise an earlier piece-count interpretation to identify material balance as the operative variable. Third, Z3 certifies feature-basis value-sufficiency on all seven classes after a signed-offset basis repair (v1 refuted, with certified concrete counterexamples on the six classes that publish pairs; v2 closed, incl. a mirror-symmetry proof, unsat in 0.25 s, and 136,068 cross-oracle agreements). We claim no progress on full chess; we characterize one boundary of one method.

**Keywords:** chess endgames, value-function compression, multi-terminal BDDs, retrograde analysis, SMT certification, scaling studies

## 1. Introduction

Compression of a solved game's value function is more than a storage problem: how small a representation suffices to reproduce every value is a measurable proxy for how much *structure* the game's outcome function actually has. Endgame databases compress chess endgames extremely well by indexing states geometrically (Thompson 1986; Nalimov et al. 2000), and symbolic methods compress Boolean and integer-valued functions as decision diagrams (Bryant 1986, 1992; Bahar et al. 1997; Fujita et al. 1997). What neither tradition answers directly is a scaling question: when the game gets bigger, does the representation get proportionally bigger, better, or worse? Chess generalizations are provably hard in the limit (Fraenkel and Lichtenstein 1983; Robson 1984), but between a solved fragment and the full game lies a measurable regime that has rarely been instrumented.

This paper instruments that regime. Our subject is K2P-4x4, a solved 4x4 king-and-two-pawns-per-side fragment whose value function is compiled into an emitted, pure-integer, zero-lookup MTBDD evaluator. We port the solver and the compressor to an N-parameterized form (an NxN board, N in {3,4,5}), then move along a second, independent axis: we add a knight per side (K2P+N) and solve seven (material class, N) combinations exactly. On both axes we measure the same quantity — how many MTBDD nodes are needed per legal state — and certify the feature basis that makes the compilation sound using Z3.

### 1.1 Problem: compression as a proxy for structural learnability

A value function V over a finite game graph is a lookup table over |S| states. A compressed evaluator replaces the table by a decision structure whose size reflects the structure of V: if nearby states share values for shared reasons, a small number of feature tests suffices. In this sense the compression ratio (states per MTBDD node) is a proxy for the structural learnability of the game's outcome function — the same intuition that motivates learned value functions in game AI (Silver et al. 2017, 2018; Schrittwieser et al. 2020), except that here the value function is exact, so the measurement is exact.

### 1.2 Contributions

- **Board-size axis (Sec. 4):** an N-parameterized retrograde oracle and MTBDD compressor, measured to N=5 (6,744,724 states, 32,551,012 edges, 110 s solve). The routed ratio improves 1:31.7 -> 1:79.7; the unified single-MTBDD build at N=5 reaches 1:86.1 (78,305 nodes). Node growth is sub-linear (states^0.775, pooled log-log OLS over ten builds; per-family 0.745-0.763).
- **Balance axis (Sec. 5):** class-by-class K2P+N compression. One added knight per side at fixed balance degrades the ratio 1.57x; unbalanced material degrades it 3.35x (worst measured class 1:8.7). Knight-only classes are structurally trivial and excluded from the degradation claims.
- **The balance reframe (Sec. 5.4):** we originally read the degradation as a piece-count effect; the class pattern (unbalanced classes degrade more than balanced ones at similar piece counts) supports material balance as the operative variable.
- **Symbolic certification (Sec. 6):** Z3-certified value-sufficiency of the feature basis on all seven classes: basis v1 refuted with concrete counterexamples (mate-net geometry, rank translation, pawn geometry); basis v2 (signed offsets + rank-edge distances + signed pawn offsets) closes all classes; mirror symmetry of the basis proved (unsat, 0.25 s) with 136,068 cross-oracle agreements.
- **Architectural correction (Sec. 2):** the source artifact's "93.84% atlas + 6.16% MTBDD residual" framing was a phase-6c snapshot; the atlas reaches exact closure at phase 7b (residual = 0, accuracy 1.0 over all 154,888 states), and the MTBDD is a parallel zero-lookup compilation of the same closed value function.

### 1.3 Scope and non-claims

This is a measurement study of one method on one fragment family. We do not claim progress toward solving chess; the 8x8 initial position sits at the material-balance extreme where this architecture is expected to fare worst (Sec. 8). Z3 certifies that the feature basis is *sufficient* for correct compilation; it proves nothing about ratios. Every claim in this paper carries an evidence tier (Sec. 2.4, Table 1), and two result tables of the underlying study were lost to a sandbox outage and are reported as lost, not reconstructed (Sec. 9).

## 2. Background and Corrected Framing

### 2.1 The K2P-4x4 artifact

K2P-4x4 solves every legal position of kings plus up to two pawns per side on a 4x4 board (154,888 legal states, 531,456 directed edges) by retrograde analysis with distance-to-conversion (DTC) iteration, then compiles the value function into per-family MTBDDs and emits a pure-integer evaluator with no lookups on the evaluation path. The artifact's ruleset is a controlled simplification of chess (no castling, no en passant, promotion capped by board size); its oracle was validated by mirror-symmetry, anti-symmetry, and K-vs-K self-tests, and our N-parameterized oracle reproduces the frozen N=4 artifact exactly (Sec. 3.3).

### 2.2 Architectural correction: the atlas closes at phase 7b

The source repository's README presented the architecture as "93.84% analytic atlas + 6.16% MTBDD residual." That is a phase-6c snapshot (145,354 of 154,888 states). The atlas was subsequently completed: at phase 7b the piecewise-algebraic atlas covers all 154,888 states with accuracy 1.0 and residual 0 (phase7b_results.json: residual, residual_core, and residual_leftover all = 0; the 151,042-state v7a baseline plus 3,846 repaired states reach full closure). The correct framing, which we use throughout, is: *the atlas reaches exact closure; the MTBDD is a parallel zero-lookup compilation of the same closed value function*, not a lossy refinement of an incomplete atlas. The construction path uses enumeration and retrograde search; the evaluation path does not.

### 2.3 What "compression" means here

The compression ratio is the number of legal states divided by the number of MTBDD nodes (states per node; larger is better). Two build modes exist and must not be conflated: *routed* builds compile each material family separately and route evaluation by family (three MTBDDs at N=4; 4,885 nodes in total), and a *unified* build compiles a single MTBDD over all families. The like-for-like board-size comparison is routed-to-routed: 4,885 nodes / 154,888 states = 1:31.7 at N=4 versus 84,618 nodes / 6,744,724 states = 1:79.7 at N=5. The N=5 *unified* build (78,305 nodes, 1:86.1) additionally benefits from unification itself (a 7.5% node saving over the routed N=5 total); no unified N=4 build exists, so we never quote 1:31.7 -> 1:86.1 as a single-methodology improvement.

### 2.4 Evidence taxonomy

Every quantitative claim in this paper is tagged with one of three evidence tiers, and each resolves to a JSON artifact and key path in the companion repository's FACTS.md (88 claims total: 80 MEASURED, 2 EXTRAPOLATED, 2 lost, 4 OPEN). Table 1 lists the claims this paper relies on.

**Table 1. Evidence taxonomy** (condensed; the full 88-row table with exact JSON key paths is FACTS.md in the companion repository).

| Claim | Tier | Source |
|---|---|---|
| N=5: 6,744,724 states, 32,551,012 edges, 110 s | MEASURED | scaling_summary.json |
| N=4 oracle byte-identical to frozen artifact | MEASURED | scaling_summary.json (meta) |
| Track B enumeration predicted 6,744,724 | MEASURED | scaling_summary.json (meta) |
| routed 1:31.7 -> 1:79.7; unified 1:86.1 | MEASURED | compression_summary.json |
| nodes ~ states^0.775 (pooled OLS) | MEASURED (fit) | compression_summary.json |
| classes: 1.57x / 3.35x degradation | MEASURED | class_compression/*.json |
| Z3 v1 refuted (4-17,892 conflicts) | MEASURED | z3_injectivity_v2.json |
| Z3 v2 closes all 7 classes | MEASURED | z3_injectivity_v2.json |
| mirror proof 0.25 s; 136,068 agreements | MEASURED | z3_injectivity_v2_mirror.json |
| full K2P+N ratio ~1:20-25 | EXTRAPOLATED | class band only |
| N=6 depth 29-31 (point 30) | EXTRAPOLATED | e3_trace_comparison.json |
| E5 phase timing split | lost | outage; walls survive |
| tuning tables (Tracks A-D) | lost | HANDOFF Sec. 4.3 |
| K2P+R; Lean formalization | OPEN | not attempted |

## 3. Methodology

### 3.1 N-parameterized oracle

The oracle enumerates king pairs, per-side piece configurations, and pawn configurations on an NxN board, filters legality, and solves the resulting game graph by retrograde fixpoint iteration followed by DTC sweeps. Values are mover-relative (1 = mover wins, 2 = mover loses, 3 = draw). The knight-free ruleset is exactly the frozen artifact's; the K2P+N ruleset adds two knight-driven generalisations (knight moves and knight captures) and is validated by five self-tests, including an exact cross-check of every knight-free sub-block against the frozen phase-1 arrays at N=3,4,5 and colour-swap/file-reflection invariance over all closure states.

### 3.2 N-parameterized compressor

The compressor computes the orbit quotient of the state graph under colour-swap and board-reflection symmetry, extracts a semantic feature vector per orbit, sorts the rows, builds an ordered MTBDD over the features, and appends a conditional six-coordinate tail when semantic features alone cannot separate value classes (Fig. 4 shows the resulting ordered structure). It then emits a pure-integer evaluator (if/else chains only, no arrays or dictionaries on the evaluation path) and verifies it against the oracle over every legal state. Verification is exhaustive at these scales: at N=5 all 6,744,724 states were evaluated with zero mismatches.

### 3.3 Trust gates

Two gates anchor the pipeline. First, at N=4 the generalized compressor reproduces the frozen artifact's builds exactly: the only difference between the emitted evaluators is one provenance header line each. Second, the N=5 state count was predicted independently — an enumeration program written without access to the solver (Track B) predicted 6,744,724 legal states, which the solver then reproduced exactly. The N=5 oracle self-tests (mirror symmetry, anti-symmetry, K-vs-K draws) pass, and the qualitative value distribution is preserved from N=4 to N=5 (draw share 6.92% -> 4.98%, decided 95.02%).

### 3.4 Experimental protocol for K2P+N

The full K2P+N 4x4 space is ~17M states and was deliberately *not* built (a workstation-class run; see Sec. 9). Instead, seven (class, N) combinations were solved exactly with a dedicated class oracle and compressed with the same pipeline: K+N vs K+N at N=3,4,5; K+P+N vs K at N=4,5; K+P vs K+P+N and K+P+N vs K+P+N at N=4. Classes partition the material space, so every ratio is measured over a complete, closed material class; no sampling is involved.
## 4. The Board-Size Axis

### 4.1 Oracle scaling

Table 2 reports the oracle measurements. States grow 150x from N=3 to N=4 and 43.5x from N=4 to N=5; edges grow faster than states (61.2x N=4->5), the mark of a densifying game graph. Solve time grows 61.2x (2.0 s -> 110.5 s wall including startup), i.e. in line with the state-count growth, on a laptop-class sandbox. Max DTC grows 4 -> 13 -> 38 plies — far slower than the state count, though faster than any linear law in N, and small in absolute terms — while the draw share falls 28.1% -> 6.9% -> 5.0%: bigger boards give attacks room to convert, and the qualitative character of the fragment (decisive, mirror-symmetric, draw-poor) is preserved.

**Table 2. Oracle scaling** (all values MEASURED; scaling_summary.json / phase1_results.txt).

| N | legal states | directed edges | wall (s) | max DTC | draws |
|---|---|---|---|---|---|
| 3 | 1,032 | 1,332 | 0.2 | 4 | 28.10% |
| 4 | 154,888 | 531,456 | 2.0 | 13 | 6.92% |
| 5 | 6,744,724 | 32,551,012 | 110.5 | 38 | 4.98% |

### 4.2 Compression scaling

Table 3 reports per-family MTBDD builds. Every family's ratio improves with board size (duel 1:26.0 -> 1:45.4; asym_3p 1:36.3 -> 1:82.9; four_pawn 1:29.1 -> 1:80.8), and the routed totals improve 1:31.7 -> 1:79.7. Per-family routed depth grows 15->16, 19->22, and 21->24 over a 43.5x state growth (the unified N=5 build reaches depth 26).

**Table 3. Compression scaling per family and build mode** (all values MEASURED; compression_summary.json). Ratio = states per MTBDD node.

| family | N | states | nodes | depth | ratio |
|---|---|---|---|---|---|
| duel | 3 | 604 | 59 | 10 | 1:10.2 |
| duel | 4 | 16,920 | 652 | 15 | 1:26.0 |
| duel | 5 | 177,640 | 3,917 | 16 | 1:45.4 |
| asym_3p | 4 | 74,340 | 2,050 | 19 | 1:36.3 |
| asym_3p | 5 | 1,909,806 | 23,034 | 22 | 1:82.9 |
| four_pawn | 4 | 63,628 | 2,183 | 21 | 1:29.1 |
| four_pawn | 5 | 4,657,278 | 57,667 | 24 | 1:80.8 |
| routed total | 4 | 154,888 | 4,885 | — | 1:31.7 |
| routed total | 5 | 6,744,724 | 84,618 | — | 1:79.7 |
| unified | 5 | 6,744,724 | 78,305 | 26 | 1:86.1 |

### 4.3 Mechanisms

Two mechanism experiments explain why board size helps. **E3 (distinct-feature growth):** on an ordered MTBDD, each feature can be tested at most once along any root-to-leaf path, so path depth equals the number of *distinct* features visited; measured deepest paths confirm depth = distinct-feature count on all seven traces (duel 15->16, asym_3p 19->22, four_pawn 21->24, full 26; Fig. 4). Compression therefore does not degrade with board size because new features activate only slowly (+1 to +3 per family per step of N), while the orbit quotient merges exponentially more placements. **E6 (translation invariance):** the semantic basis is almost entirely translation-invariant — the share of used features invariant under file and rank translation rises with N (duel 81.0%->90.0%, asym_3p 80.0%->82.4%, four_pawn 84.4%->87.5%; the only absolute-coordinate survivors are edge-folded file metrics). A bigger board amortizes the same relative geometry over exponentially more absolute placements, which is exactly what a translation-invariant feature set can exploit. **E4 (mutual zugzwang):** placements where the mover loses with either tempo (8 at N=4, 168 at N=5) are 100% blocked-contact structures at N=4 and 100% blocked-or-adjacent at N=5 (zero counterexamples): a compact semantic handle that survives scaling. E2's original causal hypothesis (non-contact race share drives compression) remains unverified; its re-run supplies shares, not causes.

**Figure 1.** MTBDD nodes vs. legal states, log-log (MEASURED; compression_summary.json). All family builds, routed totals, and the unified N=5 build sit on a sub-linear trend (pooled OLS exponent 0.775; dotted line: nodes = states).

**Figure 4.** Deepest root-to-leaf path of the duel MTBDD at N=4 (15 tests) and N=5 (16 tests), with the feature tested at each level (MEASURED; e3_trace_comparison.json). On an ordered MTBDD each feature appears at most once per path, so depth = distinct-feature count; board size adds one new discriminating feature, not a proportional growth in tests.

### 4.4 Growth law

Pooling the ten family/total builds (N in {3,4,5}, both build modes) and fitting log10(nodes) on log10(states) by ordinary least squares yields an exponent k = 0.775 (k = 0.745-0.763 within families; Fig. 1). Node counts grow meaningfully slower than the state space: a 43.5x state growth costs only a 17.3x node growth (routed-to-routed, 4,885 -> 84,618); the unified N=5 build needs 78,305 nodes (7.5% fewer than the routed N=5 total). The consistent per-family range and the stable depth growth support a sub-linear growth law over the measured range; we extrapolate no further than N=5 except for the explicit N=6 depth prediction reported in the companion diagnostics (29-31 plies, point estimate 30, marked EXTRAPOLATED).

## 5. The Balance Axis (K2P+N)

### 5.1 Class selection and coverage

Table 4 lists the seven class runs. Classes were chosen to isolate the two candidate drivers of degradation: piece count (one added knight per side at *fixed* material balance) and material balance (symmetric vs. unbalanced material at similar piece counts).

**Table 4. K2P+N class-by-class compression** (MEASURED; class_compression/*.json). Ratio = legal class states per MTBDD node; verify = emitted-evaluator check against the class oracle (0 value mismatches everywhere). RSS = peak MiB.

| class (per side) | N | states | orbits | nodes | depth | ratio | verify | RSS |
|---|---|---|---|---|---|---|---|---|
| K+N vs K+N | 3 | 2,112 | 528 | 47 | 13 | 1:44.9 | PASS, 0 mism. | 36 |
| K+N vs K+N | 4 | 46,384 | 11,596 | 78 | 17 | 1:594.7 | PASS, 0 mism. | 56 |
| K+N vs K+N | 5 | 391,072 | 97,804 | 139 | 16 | 1:2,813.5 | PASS, 0 mism. | 224 |
| K+P+N vs K | 4 | 25,178 | 12,589 | 2,324 | 18 | 1:10.8 | PASS, 0 mism. | 67 |
| K+P+N vs K | 5 | 249,728 | 124,912 | 11,252 | 21 | 1:22.2 | PASS, 0 mism. | 346 |
| K+P vs K+P+N | 4 | 136,068 | 68,034 | 15,628 | 24 | 1:8.7 | PASS, 0 mism. | 213 |
| K+P+N vs K+P+N | 4 | 1,358,808 | 339,702 | 73,013 | 28 | 1:18.6 | PASS (in-proc), 0 mism. | 814 |

### 5.2 Measured degradation

The informative comparison is at fixed board size N=4, against the knight-free K2P families built by the same pipeline:

- **Symmetric material:** K2P four_pawn (K+2P vs K+2P, balanced) compresses at 1:29.1; adding one knight per side at the same balance (K+P+N vs K+P+N) compresses at 1:18.6 — a 1.57x degradation (nodes 2,183 -> 73,013, depth 21 -> 28).
- **Unbalanced material:** K2P asym_3p (K+2P vs K+P) compresses at 1:36.3; adding a knight to the weaker side (K+P+N vs K) compresses at 1:10.8 — a 3.35x degradation. The mirror class (K+P vs K+P+N) is worse still at 1:8.7.
- **Knight-only classes:** K+N vs K+N compresses at 1:595-1:2,814. These classes are draw-saturated with max DTC = 1 (every decided state converts immediately), so their ratios reflect a trivially simple value structure; we exclude them from degradation claims rather than present them as compression successes.

Every run's emitted evaluator verifies against its oracle with zero value mismatches, and peak RSS stays below 814 MiB. Correctness is never traded for compression: where the semantic basis cannot separate values, the compiler pays in nodes and a conditional coordinate tail, not in errors.

### 5.3 The balance reframe

We originally interpreted the degradation as a piece-count effect ("board size helps, piece count hurts"). The measured class pattern supports a different reading. First, at fixed balance, adding a knight per side costs 1.57x — real, but modest. Second, at comparable piece counts, unbalanced material costs far more: K+P+N vs K (3 pieces vs. 1) degrades 3.35x and K+P vs K+P+N 4.17x, versus 1.57x for the balanced K+P+N vs K+P+N. Third, depth grows most in the unbalanced classes (24-28 vs. 21 at baseline), indicating more *distinct* features in play, not merely more states. We therefore revise the reading to: *material balance is the operative variable*; piece count contributes, but balance amplifies the cost. The board-size axis helps precisely because it does not touch balance or the feature basis; the balance axis hurts because each imbalance injects new asymmetric structure (kings defending different material) that the translation-invariant, symmetry-quotient architecture cannot amortize. A fixed balance, growing pieces is the mild case; imbalance is the hard case.

**Figure 2.** Compression ratio by material (MEASURED; class_compression/*.json). Balanced material: K2P four_pawn vs. K2P+N (1.57x degradation). Unbalanced material: K2P asym_3p vs. K+P+N vs K and K+P vs K+P+N (3.35x / 4.17x). Knight-only classes (1:595-1:2,814, structurally trivial) are omitted from the bars.

## 6. Symbolic Certification (Z3)

### 6.1 The injectivity problem

The compiler replaces states by feature vectors: two states with the same feature vector phi(s) are compiled into the same MTBDD leaf. This is sound iff the basis is *value-sufficient* on the class: for all s1, s2 in C, phi(s1) = phi(s2) implies VAL(s1) = VAL(s2). When this fails, the pipeline appends a conditional coordinate tail (which restores exactness at node cost); when it holds, the semantic basis alone suffices. Value-sufficiency is the precondition for tail-free compilation; it is sufficient but not necessary for correct compilation, and it says nothing about ratios.

### 6.2 v1 refutation

Basis v1 (5 king features + 13 knight features, plus 14 pawn features on pawn classes; 18 features on knight classes, 32 on pawn classes) was tested on all seven classes. The query "there exist s1, s2 with equal feature vectors and different VAL" is SAT on *every* class: 4, 6, 6, 518, 4,004, 2,946, and 17,892 conflict buckets respectively, with Z3-certified concrete counterexamples on the six classes that publish pairs; the mirror class's refutation is carried by its 2,946 empirical conflict buckets together with the symmetry proof and cross-oracle check described below (Table 5). Three ambiguity mechanisms account for all counterexamples: (1) *knight-square ambiguity* — positions differing only in the knight's exact square share every distance feature (Chebyshev norms discard direction) yet differ in mate-net geometry, hence in value; (2) *rank-translation ambiguity* — whole positions shifted along a file share all signed relative geometry but differ in edge-dependent mates; (3) *pawn-geometry ambiguity* — same-distance, different-file pawn placements relative to kings and knight. The companion methodology paper in this repository (paper/verification) decodes a certified knight-square pair in detail.

### 6.3 v2 fix and the minimality ladder

Basis v2 adds eight signed knight offsets (per-axis deltas from each knight to its own and the enemy king; -1,-1 when the piece is absent), two king rank-edge distances (min(y, N-1-y)), and, on pawn classes, eight signed pawn offsets — 28 features on knight classes, 50 on pawn classes. With v2, the query is UNSAT on all seven classes: zero conflict buckets (Table 5). The signed offsets alone were *not* the fix — a minimality ladder of feature subsets, probed empirically over the full classes, shows that knight-only classes require a signed-offset family *plus* the rank-edge pair, and pawn classes require both signed-offset families plus signed pawn offsets (Table 6); an opponent-orientation split changes nothing and was dropped. The uniform v2 basis is therefore mildly overdetermined by design: one class-independent definition rather than per-class minimality.

**Table 5. Z3 value-sufficiency before/after the basis repair** (MEASURED; z3_injectivity_v2.json). Conflicts = feature-equal buckets with differing oracle values. Proofs: F = full-class unsat; S = bounded-subspace unsat (fraction of class); E = empirical layer only (array axiomatisation skipped above the 60,000-state cap).

| class | N | v1 conf. | v2 conf. | proof (time) |
|---|---|---|---|---|
| K+N vs K+N | 3 | 4 | 0 | F, 1.7 s |
| K+N vs K+N | 4 | 6 | 0 | S (14.2%), 2.5 s |
| K+N vs K+N | 5 | 6 | 0 | S (4.8%), 18.7 s |
| K+P+N vs K | 4 | 518 | 0 | S (14.5%), 1.9 s |
| K+P+N vs K | 5 | 4,004 | 0 | S (9.0%), 22.8 s |
| K+P vs K+P+N | 4 | 2,946 | 0 | S (14.8%), 18.8 s |
| K+P+N vs K+P+N | 4 | 17,892 | 0 | E (1.36M states) |

**Table 6. Minimality ladder** (MEASURED; z3_injectivity_v2.json, minimality_ladder). Shorthand: kn = K+N vs K+N; kpn = K+P+N vs K; mirror = K+P vs K+P+N; both = K+P+N vs K+P+N. A = knight->own signed offsets; B = knight->enemy; C = king rank-edge distances; D = pawn->own signed offsets; E = pawn->enemy; O = opp-orientation split (redundant on every class, dropped).

| class | v1 | A | B | AB | AB+C | AB+D | AB+E |
|---|---|---|---|---|---|---|---|
| kn, N=3 | 4 | 4 | 4 | 8 | **0** | — | — |
| kn, N=4 | 6 | 8 | 8 | 8 | **0** | — | — |
| kn, N=5 | 6 | 16 | 8 | 8 | **0** | — | — |
| kpn, N=4 | 518 | 774 | 538 | 441 | — | **0** | **0** |
| kpn, N=5 | 4,004 | 8,192 | 6,305 | 6,932 | — | **0** | **0** |
| mirror, N=4 | 2,946 | 3,186 | 3,202 | 2,097 | — | **0** | **0** |
| both, N=4 | 17,892 | 7,674 | 8,054 | 7,400 | — | **0** | **0** |

**Figure 3.** Certification flow: basis v1 is refuted on every class; three certified ambiguity mechanisms motivate basis v2, which closes all seven classes.

### 6.4 Mirror symmetry

For the K+P vs K+P+N class, Z3 proved — independently of VAL, in 0.25 s — that phi commutes with the colour-swap mirror V' (phi(V'(s)) = swap_wb(phi(s)) with tau -> 1 - tau; the signed rank deltas are anti-invariant and negated under a piece-presence guard). This is a property the *v1* basis already had (unsat in 0.17 s), so the basis repair preserved colour symmetry. As a semantic cross-check, all 136,068 states of the class were re-evaluated under the mirror against an *independently solved* oracle (the K+P+N vs K+P+N run): 0 mismatches.

### 6.5 Cross-oracle validation

(As above: 136,068 agreements, 0 mismatches, every V'-image present in the balanced-class closure.)

### 6.6 What Z3 proves and what it does not

Z3 proves value-sufficiency of a feature basis on a (sub)space — a soundness certificate for compilation. It does not prove optimality of the basis, does not bound node counts, and does not transfer across material classes. On five classes the proofs are bounded-subspace proofs (an array axiomatisation over 3,640-22,375 states, 4.8-14.8% of the class) because the full-class axiomatisation exceeded the compute budget or the 60,000-state cap; on the 1.36M-state class only the empirical layer (perfect injectivity over all 1,358,808 states) is available. The proof tiers are reported per class rather than averaged into a headline.

## 7. Connection to Balance Laws in the Literature

This section is discussion, not a primary contribution. Independent analyses conducted outside this project (one using the Z.ai GLM model, one using Google Gemini; attributed and marked non-peer-reviewed in the companion repository's supplementary/ai_analyses.md) arrive, from different starting points, at a qualitative "balance law": the structural complexity of pawn-endgame value functions concentrates where material is balanced. Our class-by-class data are consistent with that claim — unbalanced classes degrade 3.35x-4.17x versus 1.57x for the balanced class — and the balance reframe of Sec. 5.3 was made *after* the measurements. We do not claim to have proven any balance law; we claim to have measured one instance of the pattern it predicts, on one fragment family, with exact values.

## 8. Discussion

### 8.1 Why compression degrades at balance

The structural reason is visible in the pipeline's own accounting. The orbit quotient merges states that differ by colour-swap or board reflection; it amortizes *symmetric* structure. Board growth feeds the quotient exponentially more states sharing the same relative geometry (Sec. 4). Material imbalance does the opposite: the sides' kings assume qualitatively different roles (attacker vs. defender), the role-assignment features split, and the number of distinct feature vectors grows faster than the quotient can merge them — visible directly in the conflicting-group counts (e.g., K+P+N vs K: 477 conflicting semantic groups at N=4) and in depth growth (24-28 vs. 21). Balance, not piece count, is what the architecture cannot amortize.

### 8.2 What would extend this work

Three extensions follow directly. (i) *K2P+R*: a sliding piece breaks translation-invariance assumptions hardest and is the sharpest stress test of the balance wall; it is proposed, not run. (ii) *Full K2P+N*: a single workstation build (~17M states, ~6 GB peak RSS by the measured per-state scaling) would replace the extrapolated full-space ratio with one measured row. (iii) *Formal verification at scale*: the subspace-proof boundary (Sec. 6) is an engineering budget, not a mathematical one; a Lean formalization of the encoding would make the certification total.

### 8.3 What we are not claiming

We are not claiming progress on the full game: the 8x8 initial position is at the balance extreme, where this architecture is expected to fare worst, and no measurement here contradicts the classical exponential bounds (Fraenkel and Lichtenstein 1983). We are not claiming a novel decision diagram: the MTBDD machinery is standard (Bryant 1986; Bahar et al. 1997; Fujita et al. 1997); the contribution is the measurement discipline and the certification layer.

## 9. Limitations and Non-Claims

**Speed.** The emitted evaluator is *slower* than a dictionary lookup: 4.73 vs. 3.05 us/state on the four_pawn family (routed full space 4.45 us/state; CPython 3.12, best-of-passes, frozen-repo benchmark). The contribution is verifiability — a pure-integer evaluator whose every branch can be audited against the oracle — not speed. **Extrapolations.** The full K2P+N 4x4 ratio (~1:20-25) is extrapolated from the pawn-bearing class band (1:8.7-1:22.2) and is not measured; the N=6 depth prediction (29-31) is a trend estimate. Both are tagged EXTRAPOLATED in FACTS.md. **Lost artifacts.** A sandbox outage destroyed the phase-level timing split (E5) and the tuning result tables (Tracks A-D); both are reported as lost, with the surviving walls and the charter's qualitative conclusions (baseline variable ordering wins on nodes; unified emission saves ~7.5% of nodes) cited instead. Nothing was reconstructed to fill the gap. **Proof coverage.** Five of seven Z3 verdicts rest on bounded subspaces and one on the empirical layer alone; the certification is a budget-bounded certificate, not a total proof. **No theorem.** The balance-law reading is a measured pattern on one family, not a theorem; no claim of generalization beyond K2P(+N) is made. **No Lean verification.** The retrograde recursion itself is empirically validated (self-tests, cross-checks, exhaustive verification), not formally verified.

## 10. Conclusion

Across two independent scaling axes of a solved chess fragment, the same compression architecture moves in opposite directions. Board size helps: nodes grow as states^0.775, MTBDD depth grows by one to three tests per step of N, and the routed ratio improves from 1:31.7 to 1:79.7 (1:86.1 unified) from N=4 to N=5. Material balance hurts: 1.57x at fixed balance, 3.35x-4.17x unbalanced, with the worst measured class at 1:8.7. The architecture stays exact everywhere (0 mismatches on every emitted evaluator), Z3 certifies the feature basis on all seven classes after a signed-offset repair, and the balance reframe — balance, not piece count, is the operative variable — is a measurement-supported revision, not a fitted story. The piece-count wall documented here is a real boundary of semantic-feature compression, and the two-axis method — solve, compile, certify, measure, per class — is the transferable part.

## Acknowledgment

The author thanks the Z.ai and Google Gemini analyses for the independent balance-law observations cited as non-peer-reviewed context in Sec. 7, and the Z3 team (de Moura and Bjorner 2008) for the solver this certification layer relies on.

## Appendix A. Artifact and Reproducibility Statement

All measurements in this paper resolve to JSON artifacts committed in the companion repository chess-compression-scaling, whose FACTS.md (88 rows, generated programmatically from those artifacts) lists every claim with its exact file and key path; the paper cites the MEASURED subset. The source solver and compressor are the unmodified scripts of the frozen K2P artifact (commit 76ba614); the N-parameterized oracle/compressor and the class and certification scripts live under experiments/ in the companion repository. The trust gates of Sec. 3.3 are re-runnable in minutes: the N=4 oracle solves in ~2 s and the N=4 compression of all three families reproduces the 4,885-node routed total; a CI workflow runs this gate on every push. The N=5 oracle solve is ~110 s wall in the authoring sandbox (CPython 3.12, NumPy 2.1); the smallest Z3 certification (K+N vs K+N, N=3) re-runs in ~1.7 s on the released per-class arrays. Two caveats are part of the record, not footnotes: the phase-level timing split and the tuning-phase result tables were lost to a sandbox outage and are reported as lost, and the full K2P+N 4x4 build was deliberately not run, so the full-space K2P+N ratio remains an extrapolation.

## References

Full numbered reference list in `paper/scaling/main.pdf` / `refs.bib` (31 entries): Zermelo 1913; Shannon 1950; Knuth & Moore 1975; Thompson 1986; Fraenkel & Lichtenstein 1983; Robson 1984; Allis 1994; Gasser 1996; Nalimov, Haworth & Heinz 2000; van den Herik, Uiterwijk & van Rijswijck 2002; Schaeffer et al. 2007; Bryant 1986, 1992; Bahar et al. 1997; Fujita, McGeer & Yang 1997; Burch et al. 1992; Somenzi (CUDD); de Moura & Bjorner 2008, 2011; Bjorner et al. (Programming Z3); Barrett, Fontaine & Tinelli (SMT-LIB 2.6); Biere et al. (Handbook of Satisfiability); Kautz & Selman 1996; Cook 1971; Leroy 2009; Klein et al. 2014; Silver et al. 2017, 2018; Schrittwieser et al. 2020; Stockfish NNUE; k2p-algebraic-closure (this project, commit 76ba614).
