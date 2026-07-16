"""
CPG matcher-scaling probe — does the recognizer/mechanism pipeline survive a REAL code graph, or
hit the Tier-4 dense/cyclic hub-flooding wall ([[finding-matcher-is-matching-bound]])?

`harneskills/cpg.py` folds a NORMALIZED CPG ({nodes, edges}) into `S P O` facts and runs a recognizer
(CPG structure -> Iteration/Mutation frames) then the mechanism rules (frames -> hazard). Its
`parse_graphson` (real joern wire decode) is stubbed and needs a JDK + joern-cli, so we cannot decode a
real joern export here. But the SCALING question does not need joern: a real Python file's AST + REF
graph, emitted in joern's normalized schema, is exactly the stressor. `ast_star` (transitive AST
containment, materialized by the recognizer) is precisely the dense-closure operation that could blow
up — this probe measures whether it does, on real source at increasing size.

TWO deliverables, both "past-toy" findings:
  1. SCALING — node/edge counts, the `ast_star` closure size (and its ratio to `ast`), and load/analyze
     wall-clock as the input grows. Sub-quadratic ast_star and bounded time => the matcher survives real
     CPGs; super-linear blow-up => the Tier-4 wall is real for code graphs too.
  2. PRECISION — the recognizer keys `iterates` on ANY identifier transitively AST-contained by a loop
     whose declaration sits outside it (`cpg.py` RECOGNIZER_RULES). On the toy fixture the only such
     identifier is the iterated collection; on REAL code, loop bodies reference many outer variables, so
     this likely OVER-recognizes (iterates >> #for-loops) and can manufacture false-positive hazards. We
     measure iterates/consumes/mutates/hazard counts so the toy->real precision cliff is visible.

The `ast`->CPG feeder below is a faithful-enough joern-schema APPROXIMATION for a Python subset (the
same status cpg.py grants its fixtures): METHOD/params, CONTROL_STRUCTURE(FOR) with the induction var as
a loop-scoped LOCAL (so the recognizer's NAC can exclude it), CALL with NAME/RECEIVER/ARGUMENT,
IDENTIFIER with REF resolved by a lexical scope stack. It is NOT a validated joern frontend — it exists
to generate real-shaped, real-scale graphs to profile the matcher on.

Run:  python bench/cpg_scaling.py
"""
from __future__ import annotations

import ast
import pathlib
import sys
import time

import ugm
import harneskills as h
from harneskills import cpg

sys.setrecursionlimit(20000)


# ---------------------------------------------------------------------------
# ast -> normalized CPG ({nodes, edges}, joern-schema-faithful for a Python subset)
# ---------------------------------------------------------------------------

class _PyToCPG:
    """Emit a normalized CPG for one module. A lexical scope stack resolves IDENTIFIER -> decl (REF).
    for-targets become LOCALs AST-contained by the loop (the recognizer NAC needs that); params and
    assignment targets become decls in the enclosing FUNCTION scope (NOT under a loop)."""

    def __init__(self, prefix: str):
        self.prefix = prefix
        self.nodes: list[dict] = []
        self.edges: list[dict] = []
        self._id = 0
        self.scopes: list[dict[str, str]] = [{}]   # module scope
        self.n_for = 0

    def _node(self, label: str, **props) -> str:
        self._id += 1
        nid = f"{self.prefix}_{self._id}"
        self.nodes.append({"id": nid, "label": label, "properties": props})
        return nid

    def _edge(self, src: str, dst: str, label: str) -> None:
        self.edges.append({"src": src, "dst": dst, "label": label})

    def _lookup(self, name: str) -> str | None:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return None

    # -- dispatch -----------------------------------------------------------
    def visit(self, node: ast.AST, parent: str) -> str | None:
        m = getattr(self, "v_" + type(node).__name__, None)
        if m:
            return m(node, parent)
        return self._generic(node, parent)

    def _generic(self, node: ast.AST, parent: str) -> str:
        nid = self._node(type(node).__name__.upper())
        self._edge(parent, nid, "AST")
        for child in ast.iter_child_nodes(node):
            self.visit(child, nid)
        return nid

    # -- decls / scopes -----------------------------------------------------
    def v_FunctionDef(self, node: ast.FunctionDef, parent: str) -> str:
        m = self._node("METHOD", NAME=node.name)
        self._edge(parent, m, "AST")
        self.scopes[-1][node.name] = m            # callable visible in enclosing scope
        self.scopes.append({})
        try:
            for a in self._all_args(node.args):
                p = self._node("METHOD_PARAMETER_IN", NAME=a.arg)
                self._edge(m, p, "AST")
                self.scopes[-1][a.arg] = p
            block = self._node("BLOCK")
            self._edge(m, block, "AST")
            for stmt in node.body:
                self.visit(stmt, block)
        finally:
            self.scopes.pop()
        return m

    v_AsyncFunctionDef = v_FunctionDef

    @staticmethod
    def _all_args(args: ast.arguments) -> list[ast.arg]:
        out = list(getattr(args, "posonlyargs", [])) + list(args.args) + list(args.kwonlyargs)
        if args.vararg:
            out.append(args.vararg)
        if args.kwarg:
            out.append(args.kwarg)
        return out

    def v_For(self, node: ast.For, parent: str) -> str:
        cs = self._node("CONTROL_STRUCTURE", CONTROL_STRUCTURE_TYPE="FOR",
                        CODE=_snippet(node))
        self._edge(parent, cs, "AST")
        self.n_for += 1
        self.visit(node.iter, cs)                 # collection resolves to an OUTER decl (visit first)
        self._bind_target(node.target, cs)        # induction var: LOCAL AST-under the loop
        body = self._node("BLOCK")
        self._edge(cs, body, "AST")
        for stmt in node.body:
            self.visit(stmt, body)
        for stmt in node.orelse:
            self.visit(stmt, body)
        return cs

    v_AsyncFor = v_For

    def _bind_target(self, target: ast.AST, loop: str) -> None:
        for nm in _names(target):
            loc = self._node("LOCAL", NAME=nm)
            self._edge(loop, loc, "AST")          # loop-scoped => recognizer NAC excludes it
            self.scopes[-1][nm] = loc

    # -- expressions --------------------------------------------------------
    def v_Name(self, node: ast.Name, parent: str) -> str | None:
        if isinstance(node.ctx, ast.Store):
            decl = self.scopes[-1].get(node.id)
            if decl is None:
                decl = self._node("LOCAL", NAME=node.id)
                self._edge(parent, decl, "AST")
                self.scopes[-1][node.id] = decl
            return decl
        idn = self._node("IDENTIFIER", NAME=node.id)
        self._edge(parent, idn, "AST")
        decl = self._lookup(node.id)
        if decl is not None:
            self._edge(idn, decl, "REF")
        return idn

    def v_Call(self, node: ast.Call, parent: str) -> str:
        call = self._node("CALL", NAME=_call_name(node), CODE=_snippet(node))
        self._edge(parent, call, "AST")
        func = node.func
        if isinstance(func, ast.Attribute):
            recv = self.visit(func.value, call)   # receiver identifier (if a Name -> has REF)
            if recv is not None:
                self._edge(call, recv, "RECEIVER")
        elif not isinstance(func, ast.Name):
            self.visit(func, call)                # complex callee: keep structure
        for a in node.args:
            aid = self.visit(a, call)
            if isinstance(a, ast.Name) and aid is not None:
                self._edge(call, aid, "ARGUMENT")
        for kw in node.keywords:
            self.visit(kw.value, call)
        return call


def _snippet(node: ast.AST) -> str:
    try:
        return ast.unparse(node)[:80]
    except Exception:
        return ""


def _names(target: ast.AST) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [n for elt in target.elts for n in _names(elt)]
    return []


def _call_name(node: ast.Call) -> str:
    f = node.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return ""


def ast_to_cpg(source: str, prefix: str) -> tuple[dict, int, int]:
    """Return (normalized-cpg export, #ast_nodes, #for_loops) for one module's source."""
    tree = ast.parse(source)
    builder = _PyToCPG(prefix)
    root = builder._node("METHOD", NAME="<module>")
    for stmt in tree.body:
        builder.visit(stmt, root)
    n_ast = sum(1 for _ in ast.walk(tree))
    return {"nodes": builder.nodes, "edges": builder.edges}, n_ast, builder.n_for


# ---------------------------------------------------------------------------
# Profiling one graph
# ---------------------------------------------------------------------------

_PROVENANCE = {ugm.PROVES, ugm.USES, ugm.AXIOM}   # provenance nodes spuriously inherit a derived type


def _count_type(g: ugm.Graph, type_name: str) -> int:
    hits = g.nodes_named(type_name)
    if not hits:
        return 0
    t = hits[0]
    return sum(1 for n in g.nodes()
               if g.name(n) not in _PROVENANCE and cpg._relation_exists(g, n, "is_a", t))


def profile(export: dict, n_for: int) -> dict:
    g = ugm.Graph()
    t0 = time.perf_counter()
    cpg.load_cpg(g, export)
    t_load = time.perf_counter() - t0
    n_nodes_after_load = len(g)
    n_ast = g.name_count("ast")

    t1 = time.perf_counter()
    cpg.analyze(g)
    t_analyze = time.perf_counter() - t1

    return {
        "for": n_for,
        "cpg_nodes": n_nodes_after_load,
        "ast": n_ast,
        "ast_star": g.name_count("ast_star"),
        "ref": g.name_count("ref"),
        "iterates": g.name_count("iterates"),
        "consumes": g.name_count("consumes"),
        "mutates": g.name_count("mutates"),
        "hazard": _count_type(g, "hazard"),
        "nodes_total": len(g),
        "t_load": t_load,
        "t_analyze": t_analyze,
    }


def _row(label: str, m: dict) -> str:
    astr = m["ast_star"]
    ratio = astr / m["ast"] if m["ast"] else 0.0
    return (f"{label:<26} for {m['for']:>4} | cpg_nodes {m['cpg_nodes']:>7} | "
            f"ast {m['ast']:>6} ast* {astr:>8} ({ratio:4.1f}x) | ref {m['ref']:>6} | "
            f"iter {m['iterates']:>5} cons {m['consumes']:>5} mut {m['mutates']:>4} "
            f"HAZ {m['hazard']:>4} | load {m['t_load']:6.2f}s analyze {m['t_analyze']:7.2f}s")


def main() -> None:
    pkg = pathlib.Path(h.__file__).resolve().parent
    files = sorted(pkg.glob("*.py"), key=lambda p: p.stat().st_size)
    print(f"CPG matcher-scaling probe over {len(files)} real modules in {pkg.name}/\n")
    hdr = (f"{'module':<26} {'':>4}   {'':>7}   {'':>6}  transitive AST closure   "
           f"           recognizer frames        wall-clock")
    print(hdr)
    print("-" * len(_row("x", {k: 0 for k in
          ('for', 'cpg_nodes', 'ast', 'ast_star', 'ref', 'iterates', 'consumes',
           'mutates', 'hazard', 'nodes_total', 't_load', 't_analyze')})))

    exports = []
    for p in files:
        src = p.read_text(encoding="utf-8", errors="replace")
        try:
            export, n_ast, n_for = ast_to_cpg(src, p.stem)
        except SyntaxError as e:
            print(f"{p.name:<26} SKIP (syntax: {e})")
            continue
        exports.append((export, n_for))
        m = profile(export, n_for)
        print(_row(p.name, m))

    # --- max-scale point: every module merged into ONE graph (ids already prefixed per file) ---
    print("\n" + "=" * 40 + " combined graph (all modules) " + "=" * 40)
    big = {"nodes": [n for e, _ in exports for n in e["nodes"]],
           "edges": [ed for e, _ in exports for ed in e["edges"]]}
    total_for = sum(f for _, f in exports)
    m = profile(big, total_for)
    print(_row(f"ALL ({len(exports)} modules)", m))
    print(f"\n  total nodes after analyze: {m['nodes_total']:,} | "
          f"ast_star/ast ratio: {m['ast_star']/max(1,m['ast']):.1f}x | "
          f"analyze: {m['t_analyze']:.2f}s")


if __name__ == "__main__":
    main()
