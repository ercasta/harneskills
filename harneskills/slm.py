"""
SLM NL->CNL harness — the exact reward signal (docs/vision_agentic.md §9).

The final arc pillar puts a small model at the boundary translating fuzzy NL into CNL, with the
SUBSTRATE doing all reasoning. The whole fine-tuning plan hinges on one thing this module provides:
a FREE, EXACT, automatic grade for a candidate CNL string — because we OWN the parser. Feed the
model's output back through the parser and compare its FRAME GRAPH to the gold frame graph. This is
the reward for supervised eval, rejection sampling, and preference-pair construction — no human eval
loop, no separate metric to trust.

WHY FRAME-GRAPH MATCH, not parse-success or string similarity: the failure mode that matters is a
CONFIDENTLY-WRONG translation — syntactically valid CNL that parses cleanly into SOME legitimate
frame, just not the intended one ("alice is a person" for "alice is a customer"). Parse-success
passes it; string/embedding similarity likely passes it; only comparing the resulting frame graph to
gold catches it. It also scores the SLM's specific copy-through behavior (carry an unknown token
VERBATIM into the slot vs. "helpfully" normalizing it) — a normalized token lands a different frame.

SCOPE (this slice): the frame graph is the FACT-level denotation of the CNL (what parsing asserts),
which covers the templated fact/statement bulk of business-rule dictation. Grading rule-CNL needs a
behavioral probe (run the rule, compare derived facts) rather than this fact-set compare — a
documented extension, not built here. DEFERRED (needs a GPU/model, per §9): the NL side of the
training corpus (sample CNL from the grammar, back-translate to NL with a larger model) and the
fine-tune itself; this module is the reward/eval half, buildable and testable with neither.
"""
from __future__ import annotations

from dataclasses import dataclass

from .session import Session


def frame_graph(cnl: str) -> frozenset[str]:
    """The FACT-level denotation of a CNL snippet: the set of facts it parses to, as canonical
    `subject predicate object` strings (representation-independent — names, not node ids, order-free).

    Submitted line-by-line through a fresh `Session` (the sequential path, so declared relations /
    definiteness take effect before the facts that use them). Blank / `#` lines skipped. A line that
    parses to no fact (an unrecognized line, or a rule) contributes nothing."""
    s = Session()
    facts: set[str] = set()
    for line in cnl.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        result = s.submit(line)
        facts |= set(getattr(result, "new_facts", None) or [])
    return frozenset(facts)


@dataclass(frozen=True)
class Grade:
    """The exact grade of a candidate CNL against gold. `exact` is the training signal; `missing` /
    `extra` are the frame-graph diff (for triage / targeted data generation); `overlap` is a soft
    Jaccard for ranking near-misses; `parsed` distinguishes an unrecognized candidate from a
    recognized-but-wrong one."""
    parsed: bool
    exact: bool
    missing: tuple[str, ...]     # gold facts the candidate failed to produce
    extra: tuple[str, ...]       # facts the candidate produced that gold does not have
    overlap: float               # |candidate ∩ gold| / |candidate ∪ gold|, in [0, 1]


def grade(candidate: str, gold: str) -> Grade:
    """Grade a candidate CNL translation against a gold CNL by comparing frame graphs. Exact,
    automatic, no model in the loop."""
    cand = frame_graph(candidate)
    want = frame_graph(gold)
    union = cand | want
    return Grade(
        parsed=bool(cand),
        exact=cand == want,
        missing=tuple(sorted(want - cand)),
        extra=tuple(sorted(cand - want)),
        overlap=(len(cand & want) / len(union)) if union else 1.0,
    )


def reward(candidate: str, gold: str) -> float:
    """A scalar reward for rejection sampling / preference pairs: 1.0 iff the frame graph matches gold
    EXACTLY, else the soft overlap (partial credit for near-misses, 0.0 for an unparseable candidate).
    Exact-match is the signal to train on; the soft floor only ranks failures against each other."""
    g = grade(candidate, gold)
    return 1.0 if g.exact else g.overlap
