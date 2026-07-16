"""
Real-joern validation (2026-07-05): the GraphSON decoder + the LOWERING FINDING, pinned against a
CAPTURED real `pysrc2cpg` + `joern-export --format=graphson` export (tests/fixtures/joern_purge_graphson
.json — the `sample.py` probe: purge / safe_copy / accumulate / show). Two things are pinned:

  1. `parse_graphson` decodes TinkerPop GraphSON v3 to the normalized {nodes, edges} shape `load_cpg`
     reads — validated against real joern output, not a hand-authored fixture.
  2. That real joern DESUGARS Python `for` into a WHILE loop over the iterator protocol
     (`tmp = coll.__iter__()` ... `while: x = tmp.__next__()`) and routes method-call receivers through
     `<operator>.fieldAccess` — and that the recognizer (RECOGNIZER_RULES shape B, added after this was
     validated) now MATCHES that lowering: on the real export it catches exactly the `purge`
     mutate-during-iteration bug and stays silent on the copy idiom / accumulator / read-only. See
     memory `finding-joern-lowering`. The hand-authored fixtures remain schema-faithful but
     lowering-unfaithful; shape A of the recognizer still serves them and the ast-feeder.
"""
import json
import pathlib

import ugm
from harneskills import cpg

FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "joern_purge_graphson.json"


def _normalized():
    return cpg.parse_graphson(FIXTURE.read_text(encoding="utf-8"))


# --- 1. the decoder is real -------------------------------------------------

def test_parse_graphson_decodes_real_export():
    g = _normalized()
    assert len(g["nodes"]) == 196 and len(g["edges"]) == 340      # matches joern-export's own count
    labels = {n["label"] for n in g["nodes"]}
    assert {"METHOD", "CONTROL_STRUCTURE", "CALL", "IDENTIFIER", "LOCAL"} <= labels
    edge_labels = {e["label"] for e in g["edges"]}
    assert {"AST", "REF", "RECEIVER", "ARGUMENT"} <= edge_labels
    # ids and property values are stringified opaque names; a CALL carries a NAME property
    calls = [n for n in g["nodes"] if n["label"] == "CALL"]
    assert any(n["properties"].get("NAME") == "remove" for n in calls)


def test_facts_fold_in_from_real_export():
    # the real normalized export folds into S P O facts like any CPG (no hand-authoring).
    g = ugm.Graph()
    cpg.load_cpg(g, _normalized())
    assert g.nodes_named("control_structure")          # CONTROL_STRUCTUREs present as is_a facts
    assert g.nodes_named("remove")                     # the mutator call name interned


# --- 2. the lowering finding (pins the seam the module flagged) --------------

def test_finding_joern_desugars_for_into_while_iterator_protocol():
    g = _normalized()
    cst = [n for n in g["nodes"] if n["label"] == "CONTROL_STRUCTURE"]
    types = {n["properties"].get("CONTROL_STRUCTURE_TYPE") for n in cst}
    # real joern lowers `for x in items:` to WHILE (iterator protocol) — NOT the FOR the fixtures assume
    assert types == {"WHILE"}, types
    # and method-call receivers route through an <operator>.fieldAccess CALL, not a bare identifier
    recv_edges = [e for e in g["edges"] if e["label"] == "RECEIVER"]
    byid = {n["id"]: n for n in g["nodes"]}
    assert any(byid[e["dst"]]["properties"].get("NAME") == "<operator>.fieldAccess" for e in recv_edges)


def test_recognizer_catches_mdi_on_real_joern_lowering():
    # The recognizer now matches joern's real desugaring (RECOGNIZER_RULES shape B: while + iterator
    # protocol + fieldAccess receivers). On the real export of sample.py it catches EXACTLY the `purge`
    # mutate-during-iteration bug and stays silent on the three safe functions: the copy idiom
    # (safe_copy), the accumulator (accumulate), and read-only (show).
    g = ugm.Graph()
    cpg.load_cpg(g, _normalized())
    cpg.analyze(g)
    # 3 iterated collections recognized (purge:items, accumulate:rows, show:items); safe_copy iterates a
    # list() COPY, so `__iter__`'s argument is a CALL not an identifier -> correctly NO `iterates`.
    assert g.name_count("iterates") == 3
    def code(n):
        return next((g.name(o) for r, o in g.relations_from(n) if g.name(r) == "code"), "")
    haz = g.nodes_named("hazard")
    hazards = sorted(code(n) for n in g.nodes()
                     if haz and g.name(n) not in {ugm.PROVES, ugm.USES, ugm.AXIOM}
                     and cpg._relation_exists(g, n, "is_a", haz[0]))
    assert hazards == ["items.remove(x)"], hazards       # only the real MDI bug, in `purge`
