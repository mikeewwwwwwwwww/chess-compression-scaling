# experiments/ — the exact code that produced the published numbers

Every script here is a byte-identical copy (`cp -p`, preserving modes) of
the working-tree scripts that produced the committed artifacts; the frozen
source repository (`k2p-algebraic-closure`, commit `76ba614`) is untouched.
The only environment difference from the original layout: the scripts were
siblings in one flat directory and import `k2pn_basis` as a sibling, so run
them with:

```bash
export PYTHONPATH=experiments/z3
```

## Subdirectories

| directory | script | what it does |
|---|---|---|
| `oracle/` | `phase1_solver_general.py` | N-parameterized retrograde oracle (VAL + DTC) for the knight-free K2P families; `--n {3,4,5}`, self-tests included |
| `compressor/` | `compress_family_general.py` | family MTBDD compiler: orbit quotient -> semantic features -> ordered MTBDD -> conditional tail -> emitted integer evaluator -> exhaustive verify; `--family duel\|asym_3p\|four_pawn\|all\|full` |
| `class/` | `k2pn_classes.py` | class retrograde oracle for K2P+N material classes (repo ruleset D1-D4 + knight generalisations R1/R2; five self-tests incl. exact knight-free cross-check vs the phase-1 npz) |
| `class/` | `compress_class_k2pn.py` | the same compiler pipeline for one material class |
| `z3/` | `k2pn_basis.py` | feature basis module, v1 API (unchanged) + v2 API (class_features_v2: signed offsets, rank-edge, pawn offsets) |
| `z3/` | `z3_injectivity.py` | the Z3 adequacy certification protocol (empirical -> certify conflicts -> full/subspace proof -> mirror-proof mode) |
| `z3/` | `probe_signed_fix.py`, `probe2_minimality.py` | minimality-ladder probes (empirical bucketing over full classes) |
| `verify_gate.py` | (this directory) | assertions for the self-contained CI gate |

Known environment caveat (documented, not patched): the family compressor's
N=4 inputs (frozen-repo per-family npz masks) resolve via an absolute path
from the authoring sandbox; see REPRODUCE.md Sec. 2 and pass
`--labels-npz` explicitly on other machines.
