"""`context` -- a trail of turns, and how sure two independently-installed
domains should be that a since-established topic is still what an
ambiguous phrase refers to.

    python -m harneskills harneskills.examples.context:install

## What this is testing

`docs/intake processing.md` already has one precedent for two
independently-installed domains competing for a SHARED occasion --
`loopingrules.help`'s `HelpTopic`/`HelpCommandCensus`, arbitrated by
`loopingrules.world.arbitrate` because neither `fs` nor `pystrider` has
any ordering relationship with the other's `install()`. `help` never
needed more than "first proposal wins," because a topic name IS the
disambiguation -- `help files` and `help python` are already disjoint
strings before either domain's responder ever runs.

`"the big one"` is not disjoint from anything -- it is the same three
words whether you were just looking at files or produce, and nothing
about its OWN text says which. `"the X one"` is the general shape: `X`
is a QUALIFIER (`big`, `red`, ...), and this module is the shared
occasion for all of them -- any domain that wants a turn at one imports
this, tags its candidate with `Candidate(domain, confidence)`, and lets
`rank_by_confidence` (below) pick using a TRAIL of turns rather than
either domain's own say-so.

## Domain eligibility is a hard gate, not a soft score

`"red"` means nothing to `fs` -- there is no `Color` component on an
`Entry`, and there never should be one just to answer this. That is not
a confidence-of-zero case; it is not a candidate at all. A domain that
has no reading of a qualifier simply never calls `propose` for it --
the same `continue`-if-I-don't-recognize-this discipline every
`propose_*` rule in `fs.py` already uses (`after_threshold`'s "no digit
token where a threshold needs one -> nothing composes" is the same
move). `DECISION_PATTERNS.md`'s own vocabulary names the distinction:
eligibility is `ruled_out`-shaped (categorical, decided once, per
domain, before anything is compared), confidence is `ranked`-shaped
(soft, decided by `rank_by_confidence`, only among candidates that
already exist). `"the red one"` asked right after a long conversation
about files still means the apple: `fs` was never in the contest,
regardless of what the trail says.

## No singleton "current topic"

An earlier draft of this pilot kept one `Topic` component, `replace`d
every time a domain resolved something -- "whatever we last talked
about." That collapses the trail the moment a second exchange happens:
there is no way to ask "how long ago was this about files" once the
answer to "about files at all" is a single overwritten bit.

`Turn`, below, is what `record_intake`/`record_outtake` wrap every
`Said`/`Reply` into -- a persistent entity, one per line either
direction, never destroyed by this module. `Topic(domain)` is attached
to a TURN, not replaced on a singleton, by `note()` -- so the trail
(`w.each(Turn, Topic)`) only ever grows, and `confidence()` can ask "how
many turns back was `domain` last true" instead of "is it true right
now."

## Two-level arbitration

Level 1 -- a ruleset ranking its OWN rival interpretations down to one,
with its own confidence -- is each domain's own business, the exact seam
`fs.arbitrate_parse` already is for a single domain's `ParseRequest`.
Neither `fs` nor `market` has genuine internal rivalry for any ONE
qualifier today (each maps a qualifier it understands to exactly one
reading), so neither builds an arbiter for it -- but each still computes
its OWN `confidence()` and attaches it to its own single candidate,
which IS level 1, trivially satisfied rather than skipped. A domain
that ever gains a second reading of the SAME qualifier (`market`, if
two apples were ever both "the red one") adds a small arbiter ahead of
where it calls `propose`, same as any other real collision in this
codebase -- not built here, because none exists yet.

Level 2 is `rank_by_confidence`, below -- the only judge this module
owns: given at most one already-ranked candidate per domain, keep only
whichever has the highest confidence. A tie (most commonly `0.0`/`0.0`,
before any topic has ever been noted) leaves every tied candidate
standing, falling through to `loopingrules.world.arbitrate`'s own
"first registered wins" -- the same honest, undesigned-past-here default
`fs.arbitrate_parse`'s own docstring already takes for "nobody proposed
a reading."
"""

from __future__ import annotations

from dataclasses import dataclass

from loopingrules.world import Proposal, Reply, Said, arbitrate, propose, reply

#: How many INTAKE turns back a noted topic's confidence decays to zero
#: -- the pilot's one tuned constant. Linear, capped at both ends, the
#: same shape `examples.shopping.project_urgency` already uses for time
#: pressure ("cap, don't extrapolate past the meaningful range").
TOPIC_HORIZON = 5


@dataclass(frozen=True)
class Turn:
    """One line, either direction. `seq` is "how many turns of this
    SAME `kind` came before it" at record time -- no counter entity
    needed, since `w.each(Turn)` is already the whole history. Never
    destroyed by this module: the trail IS the point."""

    seq: int
    kind: str   # "intake" | "outtake"
    text: str


@dataclass(frozen=True)
class _Recorded:
    """This module's own bookkeeping, not shared vocabulary -- marks the
    ORIGINAL `Said`/`Reply` as already wrapped in a `Turn`, the same
    standing `loopingrules.world`'s own `_Ripe` has for `arbitrate`/
    `census`. Without this, a `Reply` left undrained across ticks (see
    `loopingrules.engine`) would grow a fresh, duplicate `Turn` every
    tick it lingers, and the world would never settle."""


@dataclass(frozen=True)
class Topic:
    """A trace, not a value: "this TURN was about `domain`." Attached to
    a `Turn` entity by `note()`, below -- never replaced on a singleton,
    so several turns can each carry their own, over time."""

    domain: str


@dataclass(frozen=True)
class QualifiedRequest:
    """The shared occasion: someone said `"the <qualifier> one"`.
    `qualifier` is the bare word (`"big"`, `"red"`, ...), lowercased,
    uninterpreted -- this module never decides what a qualifier MEANS,
    only routes it to whichever domains choose to propose against it.
    See this module's own docstring, "Domain eligibility is a hard
    gate," above."""

    qualifier: str


@dataclass(frozen=True)
class Candidate:
    """Rides alongside `loopingrules.world.Proposal` and a domain's own
    goal component on a candidate entity. The only thing THIS module
    needs to know about a candidate -- never `fs.HuntHere` versus
    whatever `market.py` proposes."""

    domain: str
    confidence: float


def _next_seq(w, kind: str) -> int:
    return sum(1 for _entity, turn in w.each(Turn) if turn.kind == kind)


def _latest_intake_seq(w):
    seqs = [turn.seq for _entity, turn in w.each(Turn) if turn.kind == "intake"]
    return max(seqs) if seqs else None


def note(w, domain: str) -> None:
    """The most recent INTAKE turn was about `domain` -- called by a
    domain once it has actually resolved something (`fs.list_dir`,
    `market.reply_qualified`), never by this module on a domain's
    behalf.
    A no-op before any intake turn exists at all (nothing recorded yet
    to tag)."""
    intakes = [(entity, turn.seq) for entity, turn in w.each(Turn) if turn.kind == "intake"]
    if not intakes:
        return
    entity, _seq = max(intakes, key=lambda pair: pair[1])
    w.attach(entity, Topic(domain))


def confidence(w, domain: str) -> float:
    """`1.0` if `domain` was noted on the CURRENT intake turn itself,
    decaying linearly to `0.0` by `TOPIC_HORIZON` turns back. `0.0` if
    `domain` was never noted at all -- refusing to invent confidence in
    a topic nobody ever established, the same discipline
    `examples.shopping`'s `NeededBy` already uses ("no deadline, no
    urgency at all")."""
    now = _latest_intake_seq(w)
    if now is None:
        return 0.0
    matches = [turn.seq for _entity, turn, topic in w.each(Turn, Topic)
               if topic.domain == domain]
    if not matches:
        return 0.0
    distance = now - max(matches)
    return max(0.0, 1.0 - distance / TOPIC_HORIZON)


def record_intake(w) -> None:
    """Every `Said` not yet `_Recorded` -> a `Turn("intake", ...)`.
    HIGH priority (see `install`) -- ABOVE `hear_qualified`, `fs.hear`
    and `loopingrules.help.hear_help` (all `<=50`), so a turn is
    captured before whichever domain claims or destroys the `Said` that
    carried it."""
    for entity, said in w.each(Said, without=_Recorded):
        w.attach(entity, _Recorded())
        w.spawn(Turn(_next_seq(w, "intake"), "intake", said.text))


def record_outtake(w) -> None:
    """Same idea, for replies. Default priority -- nothing destroys a
    `Reply` the same tick it is spawned, so there is no race to win
    here the way `record_intake` has one."""
    for entity, said in w.each(Reply, without=_Recorded):
        w.attach(entity, _Recorded())
        w.spawn(Turn(_next_seq(w, "outtake"), "outtake", said.text))


def hear_qualified(w) -> None:
    """`Said("the <qualifier> one")` -> `QualifiedRequest(qualifier)`,
    and the `Said` is claimed immediately -- one shape, exactly three
    words, not fuzzy matching (`"do one concretely first"`): this rule
    only recognizes the SENTENCE, never the qualifier itself -- that is
    every domain's own, separate business (see this module's docstring,
    "Domain eligibility is a hard gate"). HIGH priority (see `install`),
    the same reasoning as `loopingrules.help.hear_help`'s own docstring:
    must run before `fs.hear`'s "wrap EVERY `Said`" swallows this line
    into a `ParseRequest` no `propose_*` rule recognizes."""
    for entity, said in w.each(Said):
        words = said.text.strip().lower().split()
        if len(words) != 3 or words[0] != "the" or words[2] != "one":
            continue
        w.destroy(entity)
        w.spawn(QualifiedRequest(words[1]))


def rank_by_confidence(w) -> None:
    """Level 2's judge (see this module's own docstring). Among a
    `QualifiedRequest`'s candidates, if two or more exist, destroy every
    one whose `Candidate.confidence` is below the max -- a genuine tie
    leaves every tied candidate standing, for `arbitrate_ambiguous`,
    below, to resolve by plain registration order. A qualifier only ONE
    domain was ever eligible for never reaches this rule with more than
    one candidate at all -- there was nothing to rank."""
    for occasion, _request in w.each(QualifiedRequest):
        rows = [(entity, w.get(entity, Candidate)) for entity, proposal in w.each(Proposal)
                if proposal.occasion == occasion.id]
        tagged = [(entity, candidate) for entity, candidate in rows if candidate is not None]
        if len(tagged) < 2:
            continue
        best = max(candidate.confidence for _entity, candidate in tagged)
        for entity, candidate in tagged:
            if candidate.confidence < best:
                w.destroy(entity)


def arbitrate_ambiguous(w) -> None:
    """One winner per `QualifiedRequest`, via
    `loopingrules.world.arbitrate` -- unmodified and reused as-is,
    correct once `rank_by_confidence` has already done the only
    context-specific pruning. An occasion NO domain was ever eligible
    for (nobody proposed at all -- `"the red one"` with no domain that
    knows red) is said, not swallowed -- the same posture
    `loopingrules.help.arbitrate_help` already takes."""
    for occasion, request in arbitrate(w, QualifiedRequest):
        reply(w, "not sure what \"the %s one\" means" % request.qualifier)


RULES = (record_intake, record_outtake, hear_qualified,
         rank_by_confidence, arbitrate_ambiguous)


def install(loop) -> None:
    """Register this module's five rules. Only `record_intake` and
    `hear_qualified` need a priority -- see their own docstrings;
    `rank_by_confidence`/`arbitrate_ambiguous` need theirs LOW, not for
    correctness (both re-run harmlessly every tick until there is
    nothing left to prune) but so a fresh `QualifiedRequest` always gets
    a full tick of proposers before either looks.

    No `watches=` any more -- `loopingrules.loop`'s own `Loop.rule` took
    that parameter away entirely once it started deriving a rule's
    dormancy gate from `analyze()` itself (that repo's README History,
    "No more hand-written `watches=`"); passing it here raised
    `TypeError` on every one of this module's rules until this dropped
    it. `arbitrate`/`propose`/`reply`, imported directly from
    `loopingrules.world` above, are `analyze()`'s own named exceptions
    (its docstring, "Four named exceptions"), so `arbitrate_ambiguous`
    still gets a real gate out of this, not just the `Opaque` fallback.

    Learns only the SENTENCE shape's own two fixed words -- `"the"` and
    `"one"` -- never a qualifier: which words mean something is each
    domain's own vocabulary to `learn` (`fs.WORDS` already has `"big"`;
    a domain that adds `"red"` adds it there, not here)."""
    loop.rule(record_intake, priority=100)
    loop.rule(record_outtake)
    loop.rule(hear_qualified, priority=50)
    loop.rule(rank_by_confidence, priority=-10)
    loop.rule(arbitrate_ambiguous, priority=-20)
    loop.world.learn("the", "one")
