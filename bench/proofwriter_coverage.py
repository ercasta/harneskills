"""
Coverage probe — ProofWriter (the grammar + multi-step-reasoning axis).

The WordNet probes tested PERFORMANCE on data we didn't author. This tests REASONING on
LOGIC we didn't author: ProofWriter (Tafjord et al. 2021) is a held-out benchmark of synthetic
theories — facts + if/then rules — with entailment questions stratified by REASONING DEPTH
(QDep 0..5) under the closed-world assumption (negation-as-failure).

We express each ProofWriter theory in harneskills' OWN substrate — facts as relations, rules as
`HEAD when COND and COND` (`not` for negated conditions) loaded through the real machine-rule
grammar — then forward-chain (`run_rules`, stratified negation) and answer each question by
PROVABILITY (CWA: provable => true; not provable => false). So this exercises the actual engine
+ rule grammar on problems it has never seen, and measures accuracy as a function of depth.

Scope of this slice (honest): negated CONDITIONS in rule bodies are handled (NAC); negated
CONCLUSIONS and explicitly-negative base facts are NOT yet (rules with a negative head are
SKIPPED and counted — see the coverage line). So it is exact on the positive-Horn + NAF-question
fragment, and reports where it punts.

Run:  python bench/proofwriter_coverage.py
"""
from __future__ import annotations

import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path

import harneskills as h
from harneskills.machine_rules import load_machine_rules

ZIP = Path(r"C:\Users\ercas\AppData\Local\Temp\claude\C--Users-ercas-creazioni-harneskills"
           r"\66d3fcf7-9bca-4f56-9cb8-eb5074afaad2\scratchpad\pw.zip")
ROOT = "proofwriter-dataset-V2020.12.3"

# A ProofWriter atom: ("subj" "pred" "obj" POL) where POL is + (positive), - (negated, in
# facts/questions/conclusions) or ~ (negation-as-failure, in rule bodies). Both - and ~ negate.
ATOM = re.compile(r'\(\s*"([^"]*)"\s+"([^"]*)"\s+"([^"]*)"\s+"([+\-~])"\s*\)')
NEG = {"-", "~"}
VARS = {"something", "someone", "somebody", "somewhere", "anything", "anyone"}


def _san(name: str) -> str:
    """Normalize an entity/attribute name so FACTS and RULES refer to the same node. Two
    independent gotchas the probe surfaced: (1) multi-word names ("bald eagle") must be ONE
    token — the rule CNL is whitespace-tokenized, so a space splits the entity; (2) the
    machine-rule grammar LOWERCASES its literals, so a proper noun ("Gary") in a fact would
    never match the rule's `gary`. Underscore-join + lowercase fixes both."""
    return name.replace(" ", "_").lower()


def _tok(name: str) -> str:
    """Map a ProofWriter atom slot to a harneskills token: `something` -> the rule variable
    `?x`; everything else is a (space-sanitized) literal."""
    return "?x" if name in VARS else _san(name)


def _triple(atom: tuple[str, str, str, str]) -> tuple[str, str, str]:
    """A ProofWriter atom -> a harneskills (subject, predicate, object) triple. An ATTRIBUTE
    atom `(x "is" attr)` becomes `x --attr--> yes` — the ATTRIBUTE WORD is the predicate, so each
    attribute is its OWN predicate. (Collapsing them all to one `attr` predicate created a
    self-negation cycle — `X is cold when not X is red` would be NAC-on-attr + head-attr — which
    stratification can't separate; ProofWriter's closed world is per-attribute.) A verb atom
    `(x verb y)` stays `x --verb--> y`."""
    s, p, o, _pol = atom
    if p == "is":
        return _tok(s), _san(o), "yes"
    return _tok(s), _san(p), _tok(o)


def _clause(atom: tuple[str, str, str, str]) -> str:
    return "{} {} {}".format(*_triple(atom))


def iter_records(member: str, limit: int):
    with zipfile.ZipFile(ZIP) as z, z.open(member) as f:
        for i, line in enumerate(f):
            if i >= limit:
                break
            yield json.loads(line)


def load_theory(record) -> tuple[h.Graph, int]:
    """Build the substrate graph for a record: assert positive facts as relations and load the
    positive-Horn rules through the machine-rule grammar. Returns (graph, n_skipped_rules)
    where skipped = rules with a negated CONCLUSION (this slice does not assert negatives)."""
    g = h.Graph()

    def node(name: str) -> str:
        got = g.nodes_named(name)
        return got[0] if got else g.add_node(name)

    for _tid, t in record.get("triples", {}).items():
        m = ATOM.search(t["representation"])
        if not m:
            continue
        if m.group(4) == "+":                           # negative base facts: NAF handles them
            ts, tp, to = _triple(m.groups())
            g.add_relation(node(ts), tp, node(to))

    rule_lines, skipped = [], 0
    for _rid, r in record.get("rules", {}).items():
        rep = r["representation"]
        left, _, right = rep.partition("->")
        conds = ATOM.findall(left)
        concl = ATOM.findall(right)
        if not concl:
            continue
        if concl[0][3] in NEG:                           # negated head: not in this slice
            skipped += 1
            continue
        body = " and ".join(("not " if c[3] in NEG else "") + _clause(c) for c in conds)
        head = _clause(concl[0])
        rule_lines.append(f"{head} when {body}" if body else head)

    # The MACHINE-rule grammar (not the prose `load_rules`, which silently drops these
    # arbitrary-relation / negated conditions — a real coverage gap this probe surfaced).
    rules = load_machine_rules("\n".join(rule_lines)) if rule_lines else []
    h.run_rules(g, rules)
    return g, skipped


def provable(g: h.Graph, atom: tuple[str, str, str, str]) -> bool:
    s, pred, o = _triple(atom)
    objs = set(g.nodes_named(o))
    return any(g.name(rn) == pred and ob in objs
               for si in g.nodes_named(s) for rn, ob in g.relations_from(si))


def main(per_depth: int = 200) -> None:
    print("ProofWriter coverage probe — reasoning on held-out theories, CWA, by depth\n")
    datasets = ["depth-0", "depth-1", "depth-2", "depth-3", "depth-5"]
    grand = defaultdict(lambda: [0, 0])                 # QDep -> [correct, total]
    for ds in datasets:
        member = f"{ROOT}/CWA/{ds}/meta-test.jsonl"
        by_qdep = defaultdict(lambda: [0, 0])
        neg_head = theories = q_total = unstrat = 0
        for rec in iter_records(member, per_depth):
            theories += 1
            try:
                g, skipped = load_theory(rec)
            except Exception:                           # not stratifiable (negation cycle):
                unstrat += 1                            # the engine refuses it (vision §5/§11)
                continue
            neg_head += skipped
            for _qid, q in rec.get("questions", {}).items():
                m = ATOM.search(q["representation"])
                if not m:
                    continue
                atom = m.groups()
                pol = atom[3]
                pred_true = provable(g, atom)
                predicted = pred_true if pol == "+" else (not pred_true)
                ok = (predicted == bool(q["answer"]))
                d = q.get("QDep", 0)
                by_qdep[d][0] += ok
                by_qdep[d][1] += 1
                grand[d][0] += ok
                grand[d][1] += 1
                q_total += 1
        acc = sum(c for c, _ in by_qdep.values()) / max(1, sum(t for _, t in by_qdep.values()))
        per = " ".join(f"d{d}:{c}/{t}" for d, (c, t) in sorted(by_qdep.items()))
        print(f"{ds:>9} | {theories:>4} theories ({unstrat} unstratifiable, skipped), {q_total:>5} Q "
              f"| acc {acc:6.1%} | neg-head rules dropped {neg_head:>3} | {per}")

    print("\n=== overall accuracy by reasoning depth (all datasets) ===")
    for d, (c, t) in sorted(grand.items()):
        print(f"  QDep {d}: {c/max(1,t):6.1%}  ({c}/{t})")
    tot_c = sum(c for c, _ in grand.values()); tot_t = sum(t for _, t in grand.values())
    print(f"  TOTAL: {tot_c/max(1,tot_t):6.1%}  ({tot_c}/{tot_t})")


if __name__ == "__main__":
    main()
