"""
Joern CPG -> substrate frames — the fact-producer extractor (docs/vision_agentic.md §4, §5).

Joern is a FACT PRODUCER, never a second engine (§4): a Code Property Graph IS our relational
substrate in a different serialization, so loading a joern export is mechanical re-serialization,
not a semantic bridge. This module folds a CPG export into `S P O` facts, then runs RECOGNIZER
rules that materialize the SAME `Iteration`/`Mutation` frame ontology the Stage-1 probe hand-authored
(`tests/test_code_frames.py`) — so the identical mechanism rules then derive the hazard. Frames are
the CPG<->CNL join (§5): the CPG-side recognizer and the CNL-side grammar independently target one
frame type; nothing here references CNL.

DECOUPLED FROM A LIVE JOERN (the vision's §10 Stage-4 "one vertical slice"). The adapter operates on
a NORMALIZED CPG intermediate:

    {"nodes": [{"id","label","properties":{...}}], "edges": [{"src","dst","label"}]}

with faithful CPG labels/edges (METHOD, CONTROL_STRUCTURE + CONTROL_STRUCTURE_TYPE, CALL + NAME,
IDENTIFIER, edges AST / REF / RECEIVER / ARGUMENT).

LIVE-JOERN STATUS (2026-07-05, validated against a real pysrc2cpg export):
  1. `parse_graphson` — BUILT + validated: decodes TinkerPop GraphSON v3 to the normalized shape.
     `export_cpg` runs pysrc2cpg + joern-export end-to-end (needs a JDK + joern-cli). The extractor
     (raw CPG -> normalized -> S P O facts) is real.
  2. **LOWERING FINDING (now handled) — real joern DESUGARS Python `for` into the iterator protocol.**
     `for x in coll:` becomes `tmp = coll.__iter__()` then a `CONTROL_STRUCTURE_TYPE=WHILE` whose body
     does `x = tmp.__next__()`; method-call receivers route through an `<operator>.fieldAccess` CALL,
     not a bare IDENTIFIER. The FOR-tuned RECOGNIZER_RULES (shape A) yield ZERO frames on that output,
     so a SEPARATE shape-B bank (`JOERN_RECOGNIZER_RULES`) matches the WHILE/iterator/fieldAccess
     desugaring and is gated in `analyze` on the presence of a `__next__` node. On a labeled 15-shape
     corpus compiled by real joern: recall 8/8, precision 8/8 (`bench/joern_corpus.py`), including the
     alias case via `same_as` resolution. The hand-authored fixtures (`cpg_*.json`) are schema-faithful
     but LOWERING-UNfaithful (they assume FOR); they still serve `load_cpg` folding + the shape-A path.
     Memory `finding-joern-lowering`.

WHY TWO PHASES (recognition, then reasoning). The iteration recognizer carries a NAC (exclude the
loop's induction variable, see below), which pushes it into a later stratum than the positive
mechanism rules that CONSUME its frames — so a single stratified pass would run the consumers before
the frames exist. Recognition (CPG -> frames) is genuinely a distinct phase from reasoning (frames
-> hazard), exactly as the pipeline already separates forms/canonicalize/reasoning, so `analyze`
runs the two banks in order. (This is authoring around a stratifier limitation, not an engine change
— vision §11 negation-is-stratified-only stands.)
"""
from __future__ import annotations

import json

from ugm.cnl.authoring import run_rules
from ugm.dispatch import _ensure
from ugm.cnl.machine_rules import load_machine_rules
from ugm.world_model import Graph

# The mutator LEXICON — call names that mutate their receiver in place. This is DATA (a lexicon, like
# the verb catalog), inlined here for the vertical slice; it belongs in the KB as declared
# `<name> is a mutator` facts. Extend per language/library (list: append/insert/extend/remove/pop/
# clear/sort/reverse; set: add/discard/update; dict: update/pop/clear/setdefault; Django QuerySet:
# delete/update/create; etc.).
MUTATOR_NAMES = [
    "remove", "pop", "append", "insert", "extend", "add", "discard", "clear",
    "update", "sort", "reverse", "setdefault", "delete",
]

# Node-label / property value that is lowercased on fold (a canonical enum, unlike a NAME/CODE which
# stays verbatim). CONTROL_STRUCTURE_TYPE = FOR/WHILE/... -> for/while/...
_LOWER_VALUE_PROPS = {"CONTROL_STRUCTURE_TYPE"}


def load_cpg(graph: Graph, export: dict) -> dict[str, str]:
    """Fold a normalized CPG `export` into `S P O` facts in `graph`; return the CPG-id -> node-id map.

    Each CPG node becomes one substrate node named `cpg_<id>` (distinct per id — no merging). Its
    label becomes an `is_a <label>` type fact; each property `K: v` becomes a `<k> <v>` fact; each
    edge becomes a `<label>` relation between the two nodes. Property VALUE nodes are interned by name
    (`_ensure`), so e.g. a CALL's `name remove` shares the node the mutator catalog marks `is_a
    mutator` — the recognizer joins them structurally (the matcher binds structure, not name-equality)."""
    id2node: dict[str, str] = {}
    for n in export["nodes"]:
        node = graph.add_node(f"cpg_{n['id']}")
        id2node[str(n["id"])] = node
        graph.add_relation(node, "is_a", _ensure(graph, n["label"].lower()))
        for key, value in (n.get("properties") or {}).items():
            text = str(value)
            if key in _LOWER_VALUE_PROPS:
                text = text.lower()
            graph.add_relation(node, key.lower(), _ensure(graph, text))
    for e in export["edges"]:
        graph.add_relation(id2node[str(e["src"])], e["label"].lower(), id2node[str(e["dst"])])
    return id2node


def seed_mutator_catalog(graph: Graph) -> None:
    """Assert the mutator lexicon as `<name> is a mutator` facts, interning each name node so it
    coincides with a folded CALL `name` value."""
    mutator = _ensure(graph, "mutator")
    for name in MUTATOR_NAMES:
        graph.add_relation(_ensure(graph, name), "is_a", mutator)


# --- recognizer bank: CPG structure -> Iteration / Mutation frames -----------
#
# `ast_star` is transitive AST containment (the "within" / scoping relation). The recognizer targets
# TWO frontend lowerings of a Python for-loop, structurally disjoint so they never interfere:
#
# (A) CANONICAL "FOR" shape — the hand-authored fixtures and the ast->CPG feeder (bench/cpg_scaling.py):
#     a `CONTROL_STRUCTURE_TYPE=FOR` whose iterable is a DIRECT AST child (`?loop ast ?id`), body nested
#     under a BLOCK. Binding from the DIRECT child (not `ast_star`) avoids the ~4x over-recognition that
#     keying on transitive containment caused on real loop bodies (memory `finding-cpg-scaling-precision`).
#     The NAC `not ?loop ast_star ?decl` drops the loop's INDUCTION VARIABLE (its LOCAL is FOR-contained).
#
# (B) REAL JOERN "WHILE" shape — validated against a real pysrc2cpg export (memory `finding-joern-
#     lowering`). Joern DESUGARS `for x in coll:` into the iterator protocol: `tmp = coll.__iter__()`
#     then a `CONTROL_STRUCTURE_TYPE=WHILE` whose body does `x = tmp.__next__()`. The collection is the
#     identifier ARGUMENT of the `__iter__` call; the iterator temp links the `__iter__` ASSIGNMENT to
#     the loop's `__next__` via a shared LOCAL (both identifiers REF it). A `list(coll)` iterable makes
#     `__iter__`'s argument a CALL (not an identifier), so it correctly yields NO `iterates` (safe copy).
#     Mutator receivers route through an `<operator>.fieldAccess` CALL, so the object identifier is
#     `?call receiver ?fa and ?fa ast ?objid` (the FIELD_IDENTIFIER sibling is excluded by `is_a identifier`).
#
# Real joern has no FOR and its receivers are fieldAccess CALLs with no REF, so shape (A) stays inert on
# real output. Shape (B) is a SEPARATE bank run ONLY on joern-lowered CPGs — gated in `analyze` on the
# presence of a `__next__` node — because it does NOT cheaply stay inert on a FOR-shaped graph: the rule
# compiler SORTS a rule's body patterns lexically, so hand-ordering can't put a distinctive gate first;
# on a graph lacking `__next__`/`__iter__`/`while` the matcher seeds the sorted-first, under-constrained
# `?asgn argument ?ic` and explores the whole argument/ref join before the (late-sorted) gates prune —
# a combinatorial blowup. Gating keeps (B) off non-joern graphs; on joern it is bounded (few __iter__/
# __next__ nodes prune immediately). (B) reuses the `ast_star` closure (A) already materialized.
RECOGNIZER_RULES = load_machine_rules("""
    ?a ast_star ?b when ?a ast ?b
    ?a ast_star ?c when ?a ast ?b and ?b ast_star ?c
    ?loop is_a iteration and ?loop iterates ?decl when ?loop control_structure_type for and ?loop ast ?id and ?id is_a identifier and ?id ref ?decl and not ?loop ast_star ?decl
    ?call is_a mutation and ?call mutates ?decl and ?call within ?loop when ?call is_a call and ?call name ?nm and ?nm is_a mutator and ?call receiver ?recv and ?recv ref ?decl and ?loop control_structure_type for and ?loop ast_star ?call
""")

# Shape (B): real joern WHILE/iterator lowering. Run by `analyze` ONLY when the CPG is joern-lowered.
# The iteration recognizer is SPLIT into staged rules that each materialize an intermediate frame
# (nextcall/itercall markers -> itercoll/looptmp -> iterates), each seeded from a RARE anchor
# (`__next__`/`__iter__`, then the rare derived `itercoll`/`looptmp`). A single 14-clause join was
# O(n^2+) on real joern (25s on a 15-function corpus, 9.7k nodes): the compiler sorts a rule's clauses
# LEXICALLY, so the under-constrained high-df `?asgn argument ?ic` / `?loop ast_star ?nc` clauses seed
# first and the rare gates prune too late, compounding self-joins. Staging breaks the compounding -> 1.4s
# (18x). The mutation rule stays monolithic (it seeds from the loop gate + bounded receiver walk, fast).
#
# NESTED-LOOP PRECISION — `looptmp` binds the WHILE to its OWN iterator via the BOUNDED ast path
# `?w ast ?blk and ?blk ast ?nasgn and ?nasgn argument ?nc` (while -> body BLOCK -> the `x = tmp.__next__()`
# assignment -> the __next__ CALL), NOT `?w ast_star ?nc`. Transitive containment let an OUTER loop absorb
# every NESTED loop's `__next__`, so the outer loop appeared to `iterate` all inner collections — a
# mutation in the outer body touching one of them then false-flagged (measured on real Django:
# `translation/template.py`, a token loop with read-only `for part in singular`/`plural` loops nested
# inside it + `singular.append`/`plural.append` in the outer body -> 4 FPs, all gone with the bounded
# path). Same class as the shape-A `ast_star`->`ast` fix (memory `finding-cpg-scaling-precision`):
# key a frame on the DIRECT structural position, not transitive containment.
#
# ALIAS RESOLUTION (`same_as`) — closes the `a = xs; for x in xs: a.remove(x)` miss. The mutation
# receiver's REF resolves to the alias LOCAL, a DIFFERENT decl than the iterated collection, so the
# mutation rule can't compose (memory `finding-joern-lowering`, the documented hard_ case). A plain
# `t = s` copy-free assignment is an `<operator>.assignment` CALL whose TWO arguments are both bare
# identifiers-with-REF — every DESUGARED assignment (`tmp = xs.__iter__()`, `x = tmp.__next__()`) and
# every real COPY (`a = list(xs)`, `a = xs[:]`) has a CALL on the rhs, so it yields exactly ONE
# `asgnvar` and cannot link two distinct decls. So `same_as` between DISTINCT decls arises ONLY from a
# genuine two-identifier alias — precise by construction (copies stay silent for free). `consumes` is
# then propagated across `same_as` in the mechanism bank, so the EXISTING hazard rule fires unchanged
# (composition, vision §6 — no new mutation rule).
#
# CLAUSE-ORDER TRAP (the session's load-bearing lesson): the rule compiler SORTS a rule's LHS patterns
# LEXICALLY by (s,p,o) token (authoring `_pat_key`), and the matcher seeds from `pats[0]` — so I can't
# hand-order clauses. The killer is COMPOUNDING CARTESIANS (two independent free vars in one rule). So
# `asgnvar` threads a SINGLE identifier `?a` (O(N)-linear, the same shape as `itercoll` above), and the
# `same_as` join seeds from the RARE derived `asgnvar` predicate — never a two-free-var join over a
# `<operator>.assignment` × identifier × identifier cartesian.
JOERN_RECOGNIZER_RULES = load_machine_rules("""
    ?nc is_a nextcall when ?nc name __next__
    ?ic is_a itercall when ?ic name __iter__
    ?ic itercoll ?decl when ?ic is_a itercall and ?ic argument ?collid and ?collid is_a identifier and ?collid ref ?decl
    ?w looptmp ?tmp when ?nc is_a nextcall and ?nc argument ?tid and ?tid is_a identifier and ?tid ref ?tmp and ?w ast ?blk and ?blk ast ?nasgn and ?nasgn argument ?nc and ?w control_structure_type while
    ?w is_a iteration and ?w iterates ?decl when ?w looptmp ?tmp and ?zasgn argument ?ttgt and ?ttgt is_a identifier and ?ttgt ref ?tmp and ?zasgn argument ?ic and ?ic itercoll ?decl
    ?asgn asgnvar ?d when ?asgn name <operator>.assignment and ?asgn argument ?a and ?a is_a identifier and ?a ref ?d
    ?d1 same_as ?d2 when ?asgn asgnvar ?d1 and ?asgn asgnvar ?d2
    ?call is_a mutation and ?call mutates ?decl and ?call within ?loop when ?loop control_structure_type while and ?loop ast_star ?call and ?call name ?nm and ?nm is_a mutator and ?call receiver ?fa and ?fa ast ?objid and ?objid is_a identifier and ?objid ref ?decl
""")

# --- mechanism bank: the SAME frame-level rules as the Stage-1 probe ----------
# (tests/test_code_frames.py). Coverage is by COMPOSITION over frame TYPES/ROLES (vision §6), blind
# to whether the frames came from CNL or from a CPG.
MECHANISM_RULES = load_machine_rules("""
    ?loop consumes ?c when ?loop is_a iteration and ?loop iterates ?c
    ?loop consumes ?d2 when ?loop consumes ?d1 and ?d1 same_as ?d2
    ?m is_a hazard when ?m is_a mutation and ?m mutates ?c and ?m within ?loop and ?loop consumes ?c
""")


def analyze(graph: Graph) -> None:
    """Run recognition then reasoning over an already-loaded CPG (see `load_cpg`): materialize the
    frames, then compose the hazard. Two phases by design (see module docstring). The joern WHILE/
    iterator recognizer runs ONLY on joern-lowered CPGs — detected content-blind by the presence of a
    `__next__` node — so it never explores its heavy join on a FOR-shaped (fixture/feeder) graph."""
    seed_mutator_catalog(graph)
    # Recognition on the ISA forward Machine (`run_bank` via `isa=True`), not `rewriter.run`: pure
    # positive frame/hazard recognition (implementation_plan.md Phase 0.5, the "one engine" peel).
    # No provenance is needed — the detector reads derived triples, not `why`/explain, and benches
    # actively filter provenance nodes out — so run_bank's no-provenance path is a clean (cleaner) fit.
    run_rules(graph, RECOGNIZER_RULES, isa=True)
    if graph.name_count("__next__"):
        run_rules(graph, JOERN_RECOGNIZER_RULES, isa=True)
    run_rules(graph, MECHANISM_RULES, isa=True)


def _gs_unwrap(x):
    """Strip GraphSON v3 typed envelopes ({'@type','@value'}) down to the plain value."""
    while isinstance(x, dict) and "@type" in x and "@value" in x:
        x = x["@value"]
    return x


def _gs_prop(vp) -> str:
    """A vertex property is a (possibly multi-cardinality) VertexProperty wrapping a g:List; return
    the first scalar, stringified (the substrate stores every datum as an opaque node name)."""
    if isinstance(vp, list):
        vp = vp[0] if vp else {}
    lst = _gs_unwrap(vp.get("@value"))
    val = lst[0] if isinstance(lst, list) and lst else lst
    return str(_gs_unwrap(val))


def parse_graphson(raw: str) -> dict:
    """Decode a real `joern-export --format=graphson` (TinkerPop GraphSON v3) into the normalized
    {nodes, edges} shape `load_cpg` reads. BUILT + validated against a real pysrc2cpg export
    (2026-07-05, tests/fixtures/joern_purge_graphson.json).

    Shape: top-level {'@type':'tinker:graph','@value':{'vertices':[...],'edges':[...]}}. A vertex is
    {'id':<g:Int64>,'label':L,'properties':{K:<VertexProperty wrapping a g:List>}}; an edge is
    {'label':L,'outV':<id>,'inV':<id>} with TinkerPop direction outV->inV (source->destination)."""
    inner = _gs_unwrap(json.loads(raw))
    nodes = [{"id": str(_gs_unwrap(v["id"])), "label": v["label"],
              "properties": {k: _gs_prop(vp) for k, vp in (v.get("properties") or {}).items()}}
             for v in inner["vertices"]]
    edges = [{"src": str(_gs_unwrap(e["outV"])), "dst": str(_gs_unwrap(e["inV"])),
              "label": e["label"]} for e in inner["edges"]]
    return {"nodes": nodes, "edges": edges}


def export_cpg(source, joern_home: str | None = None) -> dict:
    """Live-joern shell-out (§10 Stage-4): run pysrc2cpg + joern-export on a Python file/dir and
    return the normalized CPG. Requires a joern-cli install (`joern_home` or $JOERN_HOME) + a JDK.
    Only the format decode (parse_graphson) is our code; joern is a pure fact producer (§4).

    Real joern desugars `for` to a WHILE loop over the iterator protocol (see the module docstring);
    the shape-B `JOERN_RECOGNIZER_RULES` match that lowering, so `analyze` on this output fires frames
    and reaches the hazard (validated end-to-end by `bench/joern_corpus.py`)."""
    import os
    import pathlib
    import subprocess
    import tempfile
    home = joern_home or os.environ.get("JOERN_HOME")
    if not home:
        raise RuntimeError("set JOERN_HOME to the joern-cli directory (or pass joern_home=)")
    suffix = ".bat" if os.name == "nt" else ""
    with tempfile.TemporaryDirectory() as td:
        cpg_bin = os.path.join(td, "cpg.bin")
        out = os.path.join(td, "export")
        subprocess.run([os.path.join(home, "pysrc2cpg" + suffix), str(source),
                        "--output", cpg_bin], check=True)
        subprocess.run([os.path.join(home, "joern-export" + suffix), cpg_bin,
                        "--repr", "all", "--format", "graphson", "--out", out], check=True)
        raw = next(pathlib.Path(out).glob("*.json")).read_text(encoding="utf-8")
    return parse_graphson(raw)
