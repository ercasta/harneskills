"""
Real-corpus recall/precision for the mutate-during-iteration detector, THROUGH THE LIVE JOERN PIPELINE.

The coverage/composition audit (bench/coverage_audit.py) measured mechanism coverage over HAND-AUTHORED
frames; the CPG scaling probe measured the matcher on real code but with a stand-in ast->CPG feeder. This
closes the loop: a LABELED corpus of real mutate-during-iteration bug shapes + safe near-misses
(tests/fixtures/joern_corpus_source.py) is compiled by REAL joern (pysrc2cpg + joern-export), and the
recognizer (harneskills/cpg.py shape B, matching joern's WHILE/iterator desugaring) runs on the actual
export. So every stage is real: extraction (joern), decode (parse_graphson), recognition, reasoning.

Ground truth is the function-name prefix (see the source): pos_* = a real MDI bug the analyzer SHOULD
flag; neg_* = safe, must stay silent; hard_* = a real bug we EXPECT to miss (a documented limitation,
scored separately). A hazard (a mutation CALL) is mapped back to its enclosing function via `?method
ast_star ?call`, so recall/precision are computed per function against the labels.

REPRODUCIBLE OFFLINE: measures from the captured GraphSON fixture (joern_corpus_graphson.json), so it
needs no live joern. Regenerate the fixture with a live joern via `harneskills.cpg.export_cpg` when the
corpus or the joern frontend changes.

Run:  python bench/joern_corpus.py
"""
from __future__ import annotations

import pathlib

import harneskills as h
from harneskills import cpg

FIXTURE = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "joern_corpus_graphson.json"


def _analyzed_graph() -> h.Graph:
    g = h.Graph()
    cpg.load_cpg(g, cpg.parse_graphson(FIXTURE.read_text(encoding="utf-8")))
    cpg.analyze(g)
    return g


def _functions(g: h.Graph) -> dict[str, str]:
    """{method-node-id: function name} for every named function (excludes joern's <module> method)."""
    mnode = g.nodes_named("method")
    if not mnode:
        return {}
    meths = [n for n in g.nodes() if cpg._relation_exists(g, n, "is_a", mnode[0])]
    def name(n):
        return next((g.name(o) for r, o in g.relations_from(n) if g.name(r) == "name"), "?")
    return {n: name(n) for n in meths if name(n) not in ("?", "<module>")}


def _hazards(g: h.Graph) -> list[str]:
    haz = g.nodes_named("hazard")
    if not haz:
        return []
    prov = {h.PROVES, h.USES, h.AXIOM}
    return [n for n in g.nodes()
            if g.name(n) not in prov and cpg._relation_exists(g, n, "is_a", haz[0])]


_CACHE: dict | None = None


def measure() -> dict:
    """Per-function flagged/silent vs ground-truth label, plus recall / precision / miss taxonomy.
    Memoized: analyzing the ~9.7k-node corpus graph once is enough (callers must not mutate the result)."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    g = _analyzed_graph()
    funcs = _functions(g)                                  # id -> name
    flagged: set[str] = set()
    for call in _hazards(g):
        for mid, fname in funcs.items():
            if cpg._relation_exists(g, mid, "ast_star", call):
                flagged.add(fname)                         # the mutation's enclosing function(s)

    names = sorted(set(funcs.values()))
    pos = [n for n in names if n.startswith("pos_")]
    neg = [n for n in names if n.startswith("neg_")]
    hard = [n for n in names if n.startswith("hard_")]
    caught_pos = [n for n in pos if n in flagged]
    false_pos = [n for n in neg if n in flagged]
    caught_hard = [n for n in hard if n in flagged]

    _CACHE = {
        "names": names, "flagged": flagged,
        "pos": pos, "neg": neg, "hard": hard,
        "caught_pos": caught_pos, "false_pos": false_pos, "caught_hard": caught_hard,
        "recall": len(caught_pos) / max(1, len(pos)),
        "precision": len(caught_pos) / max(1, len(caught_pos) + len(false_pos)),
        "missed_pos": [n for n in pos if n not in flagged],
    }
    return _CACHE


def report() -> dict:
    m = measure()
    print("=" * 84)
    print("REAL-CORPUS MDI recall/precision — through the LIVE joern pipeline")
    print("=" * 84)
    print(f"\n{len(m['names'])} functions: {len(m['pos'])} real bugs (pos_), "
          f"{len(m['neg'])} safe (neg_), {len(m['hard'])} expected-miss (hard_)\n")
    for n in m["names"]:
        label = "BUG " if n.startswith("pos_") else ("safe" if n.startswith("neg_") else "hard")
        got = "FLAG  " if n in m["flagged"] else "silent"
        if n.startswith("pos_"):
            ok = "ok " if n in m["flagged"] else "XX "
        elif n.startswith("neg_"):
            ok = "ok " if n not in m["flagged"] else "XX "
        else:
            ok = "-- "                                     # hard_: either outcome is informative
        print(f"  {ok}{n:36s} [{label}]  -> {got}")

    print("\n" + "-" * 84)
    print(f"  Recall (real bugs caught) : {m['recall']:6.1%}   "
          f"({len(m['caught_pos'])}/{len(m['pos'])})")
    print(f"  Precision (of flags)      : {m['precision']:6.1%}   "
          f"(false positives on safe code: {len(m['false_pos'])})")
    if m["false_pos"]:
        print(f"    FALSE POSITIVES: {', '.join(m['false_pos'])}")
    if m["missed_pos"]:
        print(f"    MISSED BUGS    : {', '.join(m['missed_pos'])}")
    print(f"  Documented-miss (hard_)   : {len(m['hard']) - len(m['caught_hard'])}/{len(m['hard'])} "
          f"missed as expected"
          + (f"; unexpectedly CAUGHT: {', '.join(m['caught_hard'])}" if m["caught_hard"] else ""))
    print("\n  Every stage is real joern: pysrc2cpg -> joern-export -> parse_graphson -> recognizer.")
    return m


if __name__ == "__main__":
    report()
