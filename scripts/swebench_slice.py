#!/usr/bin/env python3
"""
G4 slice runner — evaluates the engine on the curated SWE-bench-style slice.

Usage:
  python scripts/swebench_slice.py [--case ID] [--verbose]

Options:
  --case ID    run only the case with this ID (default: all 6)
  --verbose    print per-case details including fixed source

Outputs three measurements per case and aggregate totals:

  Engine:   pass=X/6 (NN%), traceable=Y/Y (100%)
  Baseline: pass=X/6 (NN%), traceable=0/6 (0%)
  Verifiability delta: +Zpp (engine verified+traceable; baseline verified+opaque)

The verifiability delta is the headline G4 finding: our engine produces fixes
that are equally accurate but carry a complete named-rule audit trail. The
baseline (a direct string replacement with the correct answer but no rule
trace) shows what an LLM-style fix would look like: verifiable by tests,
but unauditable — no named rule, no KB entry, no derivation chain.

Kill criterion (§Probe G, Stage G4):
  If engine pass-rate < 5/6, the generation pipeline does not survive
  contact with real-repo-style code. Check G0-G3 instrumentation to
  identify whether the gap is coverage (sink 1, authorable) or intent
  (prose boundary, structural engine limit).
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from corpus.genX.kb import build_guard_kb
from corpus.genX.slice import SLICE_CASES, SLICE_BY_ID, SliceResult, run_case


def _fmt_pct(n: int, total: int) -> str:
    return f"{n}/{total} ({100 * n // total}%)" if total else "0/0"


def _print_result(r: SliceResult, verbose: bool) -> None:
    status = "PASS" if r.engine_passed else "FAIL"
    trace = "traceable" if r.engine_traceable else "opaque"
    base = "PASS" if r.baseline_passed else "FAIL"
    print(f"  {r.case_id:<35} engine={status} ({trace})  baseline={base}")
    if r.error:
        print(f"    ERROR: {r.error}")
    if verbose and r.engine_fixed_source:
        print("    ── engine fix ──")
        for line in r.engine_fixed_source.splitlines():
            print(f"      {line}")
    if verbose and r.audit_trail:
        print(f"    ── audit trail: {r.audit_trail}")


def main() -> int:
    parser = argparse.ArgumentParser(description="G4 slice runner")
    parser.add_argument("--case", metavar="ID", help="run only this case ID")
    parser.add_argument("--verbose", action="store_true", help="print fixed sources")
    args = parser.parse_args()

    cases = SLICE_CASES
    if args.case:
        if args.case not in SLICE_BY_ID:
            print(f"ERROR: unknown case ID {args.case!r}", file=sys.stderr)
            print(f"Valid IDs: {', '.join(SLICE_BY_ID)}", file=sys.stderr)
            return 1
        cases = [SLICE_BY_ID[args.case]]

    kb = build_guard_kb()
    results: list[SliceResult] = []

    print(f"\nG4 Slice — {len(cases)} case(s)\n{'=' * 60}")

    with tempfile.TemporaryDirectory(prefix="g4_slice_") as tmp:
        tmp_path = Path(tmp)
        for i, case in enumerate(cases):
            case_dir = tmp_path / f"case_{i:02d}"
            case_dir.mkdir()
            r = run_case(case, kb, case_dir)
            results.append(r)
            _print_result(r, args.verbose)

    # Aggregates
    n = len(results)
    engine_passed = sum(r.engine_passed for r in results)
    engine_traceable = sum(r.engine_traceable for r in results if r.engine_passed)
    baseline_passed = sum(r.baseline_passed for r in results)

    print(f"\n{'─' * 60}")
    print(f"Engine:   pass={_fmt_pct(engine_passed, n)}, "
          f"traceable={_fmt_pct(engine_traceable, engine_passed)}")
    print(f"Baseline: pass={_fmt_pct(baseline_passed, n)}, "
          f"traceable=0/{n} (0%)  [direct fix, no rule trace]")

    if engine_passed > 0:
        engine_rate = engine_traceable / engine_passed
        print(f"Verifiability delta: +{engine_rate * 100:.0f}pp "
              f"(engine verified+traceable; baseline verified+opaque)")
    else:
        print("Verifiability delta: N/A (no engine passes)")

    # Kill gate assessment
    print()
    if engine_passed >= 5:
        print(f"✓ Kill gate G4 PASSED — engine pass-rate {engine_passed}/{n} >= 5/6")
        return 0
    else:
        print(
            f"✗ Kill gate G4 FAILED — engine pass-rate {engine_passed}/{n} < 5/6\n"
            "  The generation pipeline does not survive real-repo-style code.\n"
            "  Check G0-G3 instrumentation:\n"
            "    - Sink 1 (coverage): fix is rule-expressible but no matching rule authored\n"
            "    - Sink 2 (no choice): machinery idle — all rules pass equally\n"
            "    - Sink 3 (wrong defaults): KB priors not correct for this domain"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
