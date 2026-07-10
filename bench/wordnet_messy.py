"""
Messy-graph probe — does the scaling fix hold off a clean near-tree?

WordNet noun hypernymy (the first probe, `wordnet_scaling.py`) is a near-TREE: one relation,
acyclic, low branching. This probe stresses the two things that tree hides:

  PROBE A — CLUTTER / matcher isolation. Build the MULTI-relation noun graph (is_a + part_of +
    member_of + substance_of, ~98k edges of 4 types) and run the TYPED `is_a` walk over it. If
    seed-from-ground + the typed walker isolate correctly, the is_a query cost stays ~flat and
    equal to the clean-graph cost — the other relations are just clutter the matcher skips.

  PROBE B — DENSE + CYCLIC relation. WordNet adjective `similar_to` is SYMMETRIC (cyclic) and
    CLUSTERED (components up to ~147 nodes). Walk it. This exposes the walker's OVER-EXPLORATION:
    it advances a BFS wavefront over everything reachable until fuel runs out, so per-query work
    is proportional to the connected COMPONENT, not to the target's distance — and a `fuel` below
    the component's reach can FUEL-STARVE (a false negative, a correctness risk, not just slow).
    This is the data that motivates a stop-on-arrival guard.

Run:  python bench/wordnet_messy.py
"""
from __future__ import annotations

import random
import statistics
import time
from collections import defaultdict, deque
from dataclasses import dataclass

import harneskills as h
from harneskills import demand, walker
from harneskills.rewriter import run as rw_run

try:                                              # robust to both invocation styles
    from bench.wordnet_scaling import (
        load_noun_synsets, ancestor_closure, hypernyms, fmt_row, pick_anchors, make_probes)
except ImportError:
    from wordnet_scaling import (
        load_noun_synsets, ancestor_closure, hypernyms, fmt_row, pick_anchors, make_probes)

SEED = 12345

NOUN_RELATIONS = {                                # relation name in the graph -> synset method
    "is_a": lambda s: hypernyms(s),
    "part_of": lambda s: s.part_meronyms(),
    "member_of": lambda s: s.member_meronyms(),
    "substance_of": lambda s: s.substance_meronyms(),
}


# ---------------------------------------------------------------------------
# Graph builders
# ---------------------------------------------------------------------------

def build_noun_multigraph(synset_set: set):
    """One node per synset; edges for every NOUN_RELATIONS type whose endpoints are both in
    the set. The `is_a` subgraph is identical to the clean probe — the rest is clutter."""
    g = h.Graph()
    ids = {s: g.add_node(s.name()) for s in synset_set}
    n_edges = defaultdict(int)
    for s in synset_set:
        for rel, getter in NOUN_RELATIONS.items():
            for t in getter(s):
                if t in ids:
                    g.add_relation(ids[s], rel, ids[t])
                    n_edges[rel] += 1
    return g, ids, dict(n_edges)


def build_similar_graph(adj_subset: set):
    """Adjective `similar` graph — SYMMETRIC (both directions wired), so it is cyclic and
    clustered. Returns (graph, {synset: id}, adjacency dict for ground-truth BFS)."""
    g = h.Graph()
    ids = {s: g.add_node(s.name()) for s in adj_subset}
    adjc: dict = defaultdict(set)
    for s in adj_subset:
        for t in s.similar_tos():
            if t in ids:
                adjc[s].add(t)
                adjc[t].add(s)
    for s, neighbours in adjc.items():
        for t in neighbours:
            if t in adjc.get(s, ()):                       # wire each undirected edge as s->t
                g.add_relation(ids[s], "similar", ids[t])
    return g, ids, adjc


# ---------------------------------------------------------------------------
# A general on-demand walk (mirrors walk_on_demand, returns the journal + reached size)
# ---------------------------------------------------------------------------

def walk_rel(g: h.Graph, subj: str, obj: str, *, rel: str, fuel: int):
    """Seed a demand and run the typed walker for `rel` (is_a uses the CNL bank, others the
    parameterised Python rules), seeded from the demand's locality. Returns the firing journal."""
    d = demand.seed_demand(g, subj, obj)
    amt = g.nodes_named(str(fuel))
    g.add_relation(d, walker.AMOUNT, amt[0] if amt else g.add_node(str(fuel)))
    rules = (walker.load_walker_rules() if rel == "is_a"
             else walker.DEMAND_WALK + walker.SPAWN_RULES + walker.walk_rules(rel))
    return rw_run(g, rules, tools=walker.WALK_TOOLS, seeds=[d, *g.within([d], 1)])


def has_rel(g: h.Graph, subj: str, obj: str, rel: str) -> bool:
    objs = set(g.nodes_named(obj))
    for s in g.nodes_named(subj):
        for r, o in g.relations_from(s):
            if g.name(r) == rel and o in objs:
                return True
    return False


def reached_size(g: h.Graph) -> int:
    """How many nodes the walker reached — the over-exploration metric (= component explored)."""
    ws = g.nodes_named(walker.WALKER)
    if not ws:
        return 0
    return sum(1 for r, _ in g.relations_from(ws[0]) if g.name(r) == walker.REACHED)


@dataclass
class MR:
    answer: bool
    correct: bool
    seconds: float
    firings: int
    reached: int


def run_rel_query(g: h.Graph, subj: str, obj: str, *, rel: str, fuel: int, expect: bool) -> MR:
    gq = g.copy()
    t0 = time.perf_counter()
    journal = walk_rel(gq, subj, obj, rel=rel, fuel=fuel)
    dt = time.perf_counter() - t0
    ans = has_rel(gq, subj, obj, rel)
    return MR(ans, ans == expect, dt, len(journal), reached_size(gq))


def summarize_mr(results: list[MR]) -> dict:
    secs = sorted(r.seconds for r in results)
    return {
        "n": len(results),
        "correct": sum(r.correct for r in results),
        "median_ms": statistics.median(secs) * 1000,
        "p90_ms": secs[min(len(secs) - 1, int(0.9 * len(secs)))] * 1000,
        "median_firings": int(statistics.median([r.firings for r in results])),
        "median_reached": int(statistics.median([r.reached for r in results])),
    }


def fmt_mr(label, s) -> str:
    return (f"{label:>16} | {s['n']:>3} q | correct {s['correct']:>3}/{s['n']:<3} | "
            f"median {s['median_ms']:8.2f} ms | firings {s['median_firings']:>4} | "
            f"reached {s['median_reached']:>4}")


# ---------------------------------------------------------------------------
# Probe A — clutter / matcher isolation
# ---------------------------------------------------------------------------

def probe_a(synsets, *, fuel: int):
    print("\n=== PROBE A — typed is_a walk on the MULTI-relation graph (clutter isolation) ===")
    anchors = pick_anchors(synsets, min_depth=13, k=40)
    rng = random.Random(SEED)
    for f in [0.1, 0.3, 1.0]:
        sample = rng.sample(synsets, k=int(f * len(synsets)))
        subset = ancestor_closure(set(sample) | set(anchors))
        g, _, edges = build_noun_multigraph(subset)
        probes = make_probes(anchors, depth=8, negatives=[s for s in subset if s not in set(anchors)])
        results = [run_rel_query(g, p.subj, p.obj, rel="is_a", fuel=fuel, expect=p.positive)
                   for p in probes]
        tag = f"N={len(g)}"
        print(fmt_mr(tag, summarize_mr(results)), f"| edges={sum(edges.values())} {edges}")


# ---------------------------------------------------------------------------
# Probe B — dense + cyclic `similar` walk
# ---------------------------------------------------------------------------

def _components(adjc: dict) -> list[list]:
    seen, comps = set(), []
    for s in adjc:
        if s in seen:
            continue
        q, comp = deque([s]), []
        seen.add(s)
        while q:
            x = q.popleft(); comp.append(x)
            for y in adjc[x]:
                if y not in seen:
                    seen.add(y); q.append(y)
        comps.append(comp)
    return comps


def _bfs_dist(adjc: dict, src, dst) -> int | None:
    if src == dst:
        return 0
    q, seen = deque([(src, 0)]), {src}
    while q:
        x, d = q.popleft()
        for y in adjc[x]:
            if y == dst:
                return d + 1
            if y not in seen:
                seen.add(y); q.append((y, d + 1))
    return None


def probe_b(*, fuels: list[int]):
    from nltk.corpus import wordnet as wn
    print("\n=== PROBE B — dense + cyclic `similar` walk (over-exploration + fuel-starvation) ===")
    adjs = list(wn.all_synsets("a")) + list(wn.all_synsets("s"))
    g, ids, adjc = build_similar_graph(set(adjs))
    comps = sorted((c for c in _components(adjc) if len(c) > 1), key=len, reverse=True)
    print(f"   graph: {len(g)} nodes; {len(comps)} similar-components, "
          f"biggest {len(comps[0])}; total nodes in components {sum(len(c) for c in comps)}")

    # Probes: positives at a known BFS distance inside a component; negatives across components.
    rng = random.Random(SEED)
    probes = []                                   # (subj, obj, expect, dist, comp_size)
    for comp in comps[:60]:                       # sample from the larger components
        if len(comp) < 3:
            continue
        a = comp[0]
        far = max(comp[1:], key=lambda x: _bfs_dist(adjc, a, x) or 0)
        dist = _bfs_dist(adjc, a, far)
        probes.append((a.name(), far.name(), True, dist, len(comp)))
        other = rng.choice([c for c in comps if c is not comp])[0]
        probes.append((a.name(), other.name(), False, None, len(comp)))

    for fuel in fuels:
        results = [run_rel_query(g, s, o, rel="similar", fuel=fuel, expect=exp)
                   for (s, o, exp, _d, _cs) in probes]
        s = summarize_mr(results)
        # how many positives were MISSED (fuel-starvation false negatives)?
        pos = [(r, p) for r, p in zip(results, probes) if p[2]]
        missed = sum(1 for r, p in pos if not r.answer)
        print(fmt_mr(f"fuel={fuel}", s), f"| positives missed (starved) {missed}/{len(pos)}")
    # show the over-exploration: reached vs the small target distances
    dists = [p[3] for p in probes if p[2] and p[3] is not None]
    print(f"   positive target BFS distances: min {min(dists)}, median "
          f"{int(statistics.median(dists))}, max {max(dists)} -- yet the walk reaches the whole "
          f"component (see 'reached' above): work ~ component size, not target distance.")


def main() -> None:
    print("loading WordNet ...")
    _wn, synsets = load_noun_synsets()
    probe_a(synsets, fuel=50)
    probe_b(fuels=[50, 200])


if __name__ == "__main__":
    main()
