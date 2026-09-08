"""`market` -- apples on a shelf, the second toy domain this pilot uses
to test whether "the big one" (`context.BigRequest`) means anything to a
domain that has never heard of `fs`. Same standing as
`loopingrules/examples/shopping.py`: kept here, not shipped, a data point
rather than a real domain.

## What this is testing

`harneskills.examples.context`'s `BigRequest`/`Candidate` pattern needs a
SECOND domain, oblivious of `fs`, or it proves nothing about cross-domain
arbitration -- one domain proposing against its own occasion is just
`fs.arbitrate_parse` under another name. `propose_big`, below, is
deliberately as simple as `fs.propose_big`: unconditional and structural,
no per-line parsing at all -- this domain always has an opinion about
"the biggest apple," the same way `fs` always has one about "the biggest
file," and never checks whether the OTHER domain might disagree. That is
`context.rank_by_confidence`'s job, not this module's.
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
class WantBiggest:
    """The candidate's own goal component -- "answer with the heaviest
    item on the shelf" -- real once `Proposal` is detached, same trick
    every `fs` goal already plays."""


#: Grams, not realistic produce weights -- big enough to be visibly
#: ordered, nothing more.
DEFAULT_ITEMS = (("gala", 120), ("granny smith", 150), ("honeycrisp", 180))


def _find_item(w, name: str):
    """The `Item` entity named `name`, case-insensitively, or `None` --
    same discipline as `examples.shopping._find_item`: `install` never
    seeds a duplicate name, and nothing else here spawns an `Item`."""
    for entity, item in w.all(Item):
        if item.name.lower() == name.lower():
            return entity
    return None


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


def propose_big(w) -> None:
    """Every `context.BigRequest` -> a candidate carrying `WantBiggest`,
    tagged with this domain's OWN confidence -- `context.py`'s "Level 1"
    made concrete: one ruleset, one already-ranked candidate, computed
    without knowing `fs` exists."""
    for occasion, _request in w.each(context.BigRequest):
        propose(w, occasion, WantBiggest(),
                context.Candidate("market", context.confidence(w, "market")))


def reply_biggest(w) -> None:
    """The winning `WantBiggest` -> the heaviest item, once `Proposal`
    is gone (arbitration is done) -- and a fresh `context.note`, same as
    `hear_produce`'s: this is a real market answer too, not just a
    listing."""
    for entity, _want in w.each(WantBiggest, without=Proposal):
        w.destroy(entity)
        weighed = [(item, w.get(item_entity, Weight)) for item_entity, item in w.all(Item)]
        weighed = [(item, weight) for item, weight in weighed if weight is not None]
        if not weighed:
            reply(w, "no produce to compare")
            continue
        item, weight = max(weighed, key=lambda pair: pair[1].grams)
        reply(w, "%s (%d g)" % (item.name, weight.grams))
        context.note(w, "market")


RULES = (hear_produce, propose_big, reply_biggest)


def install(loop, catalog=DEFAULT_ITEMS) -> None:
    """Register every rule above, then seed the catalog -- same
    "never touch an entry already there" policy `examples.shopping
    .install` gives its own `Item`s."""
    for rule in RULES:
        loop.rule(rule)
    world = loop.world
    for name, grams in catalog:
        if _find_item(world, name) is None:
            entity = world.spawn(Item(name))
            world.attach(entity, Weight(grams))
    world.learn("show", "apples")
