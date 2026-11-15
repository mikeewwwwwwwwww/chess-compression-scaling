# chess-compression-scaling

A scaling study of chess value-function compression, with an architectural
correction to the K2P-4x4 solver and a symbolic-verification methodology.

## TL;DR

- We port the K2P-4x4 zero-lookup MTBDD compressor to N-parameterized form
  (N=3,4,5) and to knight-bearing material (K2P+N), solving everything
  exactly by retrograde analysis.
- **Board size helps**: routed compression improves 1:31.7 (N=4) -> 1:79.7
  (N=5); the unified N=5 build reaches 1:86.1. Node growth is sub-linear
  (states^0.775, pooled log-log OLS).
- **Material balance hurts**: one added knight per side at fixed balance
  degrades the ratio 1.57x (1:29.1 -> 1:18.6); unbalanced material degrades
  it 3.35x (1:36.3 -> 1:10.8). We originally read this as a piece-count
  effect; the data support *material balance* as the operative variable.
- Z3 certifies feature-basis adequacy on all 7 classes after a
  signed-offset repair (v1 refuted with concrete counterexamples; v2
  closed; mirror symmetry proved, unsat in 0.25 s; 136,068 cross-oracle
  agreements).
- This is a measurement study, not a solver. We do NOT claim progress on
  full chess.

## Metrics

| Metric | Value | Source |
|---|---|---|
| N=4 routed compression | 1:31.7 (4,885 nodes / 154,888 states) | artifacts/compression_summary.json |
| N=5 routed compression (like-for-like) | 1:79.7 (84,618 / 6,744,724) | artifacts/compression_summary.json (per-family nodes summed) |
| N=5 unified compression | 1:86.1 (78,305 / 6,744,724) | artifacts/compression_summary.json |
| Node growth exponent | ~0.775 (pooled OLS; 0.745-0.763 per family) | derived in scripts/build_facts.py |
| K2P+N symmetric degradation | 1.57x (1:29.1 -> 1:18.6) | artifacts/class_compression/ |
| K2P+N asymmetric degradation | 3.35x (1:36.3 -> 1:10.8) | artifacts/class_compression/ |
| N=5 verification | exhaustive: 6,744,724 states, 0 mismatches | artifacts/e_diagnostics/track_a_verify.json |
| Z3 v2 basis | closes all 7 classes (0 conflicts) | artifacts/z3_injectivity_v2.json |
| Emitted evaluator speed | 4.73 us/state vs 3.05 dict (four_pawn, routed) — SLOWER; verifiability, not speed, is the contribution | k2p-algebraic-closure@76ba614 README |

All numbers are tiered and traceable in [FACTS.md](FACTS.md): every claim
resolves to a JSON file and a key path (88 claims: 80 MEASURED, 2
EXTRAPOLATED, 2 LOST, 4 OPEN). FACTS.md is generated, not hand-typed:
`python scripts/build_facts.py` rebuilds it from `artifacts/`.

## Architectural correction (to the K2P-4x4 artifact)

The original K2P repo framed the architecture as "93.84% analytic atlas +
6.16% MTBDD residual." That was a phase-6c snapshot. The atlas reached full
closure (residual = 0, accuracy 1.0 over all 154,888 states) at phase 7b.
The correct framing is: **the atlas reaches exact closure; the MTBDD is a
parallel zero-lookup compilation of the same closed value function.** The
construction path uses enumeration and retrograde search; the evaluation
path does not. This is documented in Paper 1 Sec. 2 and in
[supplementary/architectural_correction.md](supplementary/architectural_correction.md).

Also stated up front rather than buried: **the emitted evaluator is SLOWER
than a dictionary lookup** (4.73 vs 3.05 us/state on four_pawn routed).
We accept this because the goal is verifiability — a pure-integer evaluator
auditable branch-by-branch against an exact oracle — not speed.

## Architecture

```
+---------------------------------------------------------------+
|  K2P-4x4 ARTIFACT (this repo studies it; frozen at 76ba614)   |
|  Atlas closure at phase 7b (residual = 0)                     |
|  4,885-node routed MTBDD, 154,888 states                      |
+---------------------------+-----------------------------------+
                            |
                            v
+---------------------------------------------------------------+
|  N-PARAMETERIZED EXTENSION                                    |
|  Oracle: retrograde VAL/DTC for N=3,4,5 (0.2s / 2.0s / 110.5s)|
|  Compressor: orbit quotient -> semantic MTBDD -> tail         |
|  -> emitted integer evaluator -> exhaustive verify            |
+---------------------------+-----------------------------------+
                            |
                            v
+---------------------------------------------------------------+
|  BALANCE EXPERIMENTS (K2P+N, one knight per side)             |
|  7 material-class runs, exact, each verified 0-mismatch       |
|  1.57x (balanced) / 3.35x (unbalanced) degradation            |
+---------------------------+-----------------------------------+
                            |
                            v
+---------------------------------------------------------------+
|  Z3 CERTIFICATION                                             |
|  v1 refuted on all 7 classes (certified counterexamples)      |
|  v2 closes all 7; mirror proof unsat 0.25s;                   |
|  136,068 cross-oracle agreements                              |
+---------------------------------------------------------------+
```

## Honest limitations

- The emitted evaluator is slower than a dict lookup (4.73 vs 3.05
  us/state, four_pawn routed). This is a verifiability contribution, not a
  performance one.
- The full K2P+N 4x4 ratio (~1:20-25) is extrapolated from class data,
  not measured (the 17M-state, ~6 GB build was deliberately not run).
- The N=4-vs-N=5 ratio comparison must be routed-to-routed (1:31.7 ->
  1:79.7); the unified 1:86.1 exists only at N=5 and is never quoted as the
  same methodology's improvement.
- Knight-only K2P+N classes are structurally trivial (max DTC = 1) and are
  excluded from degradation claims.
- Five of seven Z3 verdicts are bounded-subspace proofs and one is
  empirical-only (array axiomatisation capped at 60,000 states); the tier
  of every proof is reported.
- The phase-level timing split (E5) and the tuning result tables
  (Tracks A-D) were lost in a sandbox outage and are reported as LOST,
  not reconstructed.
- No formal verification (Lean) of the retrograde recursion.
- No claim to solve chess; the initial position is at the balance extreme
  where compression is expected to fail.
- K2P+N asymmetric classes are not directly comparable to K2P baselines
  (material differs); the symmetric comparison is the clean one.
- Tuning levers (variable ordering, feature elimination) were explored in
  the underlying project; their result tables were lost, so only the
  charter's qualitative conclusions are cited (see FACTS.md rows T1-T3).

## Repository layout

```
README.md, FACTS.md, HONESTY.md, ARCHITECTURE.md, REPRODUCE.md
CITATION.cff, LICENSE, requirements.txt, .github/workflows/verify.yml
paper/scaling/         Paper 1: two-axis scaling (main.tex/pdf, paper.md, refs.bib, figures/)
paper/verification/    Paper 2: Z3 adequacy certification (same layout)
artifacts/             All measurement JSONs + provenance README
  scaling_summary.json, compression_summary.json, diagnostics_summary.json,
  z3_injectivity_v2.json, oracle_runs/, e_diagnostics/, z3_classes/, class_compression/
data/                  .npz oracle arrays (not tracked; see data/README.md)
experiments/
  oracle/              phase1_solver_general.py (N-parameterized retrograde oracle)
  compressor/          compress_family_general.py (family MTBDD compiler)
  class/               k2pn_classes.py, compress_class_k2pn.py (class oracle + compiler)
  z3/                  k2pn_basis.py, z3_injectivity.py, probe_signed_fix.py, probe2_minimality.py
  verify_gate.py       self-contained CI gate assertions
scripts/               build_facts.py (regenerates FACTS.md from artifacts/)
supplementary/         architectural correction, E1-E6 diagnostics, balance law, AI analyses
```

All scripts under `experiments/` are byte-identical copies of the code that
produced the published numbers (copied with `cp -p` from the working tree;
the frozen source repo is untouched at commit `76ba614`). Run them with
`PYTHONPATH=experiments/z3` — see REPRODUCE.md for the exact invocations.

## Quick start

```bash
git clone https://github.com/mikeewwwwwwwwww/chess-compression-scaling
cd chess-compression-scaling
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Self-contained reproduction gate (~10 s): oracle N=3/4, smallest class
# pipeline end-to-end, smallest Z3 proof, asserted against published values.
# (CI runs exactly this; see .github/workflows/verify.yml)
export PYTHONPATH=experiments/z3
python experiments/oracle/phase1_solver_general.py --n 3 --out-dir run/out_n3
python experiments/oracle/phase1_solver_general.py --n 4 --out-dir run/out_n4
mkdir -p experiments/class/out_n3 && cp run/out_n3/phase1_values.npz experiments/class/out_n3/
python experiments/class/k2pn_classes.py --n 3 --class-name kn --out-dir run/out_class_kn_n3
python experiments/class/compress_class_k2pn.py --n 3 --class-name kn \
  --oracle-dir run/out_class_kn_n3 --out-dir run/compress_class_kn_n3 --emit-dir run/compress_class_kn_n3
python experiments/z3/z3_injectivity.py --n 3 --class-name kn --basis v2 --mode auto \
  --oracle-dir run/out_class_kn_n3 --out run/z3_kn_n3.json
python experiments/verify_gate.py --oracle-n4 run/out_n4/phase1_results.txt \
  --oracle-n3 run/out_n3/phase1_results.txt \
  --class-json run/compress_class_kn_n3/compression_results.json \
  --z3-json run/z3_kn_n3.json
# -> ALL GATES PASS

# FACTS.md is regenerable from the committed artifacts:
python scripts/build_facts.py
```

The full family-level trust gate (compress all three N=4 families and
assert the routed total of 4,885 nodes) requires the frozen K2P artifact
arrays and the original directory layout; see REPRODUCE.md.

## Papers

- **Paper 1 (scaling):** [paper/scaling/main.pdf](paper/scaling/main.pdf)
  — "Two-Axis Scaling of Chess Value Function Compression: Board Size
  Helps, Balance Hurts" (IEEE conference format, 8 pp.) — markdown mirror
  at [paper/scaling/paper.md](paper/scaling/paper.md).
- **Paper 2 (certification):**
  [paper/verification/main.pdf](paper/verification/main.pdf) — "Symbolic
  Feature-Basis Adequacy Certification for Game Value Compression: A Z3
  Case Study" (IEEE conference format, 8 pp.) — markdown mirror at
  [paper/verification/paper.md](paper/verification/paper.md).

## Citation

```bibtex
@misc{mikeewwwwwwwwww2026scaling,
  author       = {mikeewwwwwwwwww},
  title        = {Two-Axis Scaling of Chess Value Function Compression:
                  Board Size Helps, Balance Hurts},
  year         = {2026},
  howpublished = {\url{https://github.com/mikeewwwwwwwwww/chess-compression-scaling}},
  note         = {Independent research; two-paper repository with full
                  measurement artifacts}
}
```

See also [CITATION.cff](CITATION.cff).
