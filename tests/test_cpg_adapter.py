"""
Joern CPG -> frames extractor slice (docs/vision_agentic.md §4/§5/§10 Stage 4, the RECOMMENDED-NEXT
arc step). Proves the fact-producer half of the Joern integration WITHOUT a live joern/JVM: a
normalized CPG export (faithful joern labels/edges — see the fixtures + harneskills/cpg.py) is folded
into `S P O` facts, recognizer rules materialize the `Iteration`/`Mutation` frames, and the SAME
mechanism rules from the Stage-1 probe then derive the hazard. The point of Stage 4 is to check that
the EXTRACTED frames match what Stage-1 hand-authored — so the two ends (CPG recognizer, CNL grammar)
meet on one frame ontology (§5), with the reasoning unchanged.

Not covered here (flagged in cpg.py): decoding joern's raw GraphSON wire format (`parse_graphson`,
stubbed) and running `joern-export` itself. Those are verified against a real joern later; this slice
de-risks the valuable half — CPG structure -> frames -> hazard.
"""
import json
import pathlib

import harneskills as h
from harneskills import cpg, rewriter

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"


def _load(name):
    export = json.loads((FIXTURES / f"{name}.json").read_text())
    g = h.Graph()
    ids = cpg.load_cpg(g, export)
    return g, ids


def _has(g, s, p, o):
    return any(rewriter._relation_exists(g, si, p, oi)
               for si in g.nodes_named(s) for oi in g.nodes_named(o))


def test_cpg_facts_fold_in_faithfully():
    # the raw CPG lands as S P O facts before any recognition: labels -> is_a, props -> predicates,
    # edges -> relations (spot-check the shape the recognizer will match).
    g, _ = _load("cpg_purge")
    assert _has(g, "cpg_4", "is_a", "control_structure")
    assert _has(g, "cpg_4", "control_structure_type", "for")
    assert _has(g, "cpg_8", "is_a", "call")
    assert _has(g, "cpg_8", "name", "remove")
    assert _has(g, "cpg_8", "receiver", "cpg_9")     # the mutation's receiver identifier
    assert _has(g, "cpg_6", "ref", "cpg_2")          # `items` in the loop -> the param decl
    assert _has(g, "cpg_9", "ref", "cpg_2")          # `items` in the call -> the SAME param decl


def test_recognizer_materializes_stage1_frames():
    # the extracted frames match what tests/test_code_frames.py hand-authored (§5 the join):
    # an Iteration over the collection, a Mutation of that collection, within the loop.
    g, _ = _load("cpg_purge")
    cpg.analyze(g)
    # Iteration frame — the loop iterates the collection declaration `cpg_2` (the param `items`)...
    assert _has(g, "cpg_4", "is_a", "iteration")
    assert _has(g, "cpg_4", "iterates", "cpg_2")
    # ...and NOT the induction variable `x` (`cpg_11`) — the NAC excludes the loop-scoped decl.
    assert not _has(g, "cpg_4", "iterates", "cpg_11")
    # Mutation frame — the `remove` call mutates the same decl, within the loop
    assert _has(g, "cpg_8", "is_a", "mutation")
    assert _has(g, "cpg_8", "mutates", "cpg_2")
    assert _has(g, "cpg_8", "within", "cpg_4")


def test_hazard_derives_end_to_end_from_real_cpg_shape():
    # the SAME mechanism rules (composition over frame types, §6) fire on CPG-extracted frames:
    # loop consumes the collection, mutation of the consumed collection in-loop -> hazard.
    g, _ = _load("cpg_purge")
    cpg.analyze(g)
    assert _has(g, "cpg_4", "consumes", "cpg_2")
    assert _has(g, "cpg_8", "is_a", "hazard")


def test_read_only_iteration_is_not_a_hazard():
    # `for x in items: print(x)` — iterates but never mutates (print is not in the mutator lexicon,
    # and it has no receiver). The Iteration frame is still recognized; NO hazard is derived.
    g, _ = _load("cpg_read_only")
    cpg.analyze(g)
    assert _has(g, "cpg_4", "is_a", "iteration")
    assert _has(g, "cpg_4", "iterates", "cpg_2")
    assert not _has(g, "cpg_8", "is_a", "mutation")
    assert not any(_has(g, f"cpg_{i}", "is_a", "hazard") for i in range(1, 12))


def test_graphson_decode_is_built():
    # parse_graphson is now BUILT + validated against a real joern export (tests/test_cpg_graphson.py);
    # smoke: an empty TinkerPop graph decodes to empty normalized nodes/edges.
    empty = '{"@type":"tinker:graph","@value":{"vertices":[],"edges":[]}}'
    assert cpg.parse_graphson(empty) == {"nodes": [], "edges": []}
