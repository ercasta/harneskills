"""Propositions over the world: the vocabulary a domain on `ugm` reasons in.

`world.py` gives entities and components; `loop.py` runs systems over them until
nothing changes. That is enough to build anything and not enough to build it the
same way twice. This module is the layer in between — **a relation is a component
type, its objects are the rows that component carries, and a kind is one empty
row** — and it ships here rather than in each domain because every domain that
re-derived it re-derived the same four hazards with it.

    what a domain wants to say             what it becomes here
    -------------------------------------  ------------------------------------
    `for_stmt(n)`                          `n` carries the `for_stmt` component
    `name(n, f)`                           ... carrying one ROW, `(f,)`
    `stmt(b, s1)`, `stmt(b, s2)`           ... carrying two rows, IN ORDER
    a relation, by name                    a Python CLASS, interned in `relation()`

> ⭐⭐ **A kind, an attribute and an edge are three mechanisms in most rule
> engines and ONE component here.** Nothing distinguishes them but arity.

## ⭐ Why this is not a domain, and belongs in `ugm`

`ugm`'s scope note is that it ships no domain — no files, no sockets, no Python
syntax, no business. That still holds of every line below: `Facts` knows nothing
about what a relation MEANS, only that it is interned by name and its rows are
ordered and deduped. What it does ship is the **discipline** for writing systems,
and that is not optional the way a domain is. A system that writes through
`fact`/`state`/`deny` composes with every other system on the loop; one that
keeps its conclusion in a local variable, or mutates a dict beside the world, is
invisible to `arbitration.commit`, to `save.py`, and to whoever comes next.

## ⚠⚠ The four hazards this layer exists to have already survived

1. **THE TWIN TRAP IS STRUCTURALLY GONE.** A graph substrate that mints a fresh
   node per `atom(name)` call makes a relation built in Python a TWIN of the one
   an authored rule uses: nothing matches, and the run reports a contented
   quiescence having done nothing. It cost four recorded readings. Here a
   relation IS a Python class, interned by name in `_RELATIONS` — two
   `relation("body")` calls are the same object because Python says so, and there
   is no second table to drift from.

2. **THE `no <own conclusion>` PREMISE IS NOT LOAD-BEARING.** An engine with no
   inert set offers an application that changed nothing again, so a rule that did
   not stop itself never stopped — a run burning its whole budget on the first
   applicable rule while every later rule never fired. `Loop` settles on
   `world.revision` and `World.attach` compares before it stores, so **re-deriving
   a fact that already holds is not a change**. Systems still say "only the ones
   not yet described" where that is the honest reading of the query; they no
   longer say it to avoid a hang.

3. **NO HAND-ROLLED INDEX.** `World._by_type` already is one: `of()` is a dict
   lookup, `subjects()` walks one bucket. ⚠ The defect a private index once had is
   worth naming — it saw only what `fact()` wrote, so **a reader could not see
   what a RULE had concluded**. It cannot recur while there is one store.

4. **`word` AND `value` ARE DIFFERENT KINDS OF NODE, and conflating them is a
   silent wrong answer, not a type error.** It is what stores an operator as
   `'gt'` — quoted — so a rule naming the bare `gt` never matches and half a rule
   family is dead while the suite stays green. This distinction is about what a
   symbol MEANS, not how it is stored, so no substrate change retires it.

## ⚠⚠ Systems return deltas, and that is why `_mint` exists

A system does not touch its world (`ugm` 11c459a); it returns a list of deltas and
`Loop.tick` applies them. Every write here goes through `fact`/`state`/`deny`, so
a domain written against this module did not change one line of its own LOGIC when
that contract landed — the whole adaptation lives in this one class.
`fact`/`state`/`deny` accumulate instead of writing; `system()` wraps a registered
function to collect what accumulated and hand it back; `_held` lets a `deny` then a
`fact` on the same `(name, subject)` in one turn see the accumulated write rather
than the world as of the turn's start. The genuinely new piece is `_mint`:
`word`/`value`/`node`/`reify` DESCRIBE a fresh entity rather than making one when
called from inside a system, and since that description resolves only within its own
turn, a LATER turn needing the same text has to find what an EARLIER one already
made real — `_find`, a scan, and the one place this layer pays a cost a
direct-write version did not.
"""
from __future__ import annotations

import ast
import functools
from typing import Any, Dict, List, Optional, Tuple

from .delta import Pending, attach, detach, spawn
from .loop import Loop
from .world import Component, Entity, World

#: Attribute payloads are stored as their `repr`, which round-trips exactly for
#: every constant Python's grammar can express (`str`, `bytes`, `int`, `float`,
#: `complex`, `bool`, `None`, and the ellipsis). ⚠ The value therefore lives IN
#: the world as an entity's printed name rather than in a Python dict beside it —
#: a side map would be state the systems cannot see, which is the thing this
#: substrate is for.
_ELLIPSIS = "..."


class Printed(Component):
    """What an entity is called when something has to show it to a person.

    ⚠ For PRINTING, never for identity — two entities may print the same and be
    two things (two `x`s in two functions, two files with one basename). `word()`
    and `value()` are the two places identity does go by name.
    """

    def __init__(self, text: str) -> None:
        self.text = text


class Interned(Component):
    """⭐ That this entity is THE one for its text — and which table it is in.

    ⚠⚠ **WITHOUT THIS, A SAVED WORLD COMES BACK AS TWINS.** `word("loop")` and
    `node("loop")` both spawn a `Printed("loop")`; what makes the first interned
    and the second a fresh occurrence is `Facts._words`, a Python dict beside the
    world. A dict beside the world does not survive a restart — so a restored
    `name(n, #2)` and a freshly asked `word("loop")` were two different entities,
    nothing matched, and the run reported a contented quiescence having done
    nothing. That is the twin trap this package's notes say cost four recorded
    readings, arriving through a door nobody had opened yet, because until
    `Relation.__ugm_save__` existed a world of facts could not be restored at all.

    ⭐ So the fact that gives an entity its identity lives IN the world, which is
    exactly the argument `_ELLIPSIS` already makes about a literal's payload: a
    side map is state the systems cannot see, and this substrate exists so that
    there is no such map. `_words`/`_values` are a CACHE of this now, not the
    truth.

    ⚠ An occurrence (`node()`) carries no `Interned`, and that IS the
    distinction: `f.node("gt") != f.node("gt")` by design.
    """

    WORD = "word"
    VALUE = "value"

    def __init__(self, kind: str) -> None:
        self.kind = kind


class Relation(Component):
    """One relation, on one subject: the ordered rows of objects it relates it to.

    `body(n, b)` is one row, `(b,)`. `stmt(block, s1)` and `stmt(block, s2)` are two
    rows on the same component, in deposit order — **a body is an ordered thing**,
    and describing a three-line loop by its first statement is the bug that
    ordering exists to prevent.

    A KIND (`for_stmt(n)`) is the degenerate case: one row with no objects. There
    is nothing to say about the subject except that it is one.

    ⚠ Rows are DEDUPED, which is `ugm`'s interning arriving as an ordinary set
    check. It is what makes `fact()` idempotent, and `attach` comparing before it
    stores is what turns that into *the loop settles*. See the module note.
    """

    #: ⚠ The relation's name, set by `relation()` on each subclass it mints.
    #: `None` on this base class, which is never attached to anything itself.
    relation: Optional[str] = None

    def __init__(self, rows: Tuple[Tuple[Entity, ...], ...] = ()) -> None:
        self.rows = tuple(rows)

    @classmethod
    def __ugm_save__(cls) -> Optional[str]:
        """⭐ How `save` should name this class, since it cannot FIND it.

        `save` resolves `module:ClassName` with `getattr`, and a class
        `relation()` minted with `type()` is not an attribute of anything —
        so a whole world of facts used to serialise fine and come back
        empty, one named problem per relation, the world silently thinner.
        Answering here says *call `ugm.facts:relation` with this name*
        instead, and since `relation` interns, what comes back IS the class
        the live world is already using rather than a twin of it.

        ⚠ `None` from the base class means "name me the ordinary way" — it
        is `Relation` itself, which nothing attaches; only subclasses carry
        a name to be rebuilt from.
        """
        if cls.relation is None:
            return None
        return "%s:relation(%s)" % (__name__, cls.relation)


#: relation name -> its component class. ⭐ The name table that used to be
#: `Loader`'s, and the reason the twin trap cannot recur: interning is Python's.
_RELATIONS: Dict[str, type] = {}


def relation(name: str) -> type:
    """The component class for this relation. The SAME class every call.

    ⭐ This is what a system names: `world.each(relation("for_stmt"), ...)`. A
    domain that wants to read well binds them once at module scope —
    `ForStmt = relation("for_stmt")` — and its systems then look like the plain
    `World.each` systems in `ugm`'s own tests, because they are.
    """
    cls = _RELATIONS.get(name)
    if cls is None:
        # ⚠ `type()` takes the relation's own name so a stray `repr` in a traceback
        # says `body(...)` rather than `Relation(...)` about four different things.
        cls = _RELATIONS[name] = type(name, (Relation,), {"relation": name})
    return cls


#: ⭐ `relation` is also the FACTORY `save.py` calls back into: a component whose
#: type reads `ugm.facts:relation(for_stmt)` is rebuilt by calling exactly this,
#: which returns the interned class rather than a new one. See
#: `Relation.__ugm_save__`, and `save.py`'s note on that spelling. ⚠ Nothing about
#: this is registered anywhere — the class names its own factory, so a domain that
#: mints classes some other way does the same thing without telling this module.


class Facts:
    """One world, one loop, and the propositions deposited into it."""

    def __init__(self, *domains, budget: int = 400, ceiling: int = 4096) -> None:
        self.world = World()
        self.loop = Loop(self.world, budget=budget)
        #: ⚠⚠ **THE CIRCUIT BREAKER THE TICK BUDGET IS NOT.** `budget` bounds how
        #: many times the loop asks; it does not bound what one tick COSTS, and a
        #: rule that mints can spend the machine long before tick 400. Measured, on
        #: the runaway `pystrider.plan.lower` was: entities grew LINEARLY, ~6 a
        #: tick, while resident memory went 20 MB → 65 → 236 → 966 across ticks 20
        #: to 50 — because each clone was NAMED after the entity it copied, so
        #: every generation roughly doubled a string. At tick 35 the world held 234
        #: entities and one of their names was 13.6 million characters. Neither a
        #: tick budget nor an entity count can see that; the process just dies.
        #:
        #: ⭐ So the ceiling is on the length of a NAME, because a name here is
        #: IDENTITY — what `_find` matches, what interning keys, what `save` writes
        #: — and identity that grows with the derivation is identity being used as
        #: payload. Refusing it is the same rule `known()` already keeps one door
        #: over: a system reads the vocabulary, it does not inflate it. The longest
        #: name any settled `pystrider` suite produces is 147 characters.
        self.ceiling = ceiling
        #: Interning tables. ⚠ Per-world, because an entity belongs to a world:
        #: `Entity.__eq__` checks `other.world is self.world`, so a word shared
        #: between two worlds would compare unequal to itself. Only ever hold a
        #: REAL `Entity`, never a `Pending` -- see `_mint`.
        self._words: Dict[str, Entity] = {}
        self._values: Dict[str, Entity] = {}
        #: Whether the world underneath has been scanned for entities a PREVIOUS
        #: process interned (`save.read` into this world). See `_adopt`.
        self._adopted = False
        #: THIS TURN's own not-yet-applied writes, or `None` between turns --
        #: see `system()`. `_pending` is the flat list `ugm.loop.Loop.tick`
        #: applies; `_overlay` and `_minting` are what let `fact`/`deny`/`word`
        #: read back what THIS SAME turn already described, before any of it
        #: is real.
        self._pending: Optional[list] = None
        self._overlay: Optional[Dict[Tuple[Entity, type], Optional[Component]]] = None
        self._minting: Optional[Dict[str, Entity]] = None
        for domain in domains:
            self.install(domain)

    # -- domains ----------------------------------------------------------

    def install(self, domain):
        """Hand this loop to a domain's `install(loop, facts)`.

        ⚠ Two arguments where a bare `Loop` domain takes one: a domain here needs
        the naming table as well as the world, because a system that wants to
        deposit `iteration(n)` needs the same `Facts` the reader will ask.
        """
        return domain(self.loop, self)

    def system(self, fn=None, *, name=None, watches=None, priority=0):
        """Register one system -- wrapped so `fact`/`state`/`deny`/`node`/
        `word`/`value`/`reify`, called from inside it, describe a change
        instead of making one.

        ⚠⚠ **This is the whole of what the delta contract changed for the
        domains above this module — nothing in them did.** `ugm` 11c459a made a
        system return deltas rather than touch the world; every system registered
        through here already went through `f.fact(...)`, never
        `world.attach(...)` directly, so ONE place absorbs the new contract:
        `f.fact`/`state`/`deny` accumulate instead of writing, this wrapper
        collects what accumulated and hands it back, and `Loop.tick` applies
        it exactly as it always applied whatever a system returned.

        `functools.wraps` is load-bearing, not tidiness: `ugm.loop`'s own
        `_name_of` reads `fn.__module__`/`fn.__name__` to name a system
        `patterns.iteration` rather than `facts.wrapped`, and the SYSTEMS
        registry `/systems` prints is only legible if it does.

        `watches`, passed straight through to `Loop.system`, is a relation
        NAME or a tuple of them here, not a component type -- `relation()`
        interns, so `watches="candidate"` and `watches=("candidate",
        "request")` resolve to the classes `Loop.populated` checks against.
        `priority` passes straight through too -- see `Loop.system`'s own
        note on why it orders every system, not just the ones sharing a
        watched relation.
        """
        if fn is None:
            return lambda f: self.system(f, name=name, watches=watches,
                                         priority=priority)
        kinds = None
        if watches is not None:
            names = (watches,) if isinstance(watches, str) else tuple(watches)
            kinds = tuple(relation(n) for n in names)

        @functools.wraps(fn)
        def wrapped(world):
            self._pending, self._overlay, self._minting = [], {}, {}
            try:
                fn(world)
            finally:
                pending = self._pending
                self._pending = self._overlay = self._minting = None
            return pending

        return self.loop.system(wrapped, name=name, watches=kinds, priority=priority)

    # -- reading back THIS TURN's own not-yet-applied writes ---------------

    def _held(self, subject: Entity, cls: type) -> Optional[Component]:
        """The component of this type on this subject, as of RIGHT NOW —
        this turn's own writes first (even a `None` recorded there, a
        `deny` down to nothing), the world under them otherwise.

        `subject` may be a `Pending` from a `spawn`/`node`/`word`/`value`
        earlier in THIS SAME turn — nothing on the real world yet, so
        there is nothing to fall back to but what the overlay itself
        already knows about it.
        """
        if self._overlay is not None:
            key = (subject, cls)
            if key in self._overlay:
                return self._overlay[key]
        if isinstance(subject, Pending):
            return None
        return self.world.get(subject, cls)

    # -- naming -----------------------------------------------------------

    def _find(self, text: str) -> Optional[Entity]:
        """A REAL `Printed(text)` already in the world, if one exists.

        The fallback for exactly what `_words`/`_values`/`_minting` do not
        cover: a word or value first minted mid-turn is a `Pending`, never
        cached in the global tables (see `_mint`), so a LATER turn -- even
        the very next tick, the same system reasoning about the same
        thing again -- has nothing to look up and would otherwise mint a
        SECOND entity for the same text every single time it asks. That
        is not a slow path, it is a world that never settles: `answer`
        deriving `could_not_evaluate(f, c, value(refused))` fresh every
        tick, each with a DIFFERENT entity for the identical refusal
        string, so the row never repeats and the system never stops
        firing -- `test_an_unmodelled_operator_is_refused_BY_NAME` is
        what this looked like before `_find` existed.
        """
        for entity, printed in self.world.each(Printed):
            if printed.text == text:
                return entity
        return None

    def _mint(self, text: str, kind: Optional[str] = None):
        """A fresh `Printed(text)` -- an `Entity` outside a system's turn
        (nothing to describe instead of), a `Pending` inside one, the same
        way `spawn()` itself hands one back. `_find` first, mid-turn: an
        EARLIER turn's own mint may already be real by now (`Loop.tick`
        applies a system's deltas the moment it returns, before the next
        one runs), just not yet reflected in `_words`/`_values`.

        ⚠⚠ **`word`/`value` cache only a REAL entity, never a `Pending`.**
        `_words`/`_values` are read by ANY system, on ANY later tick — a
        `Pending` only resolves within the list its own `Spawn` came back
        in, so caching one globally would hand a LATER turn a token that
        blows up the moment it is used (`ugm.delta` refuses it by name).
        `_minting` is the one place a `Pending` IS cached, and only for the
        rest of THIS turn: `word("ge")` called twice while proposing one
        repair must return the SAME token both times, or the second call
        mints a second, different "ge".
        """
        if len(text) > self.ceiling:
            # ⭐ Raised INSIDE the system that minted it, so `Loop.tick` records it
            # against that system's name and `run` re-raises it already attributed:
            # "the system 'plan.lower' raised". The culprit names itself.
            raise RuntimeError(
                f"a name of {len(text)} characters is over this world's ceiling of "
                f"{self.ceiling} — a name is identity here, so one that grows with "
                f"the derivation means a rule is minting from its own output "
                f"(pass ceiling= to raise it deliberately): {text[:120]!r}…"
            )
        if self._pending is not None:
            cached = self._minting.get(text)
            if cached is not None:
                return cached
            found = self._find(text)
            if found is not None:
                return found
            made = spawn(Printed(text))
            self._pending.append(made)
            self._minting[text] = made.entity
            self._overlay[(made.entity, Printed)] = Printed(text)
            if kind is not None:
                # ⭐ DESCRIBED, not attached -- this turn's own rule, same as every
                # other write here. `Interned` has to travel with the `Printed` or
                # a restart cannot tell this entity from an occurrence.
                self._pending.append(attach(made.entity, Interned(kind)))
                self._overlay[(made.entity, Interned)] = Interned(kind)
            return made.entity
        entity = self.world.spawn(Printed(text))
        if kind is not None:
            self.world.attach(entity, Interned(kind))
        return entity

    def _adopt(self, text: str, kind: str) -> Optional[Entity]:
        """The entity the WORLD already interned for this text, if this `Facts`
        has not seen it -- a world a previous process saved and this one read.

        ⭐ Scanned ONCE per instance, not once per miss. `save.load` refuses a
        world that is not empty, so the only way entities appear underneath a
        `Facts` without going through `word`/`value` is a restore, and a restore
        can only happen before any of this has run. After that, a miss is a
        genuinely new word and there is nothing to look for.

        ⚠ This is why no caller has to remember anything after
        `save.read(f.world, path)`. A rebuild you must remember is a rebuild
        somebody skips, and skipping it is SILENT: two entities, one text, and a
        world that settles having matched nothing.

        ⚠ It spawns nothing, ever. That is what lets `known()` use it without
        reopening the door `known()` exists to keep shut.
        """
        if self._adopted:
            return None
        self._adopted = True
        for entity, mark in self.world.each(Interned):
            printed = self.world.get(entity, Printed)
            if printed is None:
                continue
            table = self._words if mark.kind == Interned.WORD else self._values
            table.setdefault(printed.text, entity)
        table = self._words if kind == Interned.WORD else self._values
        return table.get(text)

    def node(self, printed: str) -> Entity:
        """A fresh individual. The name is for printing; identity is the entity."""
        return self._mint(printed)

    def word(self, text: str) -> Entity:
        """A VOCABULARY word — an operator, an identifier, a CNL atom.

        ⚠⚠ **Not a literal, and conflating the two made a corpus unable to talk
        about code.** `value()` encodes by `repr`, so the operator `gt` was stored
        under the name `'gt'` — quoted — while a rule naming `gt` means the bare
        word. The two never matched, so one of two repair families could never fire
        **ever**, and the only reason the suite looked healthy is that its rival
        keys on an integer, where `repr(18)` and the token `18` agree by luck.

        ⭐ The distinction is real rather than a workaround: `age > 18` holds one
        Python literal, `18`. `gt` is not a value the program computes with — it is
        a word from our vocabulary, and words are what rules are made of.
        """
        got = self._words.get(text)
        if got is not None:
            return got
        got = self._adopt(text, Interned.WORD)
        if got is not None:
            return got
        made = self._mint(text, Interned.WORD)
        if not isinstance(made, Pending):
            self._words[text] = made
        return made

    #: CNL's name for the same thing. A block's `premium` is a word.
    atom = word

    def known(self, text: str) -> Optional[Entity]:
        """The word for this text IF it has already been interned, else None.

        ⚠⚠ **THE ONE READ THAT MUST NOT MINT, and minting here is a world that never
        settles.** `word()` spawns on a miss, so a matcher that resolved an atom
        through it would `spawn` on every failed unification — the revision moves,
        the loop calls that a firing system, and it ticks until the budget runs out
        having concluded nothing. It is the old no-inert-set hang arriving through a
        different door, so the door is closed rather than documented: a system reads
        the vocabulary, it does not extend it.

        ⭐ It does read a RESTORED vocabulary, though, and that keeps the rule
        rather than bending it: `_adopt` only moves what the world already holds
        into the cache and spawns nothing. A matcher asking about a word a
        previous process interned gets it; a matcher asking about a word nobody
        has ever interned still gets `None`.
        """
        got = self._words.get(text)
        if got is not None:
            return got
        return self._adopt(text, Interned.WORD)

    def value(self, payload: Any) -> Entity:
        """An entity standing for a literal, named by its `repr` so a reader recovers it.

        ⭐ Interned, and it is the RIGHT identity rather than merely the working
        one: two `10`s in two functions are the same *value*, while the two
        `constant` nodes holding them stay distinct because those come from
        `node()`. Identity of a value is its value; identity of an occurrence is
        the occurrence.
        """
        text = _ELLIPSIS if payload is Ellipsis else repr(payload)
        got = self._values.get(text)
        if got is not None:
            return got
        got = self._adopt(text, Interned.VALUE)
        if got is not None:
            return got
        made = self._mint(text, Interned.VALUE)
        if not isinstance(made, Pending):
            self._values[text] = made
        return made

    def show(self, n: Entity) -> str:
        got = self._held(n, Printed)
        return repr(n) if got is None else got.text

    #: The word back out of the entity. The inverse of `word`.
    word_of = show

    def payload(self, n: Entity) -> Any:
        """The literal back out of the entity. The inverse of `value`."""
        text = self.show(n)
        return Ellipsis if text == _ELLIPSIS else ast.literal_eval(text)

    # -- writing ----------------------------------------------------------

    def _write(self, subject: Entity, component: Component) -> None:
        """Put this component on that subject -- described as a delta if
        this is inside a system's turn (staged in the overlay too, so
        THIS SAME turn reads it back), attached directly otherwise. The
        one place `fact`/`state` actually write.
        """
        cls = type(component)
        if self._pending is not None:
            self._pending.append(attach(subject, component))
            self._overlay[(subject, cls)] = component
        else:
            self.world.attach(subject, component)

    def _erase(self, subject: Entity, cls: type) -> None:
        """Take this component type off that subject entirely -- staged or
        direct, the same way `_write` is."""
        if self._pending is not None:
            self._pending.append(detach(subject, cls))
            self._overlay[(subject, cls)] = None
        else:
            self.world.detach(subject, cls)

    def fact(self, name: str, subject: Entity, *objects: Entity) -> Entity:
        """Deposit `name(subject, objects...)`, and return the SUBJECT.

        ⚠ Engine 4 returned the proposition, because a proposition was a node and
        `unreadable`/the gap vocabulary needed somewhere to hang. Here a relation
        is not a thing in the world — it is a component ON the subject — so there
        is nothing to hand back but the subject. Where a claim ABOUT a claim is
        wanted, the subject is minted for it (`reify`).
        """
        cls = relation(name)
        row = tuple(objects)
        held = self._held(subject, cls)
        rows = () if held is None else held.rows
        if row not in rows:
            # ⭐ A new component rather than a mutated one — `attach` compares by
            # value, and a component mutated in place is a change nothing can see.
            self._write(subject, cls(rows + (row,)))
        return subject

    def state(self, name: str, subject: Entity, *objects: Entity) -> Entity:
        """Deposit `name(subject, objects...)` as the ONLY row of that relation.

        ⭐ `fact()` appends, which is what a body of statements needs; this
        REPLACES, which is what a conclusion that can be revised needs. A system
        that re-resolves a screen shape every tick must not leave both answers
        standing — `one()` would then refuse to pick between them, correctly, about
        a question that has exactly one answer.

        ⚠ Still idempotent: `attach` compares before it stores, so restating the
        same answer does not move `revision` and the world still settles.
        """
        self._write(subject, relation(name)((tuple(objects),)))
        return subject

    def deny(self, name: str, subject: Entity, *objects: Entity) -> bool:
        """Withdraw `name(subject, objects...)`. True if it was there to withdraw.

        ⚠ Engine 4's chain was append-only, so *change this* had to be spelled
        `-old, +new` and a reader that walked its own deposit log would see BOTH —
        engine 2 shipped a repair that "succeeded" while emitting byte-identical
        source, and only an independent gate caught it. Here there is one store and
        removal is removal, so a reader cannot see a withdrawn claim at all. The
        deny-then-assert SHAPE stays because it is what a repair means; the hazard
        it guarded against is gone.

        ⚠ Reads `_held`, not `self.world.get` — `relax`/`lower` `deny` an
        operator and `fact` its replacement in the SAME turn, and the second
        call has to see the first's own effect or both rows would stand.
        """
        cls = relation(name)
        held = self._held(subject, cls)
        if held is None or tuple(objects) not in held.rows:
            return False
        rows = tuple(r for r in held.rows if r != tuple(objects))
        if rows:
            self._write(subject, cls(rows))
        else:
            self._erase(subject, cls)
        return True

    def reify(self, name: str, *members: Entity) -> Entity:
        """An entity standing for the proposition `name(members...)`, interned.

        For the places a claim is made ABOUT a claim — `unmet($p, evaluated(...))`.
        ⚠ Interned on its printed form, so asking twice about the same proposition
        gets the same subject and the rules join.
        """
        key = "%s(%s)" % (name, ", ".join(self.show(m) for m in members))
        got = self._values.get(key)
        if got is not None:
            return got
        made = self._mint(key)
        if not isinstance(made, Pending):
            self._values[key] = made
        self.fact("proposition", made)
        self.fact("about", made, self.word(name), *members)
        return made

    # -- reading ----------------------------------------------------------

    def of(self, name: str, subject: Entity) -> List[Tuple[Entity, ...]]:
        """Every `name(subject, ...)` that holds, in deposit order.

        Insertion-ordered, because a body is an ordered thing. Reads
        `_held`, not `self.world.get` — a system that `fact`s or `deny`s
        and then reads the SAME (name, subject) again before its own turn
        ends must see what it just described, not the world as of the
        turn's start.
        """
        held = self._held(subject, relation(name))
        return [] if held is None else list(held.rows)

    def one(self, name: str, subject: Entity) -> Optional[Entity]:
        """The single object of a relation, or None. Refuses to guess between two.

        ⚠ Engine 2's `targets(n, label)[0]` silently described a three-line loop by
        its first statement, and later described `f(a, b)` by its first argument
        after a gap renumbered the rest. Taking the first of several is the shape of
        both bugs, so this will not do it.
        """
        got = self.of(name, subject)
        if not got:
            return None
        if len(got) > 1:
            raise ValueError(
                f"{name} of {self.show(subject)} has {len(got)} objects — "
                f"`one` refuses to pick; the caller wants `of`"
            )
        if len(got[0]) != 1:
            # ⚠ The same refusal in the other axis, and it was once missing: a
            # THREE-place relation has two objects, and this quietly returned the
            # first — `text("wants", f)` handed back the CASE where the caller meant
            # the value, and the error surfaced two frames away in `literal_eval`.
            raise ValueError(
                f"{name} of {self.show(subject)} is {len(got[0]) + 1}-place — "
                f"`one` answers about a single object; the caller wants `of`"
            )
        return got[0][0]

    def each(self, name: str, arity: Optional[int] = None):
        """Every `(subject, *objects)` row of this relation, across every
        subject that carries it -- generator, not a list, but see `World.each`:
        it walks the world's own materialised query, so this costs nothing
        extra to consume more than once.

        ⭐ The generic reader's boilerplate, named: `arbitration.commit` and
        `request.watch` each used to spell `for occasion, held in
        world.each(Candidate): for row in held.rows: if len(row) != 1:
        continue; (option,) = row` by hand -- one relation, one arity, one
        subject per row is the overwhelmingly common shape, and this is that
        walk, done once, here::

            for occasion, option in f.each("candidate", arity=1):
                ...

        `arity`, when given, silently SKIPS a row of a different width
        rather than raising -- a system reading `stmt(subject, a, b)` next
        to `stmt(subject, a)` should see one shape or the other, not choke
        on either; a caller that wants to know about the mismatch reads
        `of()` directly, the way `one()` already does.
        """
        for subject, held in self.world.each(relation(name)):
            for row in held.rows:
                if arity is not None and len(row) != arity:
                    continue
                yield (subject,) + row

    def objects(self, name: str, subject: Entity) -> List[Entity]:
        """Every single OBJECT of a ONE-PLACE relation on this subject --
        `of()` filtered to one-place rows and unwrapped.

        The list a caller reaches for instead of `one()`'s refusal, when
        several rows are exactly what is expected (`f.objects("responding",
        details)` for however many workers answered) rather than an error:
        `[row[0] for row in f.of(name, subject) if len(row) == 1]`, spelled
        out by hand in `arbitration.py` and `request.py` before this existed.
        """
        return [row[0] for row in self.of(name, subject) if len(row) == 1]

    def subjects(self, name: str) -> List[Entity]:
        """Every entity this relation is asserted of, in spawn order.

        ⚠ Reads `self.world` straight, NOT `_held` — this asks across every
        entity there is, and the overlay only ever knows about the ones a
        single subject-keyed write already named. A system that `fact`s a
        NEW subject onto `name` and then calls `subjects(name)` in the SAME
        turn will not see that subject until the next one; nothing
        currently does both in one turn, and `test_the_world_SETTLES`
        (`facts.py`'s own guard, not a mention here) is what would catch it
        if that ever changes.
        """
        return [e for e, _ in self.world.each(relation(name))]

    def has(self, name: str, subject: Entity) -> bool:
        """Whether `name(subject)` — a kind, or any claim at all — holds now."""
        held = self._held(subject, relation(name))
        return held is not None and bool(held.rows)

    def holds(self, name: str, subject: Entity, *objects: Entity) -> bool:
        """Whether this exact proposition holds right now."""
        held = self._held(subject, relation(name))
        return held is not None and tuple(objects) in held.rows

    def text(self, name: str, subject: Entity) -> Optional[str]:
        """A WORD-valued attribute (`name`, `id`, `attr`, `operator`), back as a `str`."""
        n = self.one(name, subject)
        return None if n is None else self.show(n)

    def literal(self, name: str, subject: Entity) -> Any:
        """A VALUE-valued attribute (`literal`, `origin`, `source_line`), decoded.

        The counterpart to `text`, and named so a caller has to say which kind it
        expects — reaching for the wrong one fails loudly instead of handing back
        `"'gt'"` where `"gt"` was meant.
        """
        n = self.one(name, subject)
        return None if n is None else self.payload(n)

    # -- running ----------------------------------------------------------

    def run(self, budget: Optional[int] = None):
        """Call every system until a whole pass changes nothing.

        ⚠⚠ **A system that raised is RE-RAISED here, which `Loop.run` does not
        do.** `loop.py` records the exception on `loop.errors` and carries on,
        because a typo in one domain should not take a person's REPL down with it.
        That is right for a prompt and wrong for a DERIVATION: a rule that raised
        did not fire, so the world settles *looking* quiescent while the conclusion
        it owed is simply absent — the exact shape of silence this vocabulary has
        already paid for four times. A batch caller gets the error; `Engine` and
        anything else running a session keeps `Loop.run` and `loop.errors`.
        """
        settled = self.loop.run(budget=budget)
        if self.loop.errors:
            name, error = self.loop.errors[0]
            raise RuntimeError(
                f"the system {name!r} raised, so whatever it concludes is missing "
                f"from a world that otherwise looks settled: {error!r}"
            ) from error
        if settled.hot:
            raise RuntimeError(
                f"the world did not settle in {settled.ticks} ticks — still firing: "
                f"{', '.join(settled.hot)}. Two systems are feeding each other, or "
                f"one concludes something it cannot recognise as already concluded."
            )
        return settled
