"""
WordNet on-demand `is_a` scaling probe — does it scale beyond toy?

The architecture's answer to "transitive closure blows up" is ON-DEMAND evaluation
(walker.py / demand.py): a query emits a `<demand>`, a fuelled walker climbs only the
queried entity's `is_a` chain, and the answer materializes as a shortcut. The claim is
SELECTIVITY: per-query work is bounded by the ANSWER's depth, not by the KB size.

That claim has only ever run on toy graphs. Here it meets a real, exogenous taxonomy:
WordNet's noun hypernymy (~82k synsets, ~84k edges, depth ~14-19), loaded as `X is_a Y`.

Two sweeps separate the two failure modes:
  1. N-sweep   — fix query depth, vary KB size N.   FLAT => on-demand bounds work to the
     chain (PASS).  LINEAR in N => something scans the whole graph (SOFT FAIL).
  2. depth-sweep — fix N, vary query depth.          LINEAR in depth is fine; SUPER-LINEAR
     => firing blow-up (HARD FAIL).

We time ONLY the walk (graph copy + load excluded), and record firings + nodes touched so
engine overhead is separable from answer-intrinsic work.

Run:  python bench/wordnet_scaling.py            (default sweeps)
      python bench/wordnet_scaling.py --profile  (cProfile the median query)

Requires nltk + the `wordnet` corpus. If missing:
      python -c "import ssl,nltk; ssl._create_default_https_context=ssl._create_unverified_context; nltk.download('wordnet')"
"""
from __future__ import annotations

import argparse
import random
import statistics
import sys
import time
from dataclasses import dataclass

import harneskills as h
from harneskills.walker import walk_on_demand

SEED = 12345


# ---------------------------------------------------------------------------
# WordNet -> Graph
# ---------------------------------------------------------------------------

def load_noun_synsets():
    try:
        from nltk.corpus import wordnet as wn
    except ImportError:
        sys.exit("nltk not installed: pip install nltk")
    try:
        syns = list(wn.all_synsets("n"))
    except LookupError:
        sys.exit("wordnet corpus not downloaded (see module docstring)")
    return wn, syns


def hypernyms(s):
    """Direct parents in the taxonomy (both ordinary and instance hypernyms)."""
    return s.hypernyms() + s.instance_hypernyms()


def ancestor_closure(synsets) -> set:
    """`synsets` plus every transitive hypernym — an ancestor-closed set, so every chain
    inside it is intact (a subsample that cut a chain would corrupt depth queries)."""
    seen: set = set()
    stack = list(synsets)
    while stack:
        s = stack.pop()
        if s in seen:
            continue
        seen.add(s)
        stack.extend(hypernyms(s))
    return seen


def build_graph(synset_set: set):
    """One node per synset (named by `synset.name()`, which is unique), one `is_a` relation
    per hypernym edge whose endpoints are both in the set. Returns (graph, {synset: node_id})."""
    g = h.Graph()
    ids = {s: g.add_node(s.name()) for s in synset_set}
    for s in synset_set:
        for hyp in hypernyms(s):
            if hyp in ids:
                g.add_relation(ids[s], "is_a", ids[hyp])
    return g, ids


# ---------------------------------------------------------------------------
# Probes — fixed (descendant, ancestor) pairs at a known depth
# ---------------------------------------------------------------------------

@dataclass
class Probe:
    subj: str          # synset name of the descendant
    obj: str           # synset name of the ancestor (positive) or unrelated (negative)
    depth: int         # hops from subj up to obj (0 for negatives)
    positive: bool


def pick_anchors(synsets, *, min_depth: int, k: int):
    """k deterministic deep synsets (a single hypernym path of length >= min_depth). These are
    force-included in EVERY subsample so the same probes resolve at every N."""
    rng = random.Random(SEED)
    deep = [s for s in synsets if s.hypernym_paths()
            and max(len(p) for p in s.hypernym_paths()) >= min_depth]
    rng.shuffle(deep)
    return deep[:k]


def make_probes(anchors, *, depth: int, negatives) -> list[Probe]:
    """For each anchor, a POSITIVE probe to its ancestor `depth` hops up its longest path,
    and a NEGATIVE probe to an unrelated synset (not on any of the anchor's paths)."""
    probes: list[Probe] = []
    neg_pool = list(negatives)
    rng = random.Random(SEED + depth)
    for a in anchors:
        paths = a.hypernym_paths()
        if not paths:
            continue
        path = max(paths, key=len)              # root ... a  (a is last)
        if len(path) <= depth:
            continue
        ancestor = path[-1 - depth]             # `depth` hops up from a
        probes.append(Probe(a.name(), ancestor.name(), depth, True))
        # a negative: an ancestor set to avoid, pick something off all paths
        on_path = {s for p in paths for s in p}
        neg = next((n for n in rng.sample(neg_pool, k=min(50, len(neg_pool)))
                    if n not in on_path), None)
        if neg is not None:
            probes.append(Probe(a.name(), neg.name(), 0, False))
    return probes


# ---------------------------------------------------------------------------
# Running one query (timed) — on the walker (the wired on-demand path)
# ---------------------------------------------------------------------------

def has_is_a(g: h.Graph, subj: str, obj: str) -> bool:
    objs = set(g.nodes_named(obj))
    for s in g.nodes_named(subj):
        for r, o in g.relations_from(s):
            if g.name(r) == "is_a" and o in objs:
                return True
    return False


@dataclass
class Result:
    answer: bool
    correct: bool
    seconds: float
    firings: int


def run_query(g: h.Graph, p: Probe, *, fuel: int) -> Result:
    """Copy the graph (so the materialized shortcut doesn't pollute the next query), then time
    ONLY the on-demand walk. The copy + correctness check are outside the timer."""
    gq = g.copy()
    t0 = time.perf_counter()
    journal = _walk(gq, p.subj, p.obj, fuel=fuel)
    dt = time.perf_counter() - t0
    ans = has_is_a(gq, p.subj, p.obj)
    return Result(ans, ans == p.positive, dt, len(journal))


def _walk(g: h.Graph, subj: str, obj: str, *, fuel: int):
    """walk_on_demand, but return the firing journal for accounting. Mirrors the library call
    (seed demand + budget, SEED THE RUN FROM THE DEMAND'S LOCALITY, run walker rules with the
    tools) so we can count firings. The `seeds` matters: without it `run`'s first frontier is
    `set(graph.nodes())` (O(graph) per query) — exactly what walk_on_demand passes."""
    from harneskills import demand, walker
    from harneskills.rewriter import run as rw_run
    d = demand.seed_demand(g, subj, obj)
    amt = g.nodes_named(str(fuel))
    g.add_relation(d, walker.AMOUNT, amt[0] if amt else g.add_node(str(fuel)))
    return rw_run(g, walker.load_walker_rules(), tools=walker.WALK_TOOLS,
                  seeds=[d, *g.within([d], 1)])


# ---------------------------------------------------------------------------
# Sweeps
# ---------------------------------------------------------------------------

def summarize(results: list[Result]) -> dict:
    secs = sorted(r.seconds for r in results)
    return {
        "n": len(results),
        "correct": sum(r.correct for r in results),
        "median_ms": statistics.median(secs) * 1000,
        "p90_ms": secs[min(len(secs) - 1, int(0.9 * len(secs)))] * 1000,
        "median_firings": int(statistics.median([r.firings for r in results])),
    }


def fmt_row(label, s) -> str:
    return (f"{label:>14} | {s['n']:>4} q | correct {s['correct']:>3}/{s['n']:<3} | "
            f"median {s['median_ms']:8.2f} ms | p90 {s['p90_ms']:8.2f} ms | "
            f"firings {s['median_firings']:>4}")


def n_sweep(synsets, anchors, *, fractions, depth, fuel):
    print(f"\n=== N-SWEEP (fixed depth={depth}, fuel={fuel}) — flat? or linear in N? ===")
    rng = random.Random(SEED)
    anchor_set = set(anchors)
    for f in fractions:
        sample = rng.sample(synsets, k=int(f * len(synsets)))
        subset = ancestor_closure(set(sample) | anchor_set)
        g, _ = build_graph(subset)
        negs = [s for s in subset if s not in anchor_set]
        probes = make_probes(anchors, depth=depth, negatives=negs)
        results = [run_query(g, p, fuel=fuel) for p in probes]
        print(fmt_row(f"N={len(g):>6}", summarize(results)))


def depth_sweep(synsets, anchors, *, depths, fuel):
    print(f"\n=== DEPTH-SWEEP (full KB, fuel={fuel}) — linear in depth? or super-linear? ===")
    subset = ancestor_closure(set(synsets))          # the whole noun taxonomy
    g, _ = build_graph(subset)
    negs = [s for s in subset if s not in set(anchors)]
    print(f"   (full graph: {len(g)} nodes)")
    for d in depths:
        probes = [p for p in make_probes(anchors, depth=d, negatives=negs) if p.positive]
        if not probes:
            continue
        results = [run_query(g, p, fuel=fuel) for p in probes]
        print(fmt_row(f"depth={d}", summarize(results)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", action="store_true", help="cProfile one median query")
    ap.add_argument("--fuel", type=int, default=30,
                    help="walker budget; need >= max ancestor height (~20 for WordNet nouns)")
    args = ap.parse_args()

    print("loading WordNet noun taxonomy ...")
    _wn, synsets = load_noun_synsets()
    anchors = pick_anchors(synsets, min_depth=13, k=40)
    print(f"{len(synsets)} noun synsets; {len(anchors)} deep probe anchors")

    if args.profile:
        import cProfile
        import pstats
        subset = ancestor_closure(set(synsets))
        g, _ = build_graph(subset)
        negs = [s for s in subset if s not in set(anchors)]
        probe = [p for p in make_probes(anchors, depth=10, negatives=negs) if p.positive][0]
        gq = g.copy()
        pr = cProfile.Profile()
        pr.enable()
        _walk(gq, probe.subj, probe.obj, fuel=args.fuel)
        pr.disable()
        pstats.Stats(pr).sort_stats("cumulative").print_stats(20)
        return

    n_sweep(synsets, anchors, fractions=[0.02, 0.1, 0.3, 1.0], depth=8, fuel=args.fuel)
    depth_sweep(synsets, anchors, depths=[2, 4, 6, 8, 10, 12], fuel=args.fuel)


if __name__ == "__main__":
    main()
