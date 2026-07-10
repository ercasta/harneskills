"""
Pins the two findings of the CPG matcher-scaling probe (bench/cpg_scaling.py): the recognizer/mechanism
pipeline survives a REAL code graph on the SCALING axis (transitive AST closure is linear, no Tier-4
hub-flooding — AST containment is a tree), but hits a toy->real PRECISION cliff (the `iterates`
recognizer over-recognizes on real loop bodies and manufactures false-positive hazards). Both are pinned
on tiny deterministic reproducers so a recognizer fix makes the precision finding visibly flip while the
true-positive and scaling guards must stay green. See memory `finding-cpg-scaling-precision`.
"""
import harneskills as h
from harneskills import cpg

from bench.cpg_scaling import _count_type, ast_to_cpg


def _analyze(src: str) -> h.Graph:
    g = h.Graph()
    export, _, _ = ast_to_cpg(src, "t")
    cpg.load_cpg(g, export)
    cpg.analyze(g)
    return g


# --- feeder faithfulness: the ast->CPG feeder drives the REAL cpg.py pipeline to the same hazard the
#     hand-authored fixture (tests/test_cpg_adapter.py) and the Stage-1 probe produce -------------------

def test_feeder_reproduces_mutate_during_iteration_hazard():
    g = _analyze("def purge(items):\n    for x in items:\n        items.remove(x)\n")
    assert g.name_count("iterates") == 1            # exactly the iterated collection
    assert _count_type(g, "hazard") == 1            # the real MDI bug, end-to-end through cpg.analyze


# --- FIX (precision): binding `iterates` from the loop's DIRECT iterator child (not transitive
#     containment) kills the over-recognition. The accumulator-in-a-loop no longer flags a false
#     hazard, and the loop iterates exactly its real collection. -----------------------------------

def test_accumulator_loop_is_not_a_false_positive():
    # `for r in rules: out.append(r)` — the classic build-a-list-in-a-loop. `out` is an OUTER decl
    # referenced in the loop BODY (not the iterator slot), so the fixed recognizer no longer treats it
    # as iterated. Exactly one iterated collection (`rules`), and NO hazard. (Pre-fix: iterates 2, 1 FP.)
    g = _analyze("def build(rules):\n    out = []\n    for r in rules:\n        out.append(r)\n")
    assert g.name_count("iterates") == 1            # only the real iterator `rules`
    assert _count_type(g, "hazard") == 0            # the false positive is gone


# --- scaling guard: transitive AST closure is LINEAR in size (tree depth bounded), not quadratic —
#     the reason the Tier-4 dense/cyclic hub-flooding does NOT fire on code AST graphs ------------------

def test_ast_star_closure_is_linear_not_quadratic():
    def ratio(n_funcs: int) -> float:
        src = "\n".join(f"def f{i}(xs):\n    for a in xs:\n        xs.remove(a)\n"
                        for i in range(n_funcs))
        g = _analyze(src)
        return g.name_count("ast_star") / g.name_count("ast")

    # identical independent functions: if closure were super-linear the per-node ratio would GROW with
    # count; a stable ratio across a 4x size increase is the linear-closure signature.
    small, large = ratio(20), ratio(80)
    assert abs(large - small) < 0.5 * small, (small, large)
