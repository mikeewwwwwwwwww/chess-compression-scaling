# Symbolic Feature-Basis Adequacy Certification for Game Value Compression: A Z3 Case Study

**mikeewwwwwwwwww** — Independent Research — mikeewwwwwwwwww@users.noreply.github.com

*Markdown mirror of `paper/verification/main.tex` (same content, same tables, same figure captions; the PDF is the artifact of record).*

## Abstract

Compiling an exact game value function into a multi-terminal binary decision diagram (MTBDD) over semantic features is sound only if the feature basis is *value-sufficient*: two states with equal feature vectors must have equal values. We formalize this adequacy condition as an existential SMT query and certify it with Z3 for a family of solved chess-fragment classes (kings, pawns, and knights on NxN boards, up to 1.36M states per class). The v1 feature basis of the underlying pipeline is refuted on all seven classes, with concrete, machine-checked counterexamples exhibiting three distinct ambiguity mechanisms (knight-square geometry, rank translation, pawn geometry). The repaired v2 basis — signed per-axis piece-to-king offsets, king rank-edge distances, and signed pawn offsets — closes all seven classes: one full-class unsat proof, five bounded-subspace unsat proofs, and one perfect-injectivity empirical layer above the array-axiomatisation budget. A separate VAL-free proof establishes that the feature map commutes with the colour-swap mirror (unsat in 0.25 s), and 136,068 cross-oracle evaluations agree exactly. The methodological contribution is a budgeted adequacy certificate: cheap to run, refutation-first, and honest about which classes carry full proofs, subspace proofs, or empirical evidence only.

**Keywords:** SMT solving, Z3, decision diagrams, game solving, feature engineering, verification, chess endgames

## 1. Introduction

When a solved game's value function is compiled into a compressed evaluator, the compiler makes an invisible assumption: that the features it tests carry *all* the information the values depend on. If two states share a feature vector but differ in value, the compiled structure must either encode extra coordinates (a "tail") or it silently mis-evaluates. In the K2P compression pipeline — a solved 4x4 chess fragment whose value function is compiled into zero-lookup MTBDD evaluators — this assumption was initially trusted on empirical evidence alone (zero observed conflicts). That evidence was insufficient: when the pipeline was extended to knight-bearing material (K2P+N), a symbolic check found the assumption false, with concrete counterexamples, on every class tested.

This paper is a case study in turning that assumption into a certificate. We formalize feature-basis adequacy as an existential SMT query over the class's state space, encode states, legality, features, and values in Z3, and run a refutation-first protocol: try to break the basis; if it breaks, extract and certify counterexamples; if it survives, prove it — fully when the array axiomatisation fits the budget, otherwise on a bounded subspace, with the empirical layer covering the rest. The protocol closed on a chess-fragment family of seven material classes (2,112 to 1,358,808 states), produced a minimality ladder showing which feature families are load-bearing, and yielded a VAL-free mirror symmetry proof. The companion scaling paper reports the compression measurements this certification underwrites.

There is an order-of-trust question here as well as a measurement one. Empirical validation — enumerate every state, evaluate, compare — is cheap, complete for correctness, and silent in the best sense: it either finds a mismatch or it does not. But it cannot say *why* a representation works, it cannot be consulted when the representation is extended to new material, and its clean verdict on an old family says nothing about a new one. A symbolic certificate reverses the order: it fails fast and loud (concrete witnesses), or it proves the property outright, and its cost is bounded by explicit budgets rather than by trust. The protocol in this paper is built around that reversal, and its per-class verdicts record exactly how far the certificate reached on each class.

**Contributions:**

- a formal statement of feature-basis adequacy for feature-based MTBDD compilation (Sec. 2) and a Z3 encoding of states, legality, features, and values that supports both refutation and proof (Sec. 3);
- a refutation of the v1 basis on all seven classes, with three certified ambiguity mechanisms and a decoded counterexample pair (Sec. 4, Fig. 2);
- the v2 repair (signed offsets + rank-edge distances + signed pawn offsets), a minimality ladder over feature subsets, and closure on all seven classes with per-class proof tiers (Sec. 5, Tables 1-4);
- a VAL-free mirror-symmetry proof and a 136,068-agreement cross-oracle check (Sec. 6); and
- an explicit account of what the certificate proves and what it does not (Sec. 7).

## 2. Problem Statement

### 2.1 Value functions over finite game graphs

Let G=(S,E) be the game graph of a finite, perfect-information, two-player game under a fixed ruleset, with S the set of legal states (a state includes the side to move). The retrograde oracle computes the mover-relative value VAL: S -> {win, loss, draw} exactly — including the cycle-draw convention for unresolvable repetitions — by backward induction over E (Thompson 1986; Allis 1994). Databases of this kind are the classical substrate of endgame solving (Nalimov et al. 2000; Schaeffer et al. 2007; van den Herik et al. 2002); the contribution here is not the oracle but the certificate attached to its compressed representation. Two conventions matter for everything that follows. First, values are *mover-relative*: VAL(s) is the result for the player to move at s, which halves the state space relative to a white-to-move convention and makes mirror symmetry a value-preserving map rather than a value-negating one. Second, unresolvable repetition cycles are decided as draws by a fixed-point convention (cycle draws), so VAL is total over legal states and the array axiomatisation of Sec. 3 is exact rather than partial.

### 2.2 MTBDD as compressed evaluator

The compiler groups states by a symmetry quotient (colour swap and board reflection), assigns each orbit a semantic feature vector phi(s) (relative distances, alignments, attack and check counts, material counts, tempo), and builds an ordered MTBDD (Bryant 1986, 1992; Bahar et al. 1997; Fujita et al. 1997; Burch et al. 1992) over the features, with a conditional coordinate tail appended when features alone cannot separate value classes. The construction is deterministic: orbits are sorted, rows are sorted lexicographically over the feature vector, and the MTBDD is built over the features in a fixed order (with the tail coordinates tested after the semantic features, only on the rows that need them). The emitted evaluator is a pure-integer branching program: no tables, no arrays, no search on the evaluation path. Its correctness criterion is exact agreement with VAL on every legal state, which the pipeline checks exhaustively at these scales (all 6,744,724 states at N=5; every class run in the underlying study verified with zero mismatches).

### 2.3 The injectivity question

Grouping states by feature vector is sound iff the basis is *value-sufficient* on the class C: for all s1, s2 in C, phi(s1) = phi(s2) implies VAL(s1) = VAL(s2). Note the direction: this is a *sufficient* condition for correct compilation without a tail, not a necessary one (the tail restores correctness regardless), and it makes no claim about compression ratio. Empirically, it can only be verified by enumerating all |C|^2 pairs — or, better, by observing that equal feature vectors define equivalence classes whose value sets must be singletons, which is checkable in O(|C|) bucketing. But the empirical check says nothing about *why* the basis works or how to repair it when it fails, and it cannot distinguish a sound basis from an unlucky sample. The symbolic query answers both: it certifies refutation with a concrete pair when the condition fails, and proves it when it holds.

## 3. Z3 Encoding

### 3.1 State space and legality

Each class fixes a material vector (per side: king always; pawn and/or knight flags) and a board size N. A state is packed into seven 16-bit fields [wk, bk, wp, bp, nw, nb, stm] (square index x + yN; absent pieces fixed to the sentinel -1; stm in {0,1}). Sixteen bits are enough to hold any square index, the sentinel, and the sign bit for signed intermediate values, which keeps the bit-blasted arithmetic small. In Z3, two fresh symbolic states s1, s2 are created as BitVec variables of width 16 per field; absent-piece fields become the constant sentinel, so the solver never explores material configurations outside the class. The legality predicate is rewritten symbolically from the solver's own rules (kings never adjacent; pawns blocked by occupancy and captured diagonally; promotion constrained by board edge; knight moves and captures; the side *not* to move may not be in check; no illegal sentinels), so that legal(s) characterises exactly the class's legal states. A bijective packing ENC(s) into 32 bits — a mixed-radix product of the per-piece indices and the tempo — makes every legal state a distinct array key, which is what allows the value oracle to enter the encoding as an array lookup rather than a per-state predicate.

### 3.2 Feature extraction

The feature map phi is re-implemented over the BitVec fields with the *same feature names and definitions* as the compression pipeline's Python implementation: modular per-axis differences (wrap-around arithmetic with modulus N^2+1 handles board-edge distances), Chebyshev distances as max/min of absolute modular deltas, knight-attack and check counts, alignment features, rank-edge distances, and the v2 signed offsets (Sec. 5). Unsigned division and remainder by N extract file and rank; signed interpretations are applied after the fact so that the bit-blasted arithmetic matches the Python semantics exactly, including the sentinel propagation (any feature involving an absent piece is the sentinel, not a computed value). Each v1 counterexample check and each proof run is accompanied by unit self-tests that evaluate the symbolic phi on 500 concrete states per class and compare against the Python extraction, exactly; an encoding that drifts from the pipeline's features would fail these tests (and, in the other direction, a SAT result where the empirical layer reports zero conflicts is flagged as a suspected encoding bug and reported as such).

### 3.3 The injectivity query and the value oracle

The value function enters the encoding as an SMT array VAL : BV32 -> BV8, constructed as a chain of Store operations — one per class state — at the packed encodings with the oracle's values. The array is therefore an exact finite map of the class, and the query

    exists s1, s2: legal(s1) and legal(s2) and phi(s1) = phi(s2)
                  and VAL[ENC(s1)] != VAL[ENC(s2)]

ranges over exactly the class. Because the array must enumerate one Store per state, the axiomatisation has a hard budget (--max-proof-states, 60,000 in this study): classes above the cap cannot carry a full proof, whatever their size. The remaining protocol budgets are equally explicit: 300 s per full-class or subspace proof, a subspace target of 10% of the class, and a cap of 12 certified counterexample pairs per class (one per reported bucket, up to the cap). The protocol per class is (Fig. 1):

1. **empirical layer**: bucket all |C| states by feature vector in Python; record conflict buckets;
2. **if conflicts exist**: extract one pair per bucket, re-verify each pair *symbolically* (both states concrete, both legality and feature equality re-encoded in Z3), and report REFUTED with machine-checked counterexamples;
3. **if no conflicts**: attempt the full-class query; UNSAT => PROVED; timeout => fall through;
4. **subspace proof**: restrict to a geometric subspace (white king square < K, with K grown until the subspace covers >= 10% of the class or hits the array cap); UNSAT there => PROVED_ON_SUBSPACE;
5. **otherwise**: EMPIRICAL_ONLY.

**Table 2. Protocol parameters** (command-line defaults of the committed script; Z3 5.4.1).

| parameter | value |
|---|---|
| bit-vector width per field | 16 |
| state packing width | 32 bits (bijective) |
| full-class / subspace proof budget | 300 s each |
| array axiomatisation cap | 60,000 states |
| subspace target | 10% of class (wk < K) |
| counterexample certification cap | 12 pairs |
| phi self-test | 500 states, exact |

The cost profile is asymmetric, and deliberately so. The empirical layer is O(|C|*d) hashing — seconds for every class in this study, including the 1.36M-state class — and it runs first because it is where most defects are caught. The symbolic layer's cost is dominated by bit-blasting the feature arithmetic and by the array construction: proof time grows with the axiomatised state count (1.7 s for 2,112 states to 22.8 s for 22,375), and the two full-class attempts that exhausted their budgets returned *unknown* rather than a wrong answer, which is the failure mode the tier system is designed to absorb.

**Figure 1.** The certification pipeline. The empirical layer is the fast refutation path; the symbolic layer certifies. Budgets are explicit, and the verdict records which tier was reached.

### 3.4 Why the empirical layer was not enough

The empirical layer of this protocol — bucket all states by feature vector and check that every bucket's value set is a singleton — is exactly the check the underlying pipeline had been running informally all along, and on the knight-free families it had always come back clean: the committed family builds report zero semantic conflicts on canonical rows, and the coordinate tail was never needed. The knight extension broke that record immediately, and it broke it on classes whose empirical behaviour looked benign at small scale (the K+N vs K+N classes have only 4-6 conflict buckets out of thousands of vectors). The lesson is not that the empirical layer is worthless — it catches the vast majority of defects and is the fast refutation path here — but that it cannot distinguish "the basis is sound" from "no counterexample happened to be enumerated yet", and it offers no help at all when the question becomes *which* feature is missing. The symbolic layer answers both: it turns "0 conflicts observed" into a proof where the basis is sound, and its counterexamples into a diagnosis where it is not.

## 4. v1 Refutation

### 4.1 The query is sat for every class

Basis v1 — the basis of every committed compression run of the underlying pipeline — consists of 5 king features (tempo, king distance, opposition orientation, edge distances) and 13 knight features (counts, distances, attack/check and capture relations), extended by 14 pawn features on pawn classes: 18 features on knight-only classes, 32 on pawn classes. The query is SAT on all seven classes: 4 to 17,892 conflict buckets per class (Table 3). Every published bucket pair was re-verified symbolically; the counterexamples are not empirical accidents but certified members of the class. The symbolic re-verification matters because the buckets are found by Python hashing: a bucketing bug would produce phantom pairs, and re-encoding both states from scratch in Z3 — legality, features, and values independent of the bucketing code — rules that out before the refutation is published.

**Table 3. v1 refutation per class** (MEASURED; z3_injectivity.json). States = legal class states; conflicts = feature-equal buckets with differing oracle values; certified = machine-checked counterexample pairs; phi-distinct = distinct feature vectors.

| class | N | states | phi-distinct | conflicts | certified |
|---|---|---|---|---|---|
| kn | 3 | 2,112 | 290 | 4 | 4 |
| kn | 4 | 46,384 | 6,328 | 6 | 6 |
| kn | 5 | 391,072 | 55,312 | 6 | 6 |
| kpn | 4 | 25,178 | 5,469 | 518 | 12 |
| kpn | 5 | 249,728 | 39,307 | 4,004 | 12 |
| mirror | 4 | 136,068 | 43,489 | 2,946 | — |
| both | 4 | 1,358,808 | 568,978 | 17,892 | 12 |

### 4.2 Counterexample anatomy

Three mechanisms account for all certified counterexamples.

**(1) Knight-square ambiguity** (dominant): positions differing only in the knight's exact square can share every distance feature — Chebyshev norms deliberately discard direction — yet differ in mate-net geometry, and hence in value. Fig. 2 decodes one certified pair from the K+N vs K+N, N=4 class: with white king a1, white knight a2 and black king c2, the black knight on d2 yields a mover win, the black knight on d3 a draw; all 18 v1 features are identical (the pair shares a bucket of size 28). The mate that works through d2 fails through d3 because the *direction* of the knight's relation to both kings changes while every symmetric distance stays put.

**(2) Rank-translation ambiguity**: whole positions shifted along the rank axis preserve every signed relative geometry — signed deltas are translation-invariant too — but edge-dependent mates depend on the absolute rank band; only an edge-distance feature can pin it. The certified pair [0,6,-1,-1,4,2,1] (mover wins) versus [4,10,-1,-1,8,14,1] (draw), bucket size 12, is this mechanism made concrete: the entire position (white king a1, black king c2, white knight a2, black knight c1) is translated one rank away from the bottom edge (to a2, c3, a3, c4), every relative feature including the knight-to-king Chebyshev distance (2) is unchanged, and the value flips from win to draw because the mating geometry that depends on the rank-1 edge has been destroyed.

**(3) Pawn-geometry ambiguity** (pawn classes): pawn placements at the same distances from both kings and the knight but on different files carry different promotion races and capture geometries. These mechanisms are not independent pathologies: they all instantiate the same principle — a basis of undirected and translation-invariant features cannot distinguish configurations that differ only in orientation or edge proximity, exactly the configurations chess endgames care about.

**Figure 2.** A certified v1 counterexample pair (K+N vs K+N, N=4; states [wk,bk,wp,bp,nw,nb,stm], squares indexed x+y*4): s1 = [0,6,-1,-1,4,7,1] (knight d2), mover-relative VAL = 1 (mover wins); s2 = [0,6,-1,-1,4,11,1] (knight d3), VAL = 3 (draw). All 18 v1 features are equal (bucket size 28); the difference is pure mate-net geometry.
## 5. v2 Fix

### 5.1 Signed knight offsets, rank-edge distances, pawn offsets

The mechanisms of Sec. 4 dictate the repair. Against knight-square ambiguity, the basis needs the knight's *direction*, not just its distance: basis v2 adds eight signed per-axis offsets, four per colour (k_dx_w, k_dy_w: white knight to white king; k_dxe_w, k_dye_w: white knight to black king; and the black counterparts), each defined as the signed per-axis delta king - piece with sentinel -1,-1 when the piece is absent. Against rank-translation ambiguity, the basis needs an absolute-rank anchor: v2 adds two king rank-edge distances re_w, re_b = min(y, N-1-y). Against pawn-geometry ambiguity, v2 adds eight signed pawn offsets (pawn to own king, pawn to enemy king, per axis). The result is 28 features on knight-only classes and 50 on pawn classes (Table 4). The v1 API of the underlying basis module is unchanged, so every previously committed compression run remains reproducible; the v2 features are an addition, tested by the same certification protocol.

### 5.2 Minimality ladder

Signed knight offsets alone were the *naive* fix hypothesis, and the ladder refutes it: subsets {A}, {B}, and {A,B} (own, enemy, both signed knight-offset families) close *no* class — they leave 4 to 16 conflict buckets on the knight classes and 441 to 8,192 on the pawn classes (Table 5). The certified closure combinations are: knight-only classes close with one signed family *plus* the rank-edge pair ({A,C} = {B,C} = 0 at every N; {A,B} without C keeps 8 buckets, so C is required there); pawn classes close with both signed knight families plus signed pawn offsets ({A,B,D} = {A,B,E} = 0), where the rank-edge pair is redundant. An opponent-orientation split O (same-file vs. same-rank alignment) changes nothing on any class and was dropped. The shipped v2 basis {A,B,C,D,E} is therefore mildly overdetermined by design — one class-independent definition rather than per-class minimality — which is a deliberate trade: a single basis across classes keeps the pipeline uniform, at the cost of two redundant feature families per class type.

**Table 4. The 28 v2 features on knight-only classes** (the 50-feature pawn basis adds 14 pawn features and 8 signed pawn offsets; names are the pipeline's, from z3_injectivity_v2.json basis_v2).

| group (count) | features |
|---|---|
| tempo, king geometry (5) | tau, d_AK, opp, e_w, e_b |
| knight counts, distance (3) | nW, nB, k_dist |
| knight relations (8) | katt_w, katt_b, kchk_w, kchk_b, k_w_own, k_b_own, k_w_enemy, k_b_enemy |
| knight attacks (2) | k_atk_w, k_atk_b |
| signed offsets, own king (4) | k_dx_w, k_dy_w, k_dx_b, k_dy_b |
| signed offsets, enemy king (4) | k_dxe_w, k_dye_w, k_dxe_b, k_dye_b |
| rank-edge distances (2) | re_w, re_b |

**Table 5. Minimality ladder** (MEASURED; minimality_ladder in z3_injectivity_v2.json). Shorthand: kn = K+N vs K+N; kpn = K+P+N vs K; mirror = K+P vs K+P+N; both = K+P+N vs K+P+N. A = knight->own signed offsets; B = knight->enemy; C = king rank-edge distances; D = pawn->own signed offsets; E = pawn->enemy; O = opp-orientation split (redundant everywhere, dropped). Bold 0 = closed.

| class | v1 | A | B | AB | AB+C | AB+D | AB+E |
|---|---|---|---|---|---|---|---|
| kn, N=3 | 4 | 4 | 4 | 8 | **0** | — | — |
| kn, N=4 | 6 | 8 | 8 | 8 | **0** | — | — |
| kn, N=5 | 6 | 16 | 8 | 8 | **0** | — | — |
| kpn, N=4 | 518 | 774 | 538 | 441 | — | **0** | **0** |
| kpn, N=5 | 4,004 | 8,192 | 6,305 | 6,932 | — | **0** | **0** |
| mirror, N=4 | 2,946 | 3,186 | 3,202 | 2,097 | — | **0** | **0** |
| both, N=4 | 17,892 | 7,674 | 8,054 | 7,400 | — | **0** | **0** |

### 5.3 Result: all classes close

Under basis v2 the query is UNSAT on all seven classes: zero conflict buckets, with the empirical layer simultaneously perfect or near-perfect (the knight classes retain a largest bucket of 2: 96 class states at N=4 and 576 at N=5 share a feature vector with exactly one other state, and the oracle evaluates both identically; the pawn classes reach exact injectivity on the two largest classes, 1,358,808 states mapping to 1,358,808 distinct vectors). Table 6 gives the aggregate; Table 7 gives the per-class proof tier and timing. The proof tiers differ for budget reasons only (Sec. 7); the empirical layer is clean on the full class in every case.

Two scope notes keep this result honest. First, the near-buckets on the knight classes mean v2 is value-sufficient but not perfectly injective as a map: two states may still share a feature vector, but when they do, they agree in value, which is exactly the property compilation needs. Second, the compression runs of the underlying study were compiled with the v1 basis plus the conditional coordinate tail, which discharges every conflict exactly (all class verifications pass with zero mismatches); compression has *not* been re-run under the v2 basis, so "v2 would allow tail-free semantic compilation on these classes" is a supported expectation, not a measured result. The certification and the compression measurements are kept strictly separate throughout.

**Table 6. v2 closure per class** (MEASURED): conflict buckets drop to zero everywhere. Distinct = distinct feature vectors over the full class; max bucket = largest feature-equal group.

| class | distinct | max bucket | conflicts |
|---|---|---|---|
| kn, N=3 | 2,112 (= states) | 1 | **0** |
| kn, N=4 | 46,288 | 2 | **0** |
| kn, N=5 | 390,496 | 2 | **0** |
| kpn, N=4 | 25,146 | 2 | **0** |
| kpn, N=5 | 249,536 | 2 | **0** |
| mirror, N=4 | 136,068 (= states) | 1 | **0** |
| both, N=4 | 1,358,808 (= states) | 1 | **0** |

**Table 7. Z3 proof status and timing per class under basis v2** (MEASURED). status: PROVED (full-class unsat, 1.7 s over the two-state query); PROVED_ON_SUBSPACE (bounded-subspace unsat: white king square < K, covering the stated fraction; array sizes 3,640-22,375 states); EMPIRICAL_ONLY (array axiomatisation skipped above the 60,000-state cap). emp = empirical-layer bucketing time; total = full per-class run including the (aborted) full-class attempt where present. Z3 5.4.1.

| class | status | subspace | emp (s) | total (s) |
|---|---|---|---|---|
| kn, N=3 | PROVED | full class | 0.0 | 5.6 |
| kn, N=4 | PROVED_ON_SUBSPACE | wk<2; 14.2% | 0.03 | 271.8 |
| kn, N=5 | PROVED_ON_SUBSPACE | wk<1; 4.7% | 0.39 | 45.1 |
| kpn, N=4 | PROVED_ON_SUBSPACE | wk<2; 14.5% | 0.02 | 189.8 |
| kpn, N=5 | PROVED_ON_SUBSPACE | wk<2; 9.0% | 0.25 | 32.8 |
| mirror, N=4 | PROVED_ON_SUBSPACE | wk<2; 14.8% | 0.13 | 27.6 |
| both, N=4 | EMPIRICAL_ONLY | 10% sub > cap | 1.82 | 27.9 |

## 6. Mirror Symmetry Proof

### 6.1 Formal statement

The colour-swap mirror V' reflects the board along the horizontal axis (x, y -> x, N-1-y), swaps colours of every piece and the side to move, and maps mover-relative values to themselves. The mirror-symmetry claim about the basis is: for every legal mirror-class state s (the asymmetric class K+P vs K+P+N), phi(V'(s)) = swap_wb(phi(s)), where swap_wb exchanges every white/black feature component and maps tempo tau -> 1 - tau. The sign conventions matter: the *signed file* deltas are invariant under the swap (both the axis and the colour exchange flip twice), while the *signed rank* deltas are anti-invariant — V' maps k_dy_w(s) -> -k_dy_b(s) — and the negation must not corrupt the absence sentinel, so the swap table carries a piece-presence guard (-1 stays -1).

### 6.2 The proof

The claim is checked VAL-free: one symbolic state, legality, phi of the image versus the swapped phi of the source, and the difference query (any component of phi(V'(s)) differing from swap_wb(phi(s))). The swap table has three modes per feature component: *identity* for colour-paired features that swap directly (material counts, file deltas, edge distances, relations), *flip* for the tempo (tau -> 1 - tau), and *negate-under-guard* for the signed rank deltas, where the negation is applied only when the piece owning the target feature is present, so the absence sentinel -1 passes through unchanged. Z3 returns UNSAT in 0.25 s (v2 basis; the v1 basis also proved symmetric, in 0.17 s), so the basis repair preserved colour symmetry. The same query doubles as an implementation audit: a SAT result would mean the feature map or the swap table is asymmetric — an encoding bug — and the verdict would be recorded as such rather than as a property of the basis.

### 6.3 Cross-oracle validation

Symbolic symmetry of phi does not by itself imply the *values* are mirror-symmetric; that depends on the ruleset. The ruleset is, so the oracle's mover-relative value must be preserved under V' across *independently solved* closures: the mirror class's V'-images have material K+P+N vs K+P, which lives in the balanced class closure, not in either single-side closure. Accordingly, all 136,068 states of the mirror class were mapped through V' and their values checked against the independently solved K+P+N vs K+P+N oracle: 136,068 agreements, 0 mismatches, with the additional structural assertion that every V'-image exists in the balanced closure. Together, the symbolic proof and the cross-oracle check close the loop between the basis, the encoding, and two independent solver runs.

## 7. Limitations

### 7.1 Subspace proofs vs. full proofs

Five of the seven verdicts are bounded-subspace proofs: the array axiomatisation covers 4.7-14.8% of the class (white king restricted to the lowest ranks), selected to fit the 60,000-state cap. The subspace is chosen for budget reasons, not because the remaining region is known to be harder; the empirical layer (zero conflicts over all states) is the only evidence covering the rest of each class. A machine with more memory, or an incremental array axiomatisation, would shrink this gap; nothing in the method depends on the cap.

### 7.2 Empirical-only classes above the array cap

The largest class (1,358,808 states; its 10% subspace already exceeds the cap) carries EMPIRICAL_ONLY: zero conflicts over the full class is strong evidence of value-sufficiency — and the class reaches exact injectivity — but it is not a proof. This is reported as its own tier, not folded into the proved ones.

### 7.3 Adequacy, not optimality; encoding, not solver

The certificate establishes that the basis is *sufficient* for correct tail-free compilation. It says nothing about whether a smaller or different basis exists (the minimality ladder is measured, not proved minimal), and nothing about compression ratios: a perfectly value-sufficient basis can still compile to a large MTBDD, and the underlying scaling study measures that separately. Nor does the certificate verify the retrograde oracle itself — the oracle is trusted input, validated by its own self-tests and cross-checks; formalizing the recursion (e.g. in Lean) is future work. A Lean development would add two things this certificate cannot: an inductive proof that the retrograde fixpoint computes the game value, and a proof that the symbolic legality predicate is equivalent to a written specification of the ruleset, closing the gap that the protocol currently guards only by consistency checks.

### 7.4 Threats to validity

Three threats are worth naming explicitly. First, the legality predicate is a hand-written characterisation of the ruleset; if it admitted states the Python solver excludes, the query could in principle return SAT on pairs the empirical layer never sees — which is precisely the SAT-unexpected alarm the protocol raises, and none fired here. If it excluded legal states, the proofs would be over a narrower domain than claimed; the 500-state exact self-tests and the empirical layer's full coverage make this unlikely but do not eliminate it formally. Second, the subspace choice (wk < K, the lowest ranks) is a budget artifact; those states concentrate near the board edge where mating structure is densest, so the subspace proofs plausibly cover the *harder* geometry, but that is a plausibility argument, not a proof — the tier labels report exactly what was proved. Third, everything here is certified for one ruleset family (a controlled pawn/knight simplification of chess) and its class partition; conclusions transfer to other games only as a protocol, not as a theorem.

## 8. Related Work

Retrograde analysis and endgame databases established exact game solving on state spaces far beyond search's reach (Thompson 1986; Nalimov et al. 2000), and the solved-game tradition documents both the power and the cost of exact knowledge (Allis 1994; Schaeffer et al. 2007; van den Herik et al. 2002). Decision diagrams provide the compression substrate: BDDs (Bryant 1986, 1992), algebraic and multi-terminal variants (Bahar et al. 1997; Fujita et al. 1997), and symbolic model checking that scaled verification to astronomical state counts (Burch et al. 1992). SMT solving and its certificates are the verification substrate: Z3 (de Moura and Bjorner 2008, 2011; Programming Z3), the SMT-LIB standard (Barrett et al. 2017), and the SAT/SMT tradition of encoding combinatorial problems and extracting models as witnesses (Cook 1971; Kautz and Selman 1996; Biere et al. 2009). The protocol here borrows the refutation-first posture of that tradition: try to break the claim, extract witnesses, and only then prove. Its honesty requirements — separating proved, subspace-proved, and empirically-supported verdicts — follow the discipline of verified-systems engineering, where a certificate is only as good as the statement of what it covers (Leroy 2009; Klein et al. 2014). What the case study adds to that tradition is the pairing with a compression pipeline: the certificate is not an end in itself but a gate that decides when a feature-based value compiler may replace states by feature vectors, and its counterexamples double as feature-engineering requirements. To our knowledge, symbolic feature-adequacy certification of this form — value-sufficiency of a semantic feature basis over an exactly solved game class, with budgeted proof tiers — has not previously been documented for endgame compilation pipelines; endgame database work traditionally validates by exhaustive evaluation against the oracle, which verifies correctness but neither diagnoses failures nor guides repairs. The certificate complements the diagram tradition on its own terms: BDD packages succeed or fail on variable orderings and feature choices that are usually justified informally (CUDD), and here that justification is replaced by a machine-checked one.

## 9. Conclusion

Feature-basis adequacy is the silent assumption under every feature-based compression of game value functions; this case study makes it explicit, cheap to test, and machine-checked. On a seven-class chess-fragment family, the v1 basis failed everywhere — with three certified ambiguity mechanisms that are informative about the domain (mate-net geometry, edge dependence, pawn files) — and the v2 basis, repaired with signed offsets and edge distances, closed every class: one full proof, five subspace proofs, one perfect empirical layer, plus a VAL-free mirror proof and 136,068 cross-oracle agreements. The methodological lesson generalizes beyond chess: an adequacy certificate of this shape costs minutes, refutes or proves before measurement is trusted, and records exactly which tier of evidence each claim carries. What it does not do — prove minimality, predict ratios, or verify the oracle — is stated as plainly as what it does; that separation is the point.

## Appendix A. Reproducibility

The certification scripts ship unmodified in the companion repository (experiments/z3/): k2pn_basis.py (both feature APIs), z3_injectivity.py (the protocol of Sec. 3, with --basis v1|v2, --mode auto|full|subspace|empirical|mirror-proof), and the two minimality probes (probe_signed_fix.py, probe2_minimality.py). Inputs are the per-class oracle arrays (class_values.npz); outputs are the per-class JSONs committed under artifacts/z3_classes/, with Z3 5.4.1 recorded in every file. The recorded seven-class re-run in --mode auto --basis v2 totals ~10 minutes on a laptop-class sandbox, dominated by two full-class attempts that return unknown (240 s and 180 s); with --mode subspace, which skips those attempts, the same seven classes close in under three minutes. The smallest proof (K+N vs K+N, N=3) re-runs in ~1.7 s. The phi self-tests (500 states per class, exact) run by default on every invocation. The consolidated before/after record, including the minimality ladder, is artifacts/z3_injectivity_v2.json.

## References

Full numbered reference list in `paper/verification/main.pdf` / `refs.bib` (22 entries): de Moura & Bjorner 2008, 2011; Bjorner et al. (Programming Z3); Barrett, Fontaine & Tinelli (SMT-LIB 2.6); Biere et al. (Handbook of Satisfiability); Kautz & Selman 1996; Cook 1971; Bryant 1986, 1992; Bahar et al. 1997; Fujita, McGeer & Yang 1997; Burch et al. 1992; Leroy 2009; Klein et al. 2014; Allis 1994; Schaeffer et al. 2007; Thompson 1986; Nalimov, Haworth & Heinz 2000; van den Herik, Uiterwijk & van Rijswijck 2002; k2p-algebraic-closure (commit 76ba614); chess-compression-scaling (companion repo); Somenzi (CUDD).
