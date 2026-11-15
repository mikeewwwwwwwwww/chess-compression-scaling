#!/usr/bin/env python3
"""Self-contained verification gate for chess-compression-scaling.

Asserts the exact values that anchor the repository's claims, from freshly
generated run outputs (see .github/workflows/verify.yml and REPRODUCE.md):

  1. oracle N=4: legal states == 154,888, directed edges == 531,456
  2. class kn_n3 compression: 2,112 states, 47 MTBDD nodes, ratio 44.94,
     emitted-evaluator verification PASS with 0 mismatches
  3. Z3 kn_n3 basis v2: verdict PROVED, 0 conflict buckets

The family-level N=4 trust gate (routed total == 4,885 nodes) requires the
frozen K2P artifact arrays, which live in the frozen repository and are not
distributed here; it is documented in REPRODUCE.md and runs only where those
arrays are present. Run `python experiments/verify_gate.py --help` for the
arguments.
"""
import argparse, json, re, sys

def fail(msg):
    print(f"GATE FAIL: {msg}")
    sys.exit(1)

def parse_phase1(path):
    txt = open(path).read()
    m = re.search(r"legal states:\s*(\d+)\s+directed edges:\s*(\d+)", txt)
    if not m:
        fail(f"could not parse 'legal states / directed edges' from {path}")
    return int(m.group(1)), int(m.group(2))

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--oracle-n4", required=True, help="phase1_results.txt for N=4")
    ap.add_argument("--oracle-n3", default=None, help="phase1_results.txt for N=3")
    ap.add_argument("--class-json", required=True,
                    help="compression_results.json for class kn, N=3")
    ap.add_argument("--z3-json", default=None,
                    help="z3_injectivity v2 output for class kn, N=3")
    a = ap.parse_args()

    states, edges = parse_phase1(a.oracle_n4)
    if (states, edges) != (154888, 531456):
        fail(f"N=4 oracle produced states={states} edges={edges}, expected 154,888 / 531,456")
    print(f"gate 1 OK: N=4 oracle legal_states=154,888 directed_edges=531,456")

    if a.oracle_n3:
        s3, e3 = parse_phase1(a.oracle_n3)
        if (s3, e3) != (1032, 1332):
            fail(f"N=3 oracle produced states={s3} edges={e3}, expected 1,032 / 1,332")
        print(f"gate 1b OK: N=3 oracle legal_states=1,032 directed_edges=1,332")

    d = json.load(open(a.class_json))
    if d.get("class") != "kn" or d.get("n") != 3:
        fail(f"class json is not kn/N=3: {a.class_json}")
    if d.get("states") != 2112:
        fail(f"kn_n3 states={d.get('states')}, expected 2,112")
    if d.get("mtbdd", {}).get("nodes") != 47:
        fail(f"kn_n3 MTBDD nodes={d.get('mtbdd', {}).get('nodes')}, expected 47")
    if abs(d.get("ratio_states_per_node", 0) - 44.94) > 0.01:
        fail(f"kn_n3 ratio={d.get('ratio_states_per_node')}, expected 44.94")
    v = d.get("verification", {})
    if v.get("value_mismatches") != 0 or v.get("status") != "PASS":
        fail(f"kn_n3 verification not clean: {v}")
    print(f"gate 2 OK: kn_n3 class build = 47 nodes over 2,112 states (1:44.94), verify PASS 0 mismatches")

    if a.z3_json:
        z = json.load(open(a.z3_json))
        if z.get("verdict") != "PROVED":
            fail(f"z3 kn_n3 verdict={z.get('verdict')}, expected PROVED")
        if z.get("conflict_buckets") != 0:
            fail(f"z3 kn_n3 conflict_buckets={z.get('conflict_buckets')}, expected 0")
        if not z.get("z3_version"):
            fail("z3 json missing z3_version")
        print(f"gate 3 OK: Z3 v2 kn_n3 verdict=PROVED, 0 conflict buckets (z3 {z['z3_version']})")

    print("ALL GATES PASS")

if __name__ == "__main__":
    main()
