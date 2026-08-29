"""The world model: entities, the components they carry, and nothing else.

An **entity** is an identity and no data -- `#7`. A **component** is a
plain `@dataclasses.dataclass` -- data and no identity -- `Size(bytes=4300)`.
A thing in the world is whatever components are currently attached to one
entity, and it can stop being that kind of thing by losing one::

    @dataclasses.dataclass(frozen=True)
    class Size:
        bytes: int

    @dataclasses.dataclass(frozen=True)
    class Stale:
        pass

    entry = w.spawn(Entry(folder, "todo.txt"), Size(17), Modified(when))
    w.attach(entry, Stale())          # now it is also a stale thing
    w.detach(entry, Stale)            # now it is not

A **system** -- what `ugm.loop` calls a rule -- is a function that asks
for the entities carrying a set of components, walks them, and RETURNS
what should change -- see `ugm.delta`. It does not call `spawn`,
`attach`, `detach` or `destroy` on this class itself; `Loop.tick` does,
from what a system hands back::

    def flag_big(w):
        deltas = []
        for entity, hunt in w.each(BigHunt):
            deltas.append(destroy(entity))
            for e, entry, size in w.each(Entry, Size):
                if entry.folder == hunt.folder and size.bytes >= hunt.floor:
                    deltas.append(attach(e, Big()))
        return deltas

## Why a component and not an attribute

Because a rule asks "everything that is X and Y but not Z" far more often
than it asks "everything about this one thing". `each(Entry, Stale)` is
the query the domain actually wants, and it costs a set intersection --
where a bag of objects with a `stale` flag on them costs a scan and an
`if`. Being stale is not a property of a file, it is a claim some system
made about it, and detaching that claim is how it is unmade.

The approval gate is the sharpest case: a rename waiting for a person is
the same entity as a rename about to happen, plus one component::

    w.each(RenameWish, NeedsApproval)             # ask about these
    w.each(RenameWish, without=NeedsApproval)     # do these

`approve` detaches one tag. Nothing is copied from a held queue to a live
one, and nothing has to be told apart by a flag.

## A component is a plain dataclass, and there is nothing else to it

There is no `Component` base class here to inherit -- a component is
anything `dataclasses.is_dataclass` says yes to. That is the whole of what
`attach()` requires, and it buys the boilerplate `@dataclass` was built to
remove: `Size(17) == Size(17)` and `repr(Size(17)) == 'Size(bytes=17)'` for
free, no hand-written `__init__`/`__eq__`/`__repr__`. Frozen is a
convention, not enforced -- see the ⚠ below on why a component should never
be mutated in place regardless.

`Size(17) == Size(17)` is what makes `attach` idempotent: re-attaching a
value equal to one already there changes nothing, so a system that
recomputes the same answer every tick does not keep the world awake
forever.

⚠ A component mutated in place is a change nothing can see -- `revision`
does not move, and the loop will call the world settled. Attach a fresh
one instead of editing the one already there, and prefer `frozen=True` so
Python enforces that for you rather than a docstring.

## An entity carries a LIST of each type, not one

`attach(entity, X)` APPENDS `X` to whatever that entity already carries of
`X`'s type -- deduped against what is already there, so re-deriving the
same value is still a no-op, but genuinely different values of one type
coexist. `get(entity, Kind)` refuses to guess between several the same way
`each()`'s single-valued queries always assumed there was at most one --
`None` if there are none, the value if there is exactly one, a loud
`ValueError` if there are several, so a query written against "the" value
of a naturally-singular kind fails LOUDLY the moment two coexist rather
than silently taking whichever happened to sort first.

`replace(entity, X)` is the tool for a kind meant to stay singular --
`Session`, `Contents`, a folder's `Size` -- clearing every existing
component of `X`'s type on the entity before attaching it, but ONLY an
actual change: replacing with an equal value is still a no-op, the same
guarantee `attach` already gives.

`get_all(entity, Kind)` and `all(Kind)` read the plural case: every
instance on one entity, or every instance anywhere, respectively.

## Entities are ids, and a component may hold one -- as a plain int

`Entry(folder=1, name='todo.txt')` refers to its folder by the folder's
own entity id, which is how a relationship is spelled here -- no object
graph, no back references to keep in step. **A component field never holds
a live `Entity` object** -- only `None`, `bool`, `int`, `float`, `str`, or
a `list`/`dict`/`tuple` of those, so that a component is always exactly
what it looks like: data a `json.dumps` could write down, nothing a Python
object graph is doing behind the scenes. `attach()` enforces this: pass a
live `Entity` in a field (the ergonomic thing to do -- `Entry(folder,
name)` where `folder` came straight from a query) and it is lowered to
`folder.id` on the way in; pass anything else `attach()` cannot make sense
of as data and it raises, naming the field, rather than storing a
reference nothing here can serialize or compare by value.

`world.entity(id)` is the other direction -- turn a raw id read out of a
component field back into a handle, to `.get()`/`.attach()`/... on it.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, List

_PRIMITIVES = (type(None), bool, int, float, str)


class Entity:
    """A handle: which entity, and in which world. No data of its own.

    Compares and hashes by id, so a handle handed back by a query is the
    same one a component stored earlier, and a component holding `#7` goes
    on meaning `#7` however many times it is looked up.

    ⚠ Never store one of these AS a component field -- see the module note.
    Hold its `.id` there instead; this class exists for the API surface a
    rule reads and writes through, not for data at rest.
    """

    __slots__ = ("id", "world")

    def __init__(self, world, id_: int) -> None:
        self.world = world
        self.id = id_

    def __eq__(self, other) -> bool:
        return (isinstance(other, Entity) and other.id == self.id
                and other.world is self.world)

    def __hash__(self) -> int:
        return hash(self.id)

    def __repr__(self) -> str:
        return "#%d" % self.id

    # Sugar, for the places a system already holds the entity and wants one
    # thing off it. Everything here is `World`'s method with the entity
    # filled in -- there is no second way to do anything.
    def get(self, kind):
        return self.world.get(self, kind)

    def get_all(self, kind) -> "list":
        return self.world.get_all(self, kind)

    def has(self, *kinds) -> bool:
        return self.world.has(self, *kinds)

    def attach(self, *components) -> "Entity":
        return self.world.attach(self, *components)

    def replace(self, *components) -> "Entity":
        return self.world.replace(self, *components)

    def detach(self, *kinds) -> bool:
        return self.world.detach(self, *kinds)

    def remove(self, component) -> bool:
        return self.world.remove(self, component)

    def destroy(self) -> bool:
        return self.world.destroy(self)

    @property
    def alive(self) -> bool:
        return self.world.alive(self)


@dataclasses.dataclass(frozen=True)
class Said:
    """A line arriving on a channel. What a person typed, before anything
    has decided it means something."""

    channel: str
    text: str


@dataclasses.dataclass(frozen=True)
class Reply:
    """Something to say back on a channel. The one thing a prompt prints
    unasked -- see `harneskills.repl`."""

    channel: str
    text: str


def _lower(value: Any, where: str) -> Any:
    """`value`, with any `Entity` turned into its plain id -- recursively,
    through `list`/`dict`/`tuple` -- or a `TypeError` naming `where` if
    what is left still is not data `attach()` can store. See the module
    note: this is the one place "a component holds no Python object
    references" is enforced rather than merely documented.
    """
    if isinstance(value, Entity):
        return value.id
    if isinstance(value, _PRIMITIVES):
        return value
    if isinstance(value, tuple):
        return tuple(_lower(v, where) for v in value)
    if isinstance(value, list):
        return [_lower(v, where) for v in value]
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                raise TypeError("%s: a dict key must be a string, not %s"
                                % (where, type(key).__name__))
        return {k: _lower(v, where) for k, v in value.items()}
    raise TypeError(
        "%s: a component field must be a primitive (None/bool/int/float/"
        "str), another entity (stored as its plain id, not the handle), "
        "or a list/dict/tuple of those -- got a %s, which is a reference "
        "to a Python object this world cannot store or compare by value"
        % (where, type(value).__name__))


def _normalize(component: Any) -> Any:
    """The same component, if none of its fields needed lowering; a FRESH
    one, built without calling `__init__` (so this works whether or not the
    dataclass is frozen), otherwise. Compared by value, not by identity, so
    a field that round-trips to something equal (a tuple rebuilt from
    already-plain ints, say) does not force a needless rebuild.
    """
    if not dataclasses.is_dataclass(component) or isinstance(component, type):
        raise TypeError(
            "attach() wants a component INSTANCE -- a plain @dataclass -- "
            "got %r" % (component,))
    name = type(component).__name__
    changed = False
    fields = {}
    for f in dataclasses.fields(component):
        value = getattr(component, f.name)
        lowered = _lower(value, "%s.%s" % (name, f.name))
        fields[f.name] = lowered
        if lowered != value:
            changed = True
    if not changed:
        return component
    fresh = object.__new__(type(component))
    for field_name, value in fields.items():
        object.__setattr__(fresh, field_name, value)
    return fresh


class World:
    """Entities, the components on them, and the queries systems ask."""

    def __init__(self) -> None:
        # entity id -> handle, in spawn order; and component type -> {entity
        # id: [components, in attach order]}. The second is the index every
        # query runs on: a query for three types is three dict lookups and
        # a walk of the smallest of them.
        self._entities: Dict[int, Entity] = {}
        self._by_type: Dict[type, Dict[int, List[Any]]] = {}
        self._next = 0
        # Bumped by every spawn, destroy, attach/replace that changed
        # something, and detach/remove that removed something. The loop
        # reads it to tell a system that did something from one that did
        # not, which is the whole of how it knows the world has settled.
        self.revision = 0
        # Words a domain expects a person to type. Only the prompt reads
        # this (to autocorrect); nothing here affects what a system finds.
        self.vocabulary: set = set()

    # -- entity ids, handles, either -----------------------------------

    def _id(self, entity) -> int:
        """An entity id, whether handed a live handle or the plain int
        already -- what lets every method below take either, which is what
        lets a component field holding a plain id (see the module note) be
        passed straight back into `get`/`has`/`attach`/... without a
        caller converting it to a handle first."""
        return entity.id if isinstance(entity, Entity) else int(entity)

    def entity(self, entity_id) -> Entity:
        """The handle for this id -- the other direction from a component
        field's plain int back to something `.get()`/`.attach()`/... work
        on. No existence check: the same trust level constructing `Entity`
        directly always had."""
        return Entity(self, int(entity_id))

    # -- writing -----------------------------------------------------

    def spawn(self, *components) -> Entity:
        """A new entity carrying these components. The only way to make one
        -- there is no such thing as an entity that never existed here."""
        self._next += 1
        entity = Entity(self, self._next)
        self._entities[entity.id] = entity
        self.revision += 1
        if components:
            self.attach(entity, *components)
        return entity

    def _adopt(self, entity_id: int) -> Entity:
        """The handle for this id, making the entity if it is not here.

        The one thing that exists for `ugm.save`, and the only way
        an entity ever gets an id it did not just take from the counter. It
        keeps the counter above whatever it has seen, so a restored world
        cannot hand a new entity an id some component still points at --
        and it does NOT move `revision`, because restoring is not something
        that happened to the world, it IS the world.
        """
        entity = self._entities.get(entity_id)
        if entity is None:
            entity = self._entities[entity_id] = Entity(self, entity_id)
            self._next = max(self._next, entity_id)
        return entity

    def destroy(self, entity) -> bool:
        """It is not here any more, and neither is anything on it. True if
        it was. What a system calls on an occasion it has finished with."""
        entity_id = self._id(entity)
        if self._entities.pop(entity_id, None) is None:
            return False
        for bucket in self._by_type.values():
            bucket.pop(entity_id, None)
        self.revision += 1
        return True

    def attach(self, entity, *components) -> Entity:
        """Add these components to whatever entity already carries of
        their own type -- deduped against what is already there, so
        re-attaching a value equal to one already present is not a
        change: it is not stored again and `revision` does not move,
        which is what lets a system recompute the same answer every tick
        and still let the world settle.

        A live `Entity` inside a component field is lowered to its plain
        id before storing -- see the module note; anything else that is
        not JSON-shaped data raises, naming the field.
        """
        entity_id = self._id(entity)
        if entity_id not in self._entities:
            raise ValueError("%r is not in this world" % (entity,))
        for component in components:
            component = _normalize(component)
            cls = type(component)
            values = self._by_type.setdefault(cls, {}).setdefault(entity_id, [])
            if component in values:
                continue
            values.append(component)
            self.revision += 1
        return self._entities[entity_id]

    def replace(self, entity, *components) -> Entity:
        """Each given component replaces every existing component of ITS
        OWN type on this entity -- the tool for a kind meant to stay
        singular (`Session`, `Contents`, a folder's `Size`).

        Still idempotent: replacing with a value equal to what is already
        the sole component of that type is not a change, same guarantee as
        `attach`. Two components of the SAME type passed to one call each
        replace in turn, so only the last survives -- meant for one
        component per type per call, the way every call site that needs
        this reaches for it.
        """
        entity_id = self._id(entity)
        if entity_id not in self._entities:
            raise ValueError("%r is not in this world" % (entity,))
        for component in components:
            cls = type(component)
            normalized = _normalize(component)
            bucket = self._by_type.setdefault(cls, {})
            if bucket.get(entity_id) == [normalized]:
                continue
            bucket[entity_id] = [normalized]
            self.revision += 1
        return self._entities[entity_id]

    def detach(self, entity, *kinds) -> bool:
        """Take EVERY component of these types off it. True if any were
        there. See `remove` to take off one specific value and leave the
        rest of that type standing."""
        entity_id = self._id(entity)
        gone = False
        for kind in kinds:
            bucket = self._by_type.get(kind)
            popped = bucket.pop(entity_id, None) if bucket else None
            if popped is not None:
                self.revision += 1
                gone = True
        return gone

    def remove(self, entity, component) -> bool:
        """Take ONE component equal to this value off it, leaving any other
        instances of the same type standing. True if it was there."""
        entity_id = self._id(entity)
        component = _normalize(component)
        cls = type(component)
        bucket = self._by_type.get(cls)
        values = bucket.get(entity_id) if bucket else None
        if not values or component not in values:
            return False
        values.remove(component)
        if not values:
            del bucket[entity_id]
        self.revision += 1
        return True

    def changed(self, entity=None) -> None:
        """Something changed that no attach said -- an index a domain keeps
        by hand, mutated in place. See the ⚠ at the top of this module."""
        self.revision += 1

    def learn(self, *words) -> None:
        """Add words to what the prompt will pull a typo towards."""
        self.vocabulary.update(str(word) for word in words)

    # -- reading -----------------------------------------------------

    def alive(self, entity) -> bool:
        return self._id(entity) in self._entities

    def get(self, entity, kind):
        """The one component of this kind on this entity, or `None`.
        Refuses to guess between several -- `ValueError` naming how many
        there are; the caller wants `get_all()`."""
        values = self._by_type.get(kind, {}).get(self._id(entity), ())
        if not values:
            return None
        if len(values) > 1:
            raise ValueError(
                "%r carries %d %s components -- get() refuses to guess; "
                "the caller wants get_all()" % (entity, len(values), kind.__name__))
        return values[0]

    def get_all(self, entity, kind) -> "list":
        """Every component of this kind on this entity, in attach order.
        `[]` if none -- the plural counterpart to `get()`."""
        return list(self._by_type.get(kind, {}).get(self._id(entity), ()))

    def has(self, entity, *kinds) -> bool:
        entity_id = self._id(entity)
        return all(self._by_type.get(k, {}).get(entity_id) for k in kinds)

    def populated(self, *kinds) -> bool:
        """Whether ANY entity carries at least one of these component
        types -- an existence check, not a query: `O(len(kinds))` dict
        lookups, no intersection, no walk of a bucket.

        This is what lets a system declare itself dormant (`Loop.system`'s
        `watches=`) rather than merely fast: `each()` on an empty bucket
        already returns quickly, but it still calls the system's own
        Python body to find that out. A system that watches a type nobody
        has ever attached is skipped before it runs at all.
        """
        return any(self._by_type.get(k) for k in kinds)

    def each(self, *kinds, without=()) -> "list":
        """Every entity carrying all of these components, oldest first::

            for entity, entry, size in w.each(Entry, Size):
            for entity, wish in w.each(RenameWish, without=NeedsApproval):

        One tuple per match: the entity, then its components in the order
        asked for. An entity carrying SEVERAL of an intersecting kind
        yields one row per combination -- the cross product across the
        kinds asked for, degenerating to today's one-row-per-entity the
        moment every matched kind is single-valued there, which is every
        case this codebase has today.

        Materialised, not lazy -- a system is expected to spawn and
        destroy while it walks what it found.
        """
        if not kinds:
            raise TypeError("each() needs at least one component type")
        if isinstance(without, type):
            without = (without,)
        buckets = [self._by_type.get(kind) or {} for kind in kinds]
        excluded = [self._by_type.get(kind) or {} for kind in without]
        out = []
        # Walk the rarest component and check the rest: a query is as
        # cheap as its most specific term, not as its widest.
        for entity_id in sorted(min(buckets, key=len)):
            if any(entity_id not in bucket for bucket in buckets):
                continue
            if any(entity_id in bucket for bucket in excluded):
                continue
            entity = self._entities[entity_id]
            per_kind = [bucket[entity_id] for bucket in buckets]
            for combo in _product(per_kind):
                out.append((entity,) + combo)
        return out

    def first(self, *kinds, without=()):
        """The first match of `each`, or None."""
        found = self.each(*kinds, without=without)
        return found[0] if found else None

    def the(self, kind):
        """The one component of a kind the world keeps exactly one of --
        the clock, the session. None if nothing carries it."""
        bucket = self._by_type.get(kind) or {}
        for entity_id in sorted(bucket):
            values = bucket[entity_id]
            if values:
                return values[0]
        return None

    def all(self, kind) -> "list":
        """Every component of this kind, anywhere -- `(entity, component)`
        per instance, entity first so a caller can trace it back without a
        component having to carry its own owner. World-wide counterpart to
        `get_all()`."""
        bucket = self._by_type.get(kind) or {}
        out = []
        for entity_id in sorted(bucket):
            entity = self._entities[entity_id]
            for component in bucket[entity_id]:
                out.append((entity, component))
        return out

    def components(self, entity) -> "list":
        """Everything on it, in the order the types were first seen, and
        within a type, the order it was attached in."""
        entity_id = self._id(entity)
        out = []
        for bucket in self._by_type.values():
            out.extend(bucket.get(entity_id, ()))
        return out

    def entities(self) -> "list":
        """Every entity, in the order it was spawned."""
        return [self._entities[i] for i in sorted(self._entities)]

    def show(self, entity) -> str:
        """`#7  Entry(folder=1, name='todo.txt')  Size(bytes=17)`"""
        handle = entity if isinstance(entity, Entity) else self.entity(entity)
        return "%-5s %s" % (handle, "  ".join(
            repr(c) for c in self.components(entity)))

    def __len__(self) -> int:
        return len(self._entities)

    def __contains__(self, entity) -> bool:
        if isinstance(entity, Entity):
            return entity.id in self._entities
        if isinstance(entity, int):
            return entity in self._entities
        return False


def _product(sequences: "list") -> "list":
    """The cross product of several lists, as a list of tuples --
    `itertools.product` spelled out so this module has no import beyond
    the standard library it already needed. `_product([[a], [b, c]])` is
    `[(a, b), (a, c)]`; `_product([[a]])` is `[(a,)]`, which is `each()`'s
    entire behaviour when every matched kind is single-valued.
    """
    out: "list" = [()]
    for sequence in sequences:
        out = [combo + (item,) for combo in out for item in sequence]
    return out
