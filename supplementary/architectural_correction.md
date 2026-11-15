# Architectural correction: atlas closure at phase 7b

**What the frozen repo says.** The README of `k2p-algebraic-closure`
(commit 76ba614) describes a "two-tier hybrid: a piecewise algebraic atlas
that analytically explains 93.84% of the space, plus exact sub-game closure
compiled into a zero-lookup MTBDD decision circuit for the remaining
6.16%." Its metrics table lists "Tier-1 analytic coverage (Piecewise
Algebraic Atlas): 93.84% (145,354 states)".

**What that number actually is.** A phase-6c snapshot: a partial atlas over
145,354 of 154,888 states, with the not-yet-covered 9,534 states handled by
the MTBDD tier. It was the state of the build at the time the README was
written, not the architecture's end state.

**What happened next.** Phases 7a/7b repaired the remaining mandate:
`phase7b_results.json` records the v7a baseline atlas at 151,042 states,
plus 3,846 repaired states (mandate 1: 578; mandate 2: 3,268), reaching
full closure: `psi_v7b_global = 154,888` at accuracy `1.0`, with `residual
= 0`, `residual_core = 0`, `residual_leftover = 0`.

**The correct framing.**

1. The atlas reaches exact closure at phase 7b. There is no permanent
   "MTBDD residual".
2. The MTBDD is a **parallel zero-lookup compilation** of the same closed
   value function — an alternative representation of the same object the
   atlas explains, not a handler for what the atlas cannot explain.
3. "Zero-lookup, no search" describes the **evaluation path** only. The
   construction path enumerates states and runs retrograde search. Both
   statements are true and must be stated together.

**Consequences.** None of the measurements change: the compression numbers,
verifications, and diagnostics are unaffected. What changes is the story:
the compiler's correctness does not rest on a division of labour between
an analytic tier and a compiled tier; the whole value function is closed
before compilation begins, and the MTBDD reproduces it exactly (0
mismatches on every exhaustive verification).

**Where this is stated.** Paper 1 Sec. 2.2; README ("Architectural
correction"); HONESTY.md Sec. 3. The frozen repository itself is left
untouched at commit 76ba614; this correction lives here, next to the
evidence (`artifacts/e_diagnostics/phase7b_results.json`).
