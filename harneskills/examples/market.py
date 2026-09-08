"""`market` -- apples on a shelf, the second toy domain this pilot uses
to test whether "the X one" (`context.QualifiedRequest`) means anything
to a domain that has never heard of `fs`. Same standing as
`loopingrules/examples/shopping.py`: kept here, not shipped, a data
point rather than a real domain.

## What this is testing

`harneskills.examples.context`'s `QualifiedRequest`/`Candidate` pattern
needs a SECOND domain, oblivious of `fs`, or it proves nothing about
cross-domain arbitration -- one domain proposing against its own
occasion is just `fs.arbitrate_parse` under another name.

It also needs a qualifier `fs` genuinely has no reading for, to prove
domain eligibility is a real gate and not just a `fs`-shaped confidence
race -- `"red"`, below (`Color`, an apple's own vocabulary, has no `fs`
equivalent: a file has no color). `QUALIFIERS`, below, maps each
qualifier this domain understands to how to pick an item for it --
`propose_qualified` is deliberately as simple as `fs.propose_qualified`:
unconditional and structural for whichever qualifiers it knows, no
per-line parsing, and never checks whether `fs` might also have an
opinion. That is `context.rank_by_confidence`'s job, not this module's.
"""

from __future__ import annotations

from dataclasses import dataclass

from loopingrules.world import Proposal, Said, propose, reply

from . import context


@dataclass(frozen=True)
class Item:
    name: str


@dataclass(frozen=True)
class Weight:
    grams: int


@dataclass(frozen=True)
class Color:
    name: str


@dataclass(frozen=True)
class WantQualified:
    """The candidate's own goal component -- "answer 'the `qualifier`
    one'" -- real once `Proposal` is detached, same trick every `fs`
    goal already plays."""

    qualifier: str


#: `(name, grams, color)` -- big enough to be visibly ordered by weight,
#: and exactly ONE red apple, so `"the red one"` has exactly one answer
#: without this module ever needing an internal arbiter (see this
#: module's own docstring on `context.py`'s "Level 1").
DEFAULT_ITEMS = (("gala", 120, "red"), ("granny smith", 150, "green"),
                  ("honeycrisp", 180, "gold"))


def _find_item(w, name: str):
    """The `Item` entity named `name`, case-insensitively, or `None` --
    same discipline as `examples.shopping._find_item`: `install` never
    seeds a duplicate name, and nothing else here spawns an `Item`."""
    for entity, item in w.all(Item):
        if item.name.lower() == name.lower():
            return entity
    return None


def _pick_big(w):
    """The heaviest item, or `None` if nothing is weighed at all --
    refuse rather than guess, same as every other picker below."""
    weighed = [(item, w.get(entity, Weight)) for entity, item in w.all(Item)]
    weighed = [(item, weight) for item, weight in weighed if weight is not None]
    if not weighed:
        return None
    item, weight = max(weighed, key=lambda pair: pair[1].grams)
    return "%s (%d g)" % (item.name, weight.grams)


def _pick_red(w):
    """The one red item, or `None` if there is none -- or more than
    one: `"the red one"` presupposes exactly one, and a genuine tie is
    this domain's own honest gap, not a coin flip."""
    reds = [item for entity, item in w.all(Item)
            if w.has(entity, Color) and w.get(entity, Color).name == "red"]
    return reds[0].name if len(reds) == 1 else None


#: This domain's own vocabulary of `"the X one"` -- grown one entry at a
#: time, the same restraint `fs.FS_QUALIFIERS` uses. Each picker reads
#: `w` fresh and returns text to say, or `None` for "no answer" (never
#: raises, never guesses).
QUALIFIERS = {"big": _pick_big, "red": _pick_red}


def hear_produce(w) -> None:
    """`show apples` -> one line per item, then `context.note` -- the
    market-side "we were just talking about this" signal, same job
    `fs.list_dir`'s own `context.note` call does."""
    for entity, said in w.each(Said):
        if said.text.strip().lower() != "show apples":
            continue
        w.destroy(entity)
        lines = []
        for item_entity, item in sorted(w.all(Item), key=lambda row: row[1].name):
            weight = w.get(item_entity, Weight)
            lines.append("%s (%d g)" % (item.name, weight.grams) if weight else item.name)
        reply(w, "; ".join(lines) if lines else "no produce")
        context.note(w, "market")


def propose_qualified(w) -> None:
    """Every `context.QualifiedRequest` this domain has a reading for
    (`QUALIFIERS`) -> a candidate carrying `WantQualified`, tagged with
    this domain's OWN confidence -- `context.py`'s "Level 1" made
    concrete: one ruleset, one already-ranked candidate, computed
    without knowing `fs` exists."""
    for occasion, request in w.each(context.QualifiedRequest):
        if request.qualifier not in QUALIFIERS:
            continue
        propose(w, occasion, WantQualified(request.qualifier),
                context.Candidate("market", context.confidence(w, "market")))


def reply_qualified(w) -> None:
    """The winning `WantQualified` -> whatever its own qualifier's
    picker says, once `Proposal` is gone (arbitration is done) -- and a
    fresh `context.note`, same as `hear_produce`'s: this is a real
    market answer too, not just a listing."""
    for entity, want in w.each(WantQualified, without=Proposal):
        w.destroy(entity)
        text = QUALIFIERS[want.qualifier](w)
        if text is None:
            reply(w, "not sure which one is %s" % want.qualifier)
            continue
        reply(w, text)
        context.note(w, "market")


RULES = (hear_produce, propose_qualified, reply_qualified)


def install(loop, catalog=DEFAULT_ITEMS) -> None:
    """Register every rule above, then seed the catalog -- same
    "never touch an entry already there" policy `examples.shopping
    .install` gives its own `Item`s."""
    for rule in RULES:
        loop.rule(rule)
    world = loop.world
    for name, grams, color in catalog:
        if _find_item(world, name) is None:
            entity = world.spawn(Item(name))
            world.attach(entity, Weight(grams), Color(color))
    world.learn("show", "apples", *QUALIFIERS)
