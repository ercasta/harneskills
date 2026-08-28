"""A small, domain-general prototype of `docs/decision_patterns.md`: propose
candidates as plain facts, justify them in a vocabulary a judge can reason
about at a distance, arbitrate over the whole set with ONE generic reader,
run to a fixpoint. See that note for the argument; this is the vocabulary
made runnable.

⭐ Nothing here is specific to Python or to code. An OCCASION is any entity a
caller mints (`f.node("dessert")`, or an interned `f.word("decision:screen")`
— this module does not care). Every relation below is read generically by
`commit`, regardless of how many judges propose, justify, rank, or rule
candidates out for it: a new judge is a new system on the loop and changes
nothing here.

⭐ WHY THIS SHIPS IN `ugm` RATHER THAN IN THE DOMAIN THAT NEEDED IT. Every
piece was extracted from a working domain (`pystrider`, which reads and
writes Python on this world), and the reason it did not stay there is what
that domain measured before the extraction: with each rule family deciding
FOR ITSELF whether to fire, two repairs both fired on one bug and the answer
was correct by luck. Agency in the base rule does not compose — on a loop
that runs every system every tick, a rule with an opinion about its rivals is
a rule with an opinion about registration order. So the arbitration lives in
ONE generic reader over the candidate set, and a domain that skips it is not
choosing a simpler design, it is choosing that bug. That is the sense in
which a `ugm` user should comply with this file.

⚠ WHAT THIS MODULE DELIBERATELY DOES NOT DO: there is no `needs`/`deferred`
relation here, and that is the point rather than a gap. A judge that needs
more information before it can rank or rule on a candidate asserts an
ordinary fact (see the pricing example in `tests/test_arbitration.py`) and
whatever answers it is some other, unrelated system — `commit` needs no
code at all to support this, because unblocking is just "the guard read
false, now it reads true," the same as every system, always. Baking `needs`
in here would be inventing goal machinery for a case that does not need any.

⚠⚠ HARD BEATS SOFT, STRUCTURALLY, NOT BY CONVENTION. `commit` computes
`eligible` (candidates minus `ruled_out`) BEFORE it ever looks at `ranked`,
so a candidate a hard judge vetoed cannot win by out-scoring a survivor —
"pizza or nothing? you're on a diet, so nothing" reads exactly this way:
the diet judge's veto is consulted first, the preference ranking pizza
already won on never gets a say once pizza is gone.
"""
from __future__ import annotations

from .facts import Facts, relation

Candidate = relation("candidate")
Realizes = relation("realizes")
RuledOut = relation("ruled_out")
Ranked = relation("ranked")
Winner = relation("winner")
Verdict = relation("verdict")


def realizes_closure(f: Facts):
    """The transitive closure of `realizes` — `pizza realizes deep_dish`,
    `deep_dish realizes junk_food` => `pizza realizes junk_food` — so a
    judge authored against `junk_food` reaches `pizza` without ever being
    told `deep_dish` exists. An ordinary system reading its own conclusion at
    a fixpoint — the same shape as propagating anything else transitively
    (an effect across a call graph, a reachability across a tree), narrowed
    to one named relation.
    """

    def system(world) -> None:
        for option, held in list(world.each(Realizes)):
            for (property_,) in [r for r in held.rows if len(r) == 1]:
                for row in f.of("realizes", property_):
                    if len(row) != 1:
                        continue
                    further = row[0]
                    if not f.holds("realizes", option, further):
                        f.fact("realizes", option, further)

    return system


def commit(f: Facts):
    """The one generic reader, for every occasion any judge proposed a
    `candidate` for.

    ⚠ Refuses to guess, the same discipline `facts.one()` already uses: a tie
    for the top rank among survivors is reported (`ambiguous`), never broken by
    iteration order. An occasion
    with no eligible survivor is `unresolved` — including when every
    candidate was ruled out — never a silently-picked default; an author
    who wants a fallback proposes it as an ordinary candidate that happens
    to survive every veto, rather than teaching this reader about defaults.
    """

    def system(world) -> None:
        for occasion, held in world.each(Candidate):
            options = [row[0] for row in held.rows if len(row) == 1]
            if not options:
                continue
            ruled_out = {row[0] for row in f.of("ruled_out", occasion) if len(row) == 2}
            eligible = [o for o in options if o not in ruled_out]
            current = f.one("winner", occasion)
            if not eligible:
                # ⚠ A candidate can go from winning to ruled-out on a LATER
                # tick (another judge fires after this one settled once) --
                # `state()` alone only replaces `verdict`, it does not clear
                # a `winner` from a tick where the answer was different.
                # Any reader that republishes a single answer has this
                # shape: `deny` whatever is not the (possibly new) winner.
                if current is not None:
                    f.deny("winner", occasion, current)
                f.state("verdict", occasion, f.word("unresolved"))
                continue
            scores = {row[0]: f.payload(row[1])
                      for row in f.of("ranked", occasion) if len(row) == 2}
            best = max((scores.get(o, 0) for o in eligible), default=0)
            top = [o for o in eligible if scores.get(o, 0) == best]
            if len(top) == 1:
                f.state("winner", occasion, top[0])
                f.state("verdict", occasion, f.word("forced"))
            else:
                if current is not None:
                    f.deny("winner", occasion, current)
                f.state("verdict", occasion, f.word("ambiguous"))

    return system


#: ⭐ The two pieces, in one place, so a caller can install a SUBSET — for
#: the ordinary reason a domain offers that knob: proving `realizes_closure`
#: in isolation from arbitration, or vice versa.
DESCRIPTIONS = {"realizes_closure": realizes_closure, "commit": commit}


def install(loop, f: Facts, only=None) -> None:
    """Register the pieces. `only` names a subset, for a control."""
    for name, make in DESCRIPTIONS.items():
        if only is None or name in only:
            f.system(make(f), name=f"arbitration.{name}")
