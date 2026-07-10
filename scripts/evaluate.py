"""
Evaluation runner.

Runs the @slow integration tests (real subprocess pytest runs, real file I/O)
and prints a structured score report.  Run explicitly - not part of the
default `pytest` suite.

Usage:
    python scripts/evaluate.py            # all probes
    python scripts/evaluate.py --probe s0 # single probe by tag
"""
from __future__ import annotations
import argparse
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).parent.parent
TESTS = ROOT / "tests"


# ---------------------------------------------------------------------------
# Probe registry - each entry maps a human label to a test file + optional
# subset pattern.  Order is chronological (matches probe sequence table).
# ---------------------------------------------------------------------------
@dataclass
class Probe:
    tag: str
    label: str
    file: str
    pattern: str | None = None   # passed to pytest -k


PROBES: list[Probe] = [
    Probe("m1",  "M1 - Dispatcher loop",       "test_dispatcher_loop.py"),
    Probe("m3",  "M3 - Fix application",        "test_fix_application.py"),
    Probe("p4",  "P4 - Cold-start loop",        "test_cold_start_loop.py"),
    Probe("p5",  "P5 - Zero-division loop",     "test_probe5.py",       pattern="slow"),
    Probe("p3",  "Third pattern loop",          "test_probe_third.py",  pattern="slow"),
    Probe("s0",  "S0 - Failed-fix recovery",    "test_s0_failed_fix.py"),
    Probe("s1",  "S1 - Recognizer in-loop",     "test_s1_recognizer.py", pattern="slow"),
    Probe("s2",  "S2 - Parameterised transforms","test_s2_transforms.py", pattern="slow"),
    Probe("s3",  "S3 - Tracer in-loop",         "test_s3_tracer.py",     pattern="slow"),
    Probe("s4",  "S4 - Daikon-lite in-loop",    "test_s4_daikon.py",     pattern="slow"),
    Probe("s6",  "S6 - Contract enactment",     "test_s6_contract.py",   pattern="slow"),
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
@dataclass
class ProbeResult:
    probe: Probe
    passed: int = 0
    failed: int = 0
    errors: int = 0
    elapsed: float = 0.0
    output: str = ""

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.errors

    @property
    def ok(self) -> bool:
        return self.failed == 0 and self.errors == 0 and self.passed > 0


def run_probe(probe: Probe) -> ProbeResult:
    result = ProbeResult(probe=probe)
    cmd = [
        sys.executable, "-m", "pytest",
        str(TESTS / probe.file),
        "-m", "slow",
        "-v", "--tb=short", "-p", "no:warnings",
    ]
    if probe.pattern:
        cmd += ["-k", probe.pattern]

    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    result.elapsed = time.perf_counter() - t0
    result.output = proc.stdout + proc.stderr

    # Parse summary line: "X passed, Y failed in ..."
    for line in result.output.splitlines():
        line = line.strip()
        if " passed" in line or " failed" in line or " error" in line:
            parts = line.split()
            for i, p in enumerate(parts):
                if p == "passed,":
                    result.passed = int(parts[i - 1])
                elif p == "passed":
                    result.passed = int(parts[i - 1])
                elif p in ("failed,", "failed"):
                    result.failed = int(parts[i - 1])
                elif p in ("error,", "errors", "errors,"):
                    result.errors = int(parts[i - 1])
    return result


def print_report(results: list[ProbeResult]) -> int:
    total_pass = sum(r.passed for r in results)
    total_fail = sum(r.failed + r.errors for r in results)
    total_tests = total_pass + total_fail
    elapsed_all = sum(r.elapsed for r in results)

    print()
    print("=" * 64)
    print("  EVALUATION REPORT")
    print("=" * 64)
    for r in results:
        status = "PASS" if r.ok else "FAIL"
        bar = f"{r.passed}/{r.total}" if r.total else "no tests"
        print(f"  [{status}] {r.probe.label:<38}  {bar:>8}  {r.elapsed:5.1f}s")
    print("-" * 64)
    print(f"  TOTAL: {total_pass}/{total_tests} tests passed  ({elapsed_all:.1f}s)")
    if total_fail == 0:
        print("  Score: ALL PROBES PASS")
    else:
        probes_pass = sum(1 for r in results if r.ok)
        print(f"  Score: {probes_pass}/{len(results)} probes pass")
    print("=" * 64)

    # Print verbose output for any failures
    for r in results:
        if not r.ok:
            print()
            print(f"--- {r.probe.label} output ---")
            print(r.output[-3000:])

    return 0 if total_fail == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Run slow integration probes.")
    parser.add_argument("--probe", metavar="TAG",
                        help="run only the probe with this tag (e.g. s0, p4)")
    parser.add_argument("--list", action="store_true",
                        help="list available probe tags and exit")
    args = parser.parse_args()

    if args.list:
        for p in PROBES:
            print(f"  {p.tag:<6}  {p.label}")
        return

    probes = PROBES
    if args.probe:
        probes = [p for p in PROBES if p.tag == args.probe]
        if not probes:
            print(f"Unknown probe tag: {args.probe!r}")
            print("Available:", ", ".join(p.tag for p in PROBES))
            sys.exit(1)

    print(f"Running {len(probes)} probe(s)...")
    results = []
    for probe in probes:
        print(f"  {probe.label}...", end="", flush=True)
        r = run_probe(probe)
        status = "ok" if r.ok else "FAILED"
        print(f" {status} ({r.elapsed:.1f}s)")
        results.append(r)

    sys.exit(print_report(results))


if __name__ == "__main__":
    main()
