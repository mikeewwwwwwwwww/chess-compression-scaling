# REPRODUCE.md

How to rebuild every published number in this repository from its code.
All commands were re-executed on 2026-11-15 in the authoring sandbox
(Python 3.12.16, NumPy 2.1.3, Z3 5.4.1, tectonic for the papers); the
self-contained gate passed end-to-end the same day.

## 0. Environment

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # numpy, z3-solver
export PYTHONPATH=experiments/z3         # the pipeline scripts import k2pn_basis from there
```

`PYTHONPATH` is needed because the scripts were siblings in the original
flat working directory; the copies here are byte-identical and were not
reorganised internally.

## 1. Oracles (exact retrograde solve)

```bash
python experiments/oracle/phase1_solver_general.py --n 3 --out-dir run/out_n3
python experiments/oracle/phase1_solver_general.py --n 4 --out-dir run/out_n4
python experiments/oracle/phase1_solver_general.py --n 5 --out-dir run/out_n5   # ~110 s, ~2.4 GB RSS
```

Expected (published) values, asserted by `experiments/verify_gate.py`:

| N | legal states | directed edges | wall (s) | max DTC | draws |
|---|---|---|---|---|---|
| 3 | 1,032 | 1,332 | 0.2 | 4 | 28.10% |
| 4 | 154,888 | 531,456 | 2.0 | 13 | 6.92% |
| 5 | 6,744,724 | 32,551,012 | 110.5 | 38 | 4.98% |

Trust gates inside the oracle: mirror symmetry, phi/mu/chi anti-symmetry,
K-vs-K draws (all self-tests print OK), and — for the N-parameterized
solver — a validation pass against the frozen artifact's N=4 arrays with
0 diffs on VAL/DTC/MIR/STMW/MAT.

## 2. Family compression at N=4 (the 4,885-node routed trust gate)

This reproduces the frozen artifact's routed total. **Important:** the
family compressor resolves its N=4 inputs (per-family masks/values) from
the frozen K2P artifact's npz files, which are NOT distributed in this
repository, and the committed script carries the authoring sandbox's
absolute path for them. On a machine with the frozen artifact
(`k2p-algebraic-closure`, commit 76ba614) checked out, either run from that
layout as originally done, or pass the arrays explicitly:

```bash
python experiments/compressor/compress_family_general.py --n 4 --family duel
python experiments/compressor/compress_family_general.py --n 4 --family asym_3p
python experiments/compressor/compress_family_general.py --n 4 --family four_pawn
python experiments/compressor/compress_family_general.py --n 4 --family all
```

Expected: duel 652 nodes / 16,920 states (1:26.0); asym_3p 2,050 / 74,340
(1:36.3); four_pawn 2,183 / 63,628 (1:29.1); routed total 4,885 over
154,888 states (1:31.7); emitted evaluators byte-identical to the frozen
repo's except one provenance header line each.

At N=5 the unified build exists and is reproduced by
`--n 5 --family full` (78,305 nodes / 6,744,724 states = 1:86.1;
~6 min build wall in the authoring sandbox) and the per-family builds by
`--n 5 --family duel|asym_3p|four_pawn` (3,917 / 23,034 / 57,667 nodes;
routed total 84,618 = 1:79.7). The N=5 exhaustive verification gate
(Track A re-run) evaluated all 6,744,724 states with 0 mismatches
(artifacts/e_diagnostics/track_a_verify.json).

## 3. K2P+N class experiments (7 runs)

Each class = a dedicated oracle + compression + emitted-evaluator
verification. The smallest one is the CI gate; all seven were run for the
published tables:

```bash
# example: the smallest class (K+N vs K+N, N=3) — CI runs exactly this
python experiments/class/k2pn_classes.py --n 3 --class-name kn --out-dir run/out_class_kn_n3
python experiments/class/compress_class_k2pn.py --n 3 --class-name kn \
  --oracle-dir run/out_class_kn_n3 --out-dir run/compress_class_kn_n3 --emit-dir run/compress_class_kn_n3
```

`k2pn_classes.py` runs five self-tests by default, including an exact
cross-check of every knight-free state against the phase-1 oracle npz
(put a copy at `experiments/class/out_n{N}/phase1_values.npz`, as the CI
does, or pass `--no-k2p-crosscheck` to skip).

Expected results (published; `artifacts/class_compression/*/compression_results.json`):

| class | N | states | nodes | ratio | verify |
|---|---|---|---|---|---|
| kn | 3 | 2,112 | 47 | 1:44.9 | PASS, 0 mism. |
| kn | 4 | 46,384 | 78 | 1:594.7 | PASS, 0 mism. |
| kn | 5 | 391,072 | 139 | 1:2,813.5 | PASS, 0 mism. |
| kpn | 4 | 25,178 | 2,324 | 1:10.8 | PASS, 0 mism. |
| kpn | 5 | 249,728 | 11,252 | 1:22.2 | PASS, 0 mism. |
| mirror | 4 | 136,068 | 15,628 | 1:8.7 | PASS, 0 mism. |
| both | 4 | 1,358,808 | 73,013 | 1:18.6 | PASS (in-proc), 0 mism. |

Class names: `kn` = K+N vs K+N; `kpn` = K+P+N vs K; `mirror` = K+P vs
K+P+N; `both` = K+P+N vs K+P+N. The class oracle's ruleset is the repo's
D1-D4 plus two knight-driven generalisations (R1/R2) documented in its
header.

## 4. Z3 certification

```bash
# refutation (basis v1): expect REFUTED with certified counterexamples
python experiments/z3/z3_injectivity.py --n 3 --class-name kn --basis v1 --mode auto \
  --oracle-dir run/out_class_kn_n3 --out run/z3_v1_kn_n3.json

# closure (basis v2): expect PROVED (kn N=3), ~2 s
python experiments/z3/z3_injectivity.py --n 3 --class-name kn --basis v2 --mode auto \
  --oracle-dir run/out_class_kn_n3 --out run/z3_kn_n3.json

# mirror proof (VAL-free colour symmetry) on the mirror class
python experiments/z3/z3_injectivity.py --n 4 --class-name mirror --basis v2 --mode mirror-proof \
  --oracle-dir run/out_class_mirror_n4 --out run/z3_mirror.json

# minimality probes (empirical bucketing over full classes)
python experiments/z3/probe_signed_fix.py --help
python experiments/z3/probe2_minimality.py --help
```

Protocol knobs and defaults: 300 s proof budgets, 60,000-state array
axiomatisation cap, 10% subspace target (white king on the lowest ranks),
12 certified counterexample pairs max, 500-state exact phi/enc self-tests.
Budgeted full-class attempts that exceed the cap return *unknown* and the
verdict falls through to subspace/empirical tiers — that is recorded
behaviour, not a failure.

Published outcomes: v1 refuted on all 7 classes (4 / 6 / 6 / 518 / 4,004 /
2,946 / 17,892 conflict buckets); v2 closes all 7 (0 buckets; 1 full proof,
5 subspace proofs, 1 empirical layer); mirror proof unsat 0.25 s; 136,068
cross-oracle agreements. Consolidated record:
`artifacts/z3_injectivity_v2.json`; per-class raw:
`artifacts/z3_classes/*/z3_injectivity{,_v2}.json`.

## 5. Self-contained gate (what CI runs)

```bash
# steps 1 (N=3,4), 3 (kn_n3), 4 (v2 kn_n3), then:
python experiments/verify_gate.py \
  --oracle-n4 run/out_n4/phase1_results.txt \
  --oracle-n3 run/out_n3/phase1_results.txt \
  --class-json run/compress_class_kn_n3/compression_results.json \
  --z3-json run/z3_kn_n3.json
# -> ALL GATES PASS
```

`.github/workflows/verify.yml` runs exactly this sequence on every push.

## 6. FACTS.md and the papers

```bash
python scripts/build_facts.py     # regenerates FACTS.md from artifacts/ (88 rows)
```

Papers compile with tectonic (auto-fetches IEEEtran):

```bash
cd paper/scaling && tectonic main.tex       # 8 pages
cd ../verification && tectonic main.tex     # 8 pages
```

`paper.md` in each directory is the markdown mirror (same sections, tables,
figure captions).

## 7. What cannot be reproduced from this repository alone

- The N=4 family trust gate needs the frozen artifact's npz arrays
  (Sec. 2) — by design, since it verifies the new code against the frozen
  artifact.
- The N=5 per-family/unified builds need ~2.4-3.4 GB RSS and take minutes;
  they are reproduced from the same scripts with `--n 5` (Sec. 2).
- The pre-outage tuning tables and the E5 phase timing split are LOST
  (see HONESTY.md Sec. 6); nothing here reconstructs them.
