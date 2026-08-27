"""The world model: entities, the components they carry, and nothing else.

An **entity** is an identity and no data -- `#7`. A **component** is data
and no identity -- `Size(bytes=4300)`. A thing in the world is whatever
components are currently attached to one entity, and it can stop being
that kind of thing by losing one::

    entry = w.spawn(Entry(folder, "todo.txt"), Size(17), Modified(when))
    w.attach(entry, Stale())          # now it is also a stale thing
    w.detach(entry, Stale)            # now it is not

A **system** -- what `ugm.loop` calls a rule -- is a function that
asks for the entities carrying a set of components and walks them::

    def flag_big(w):
        for entity, hunt in w.each(BigHunt):
            w.destroy(entity)
            for e, entry, size in w.each(Entry, Size):
                if entry.folder == hunt.folder and size.bytes >= hunt.floor:
                    w.attach(e, Big())

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

## A component is a value

`Size(17) == Size(17)` -- same type, same fields. That is what makes
`attach` idempotent: re-attaching a component equal to the one already
there changes nothing, so a system that recomputes the same answer every
tick does not keep the world awake forever. It also means a component is
REPLACED rather than edited::

    w.attach(entity, Size(4300))      # not: size.bytes = 4300

⚠ A component mutated in place is a change nothing can see -- `revision`
does not move, and the loop will call the world settled. Attach a new one.
Where that is genuinely wrong (a big index a domain keeps by hand, like
`Contents`), mutate it and call `world.changed()`.

## Entities are ids, and a component may hold one

`Entry(folder=#1, name='todo.txt')` refers to its folder by entity, which
is how relationships are spelled here -- no object graph, no back
references to keep in step. A handle compares and hashes by id, so two
handles for `#1` are interchangeable, and an entity that has been
destroyed is simply one that `alive()` says no to.

`Said` and `Reply` live in this module rather than in the prompt because a
domain that says something should not have to import a terminal to do it.
"""

from __future__ import annotations


class Component:
    """Data attached to an entity. Subclass it and assign in `__init__`::

        class Size(Component):
            def __init__(self, num_bytes):
                self.bytes = num_bytes

    A component with no fields is a TAG -- `Stale()`, `NeedsApproval()` --
    and every instance of it is equal to every other, which is exactly
    what "this entity is in that set" needs to mean.
    """

    def __eq__(self, other) -> bool:
        return type(self) is type(other) and vars(self) == vars(other)

    def __ne__(self, other) -> bool:
        return not self == other

    # Value equality without hashability: a component is stored BY the
    # entity it is on and by its own type, never in a set of its own, and
    # a `__hash__` that had to stay in step with mutable fields would be a
    # promise this class cannot keep.
    __hash__ = None

    def __repr__(self) -> str:
        return "%s(%s)" % (type(self).__name__, ", ".join(
            "%s=%r" % (name, value) for name, value in vars(self).items()))


class Entity:
    """A handle: which entity, and in which world. No data of its own.

    Compares and hashes by id, so a handle handed back by a query is the
    same one a component stored earlier, and a component holding `#7` goes
    on meaning `#7` however many times it is looked up.
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

    def has(self, *kinds) -> bool:
        return self.world.has(self, *kinds)

    def attach(self, *components) -> "Entity":
        return self.world.attach(self, *components)

    def detach(self, *kinds) -> bool:
        return self.world.detach(self, *kinds)

    def destroy(self) -> bool:
        return self.world.destroy(self)

    @property
    def alive(self) -> bool:
        return self.world.alive(self)


class Said(Component):
    """A line arriving on a channel. What a person typed, before anything
    has decided it means something."""

    def __init__(self, channel: str, text: str) -> None:
        self.channel = channel
        self.text = text


class Reply(Component):
    """Something to say back on a channel. The one thing a prompt prints
    unasked -- see `harneskills.repl`."""

    def __init__(self, channel: str, text: str) -> None:
        self.channel = channel
        self.text = text


class World:
    """Entities, the components on them, and the queries systems ask."""

    def __init__(self) -> None:
        # entity id -> handle, in spawn order; and component type -> {entity
        # id: component}. The second is the index every query runs on: a
        # query for three types is three dict lookups and a walk of the
        # smallest of them.
        self._entities: dict = {}
        self._by_type: dict = {}
        self._next = 0
        # Bumped by every spawn, destroy, attach that changed something,
        # and detach that removed something. The loop reads it to tell a
        # system that did something from one that did not, which is the
        # whole of how it knows the world has settled.
        self.revision = 0
        # Words a domain expects a person to type. Only the prompt reads
        # this (to autocorrect); nothing here affects what a system finds.
        self.vocabulary: set = set()

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

    def destroy(self, entity: Entity) -> bool:
        """It is not here any more, and neither is anything on it. True if
        it was. What a system calls on an occasion it has finished with."""
        if self._entities.pop(entity.id, None) is None:
            return False
        for bucket in self._by_type.values():
            bucket.pop(entity.id, None)
        self.revision += 1
        return True

    def attach(self, entity: Entity, *components) -> Entity:
        """Put these components on it, replacing any of the same type.

        A component equal to the one already there is not a change: it is
        not stored again and `revision` does not move, so a system that
        recomputes the same answer every tick still lets the world settle.
        """
        if entity.id not in self._entities:
            raise ValueError("%r is not in this world" % (entity,))
        for component in components:
            bucket = self._by_type.setdefault(type(component), {})
            if bucket.get(entity.id) == component:
                continue
            bucket[entity.id] = component
            self.revision += 1
        return entity

    def detach(self, entity: Entity, *kinds) -> bool:
        """Take these component types off it. True if any were there."""
        gone = False
        for kind in kinds:
            if self._by_type.get(kind, {}).pop(entity.id, None) is not None:
                self.revision += 1
                gone = True
        return gone

    def changed(self, entity=None) -> None:
        """Something changed that no attach said -- an index a domain keeps
        by hand, mutated in place. See the ⚠ at the top of this module."""
        self.revision += 1

    def learn(self, *words) -> None:
        """Add words to what the prompt will pull a typo towards."""
        self.vocabulary.update(str(word) for word in words)

    # -- reading -----------------------------------------------------

    def alive(self, entity: Entity) -> bool:
        return entity.id in self._entities

    def get(self, entity: Entity, kind):
        """That component off that entity, or None."""
        return self._by_type.get(kind, {}).get(entity.id)

    def has(self, entity: Entity, *kinds) -> bool:
        return all(entity.id in self._by_type.get(k, {}) for k in kinds)

    def each(self, *kinds, without=()) -> "list":
        """Every entity carrying all of these components, oldest first::

            for entity, entry, size in w.each(Entry, Size):
            for entity, wish in w.each(RenameWish, without=NeedsApproval):

        One tuple per match: the entity, then its components in the order
        asked for. Materialised, not lazy -- a system is expected to spawn
        and destroy while it walks what it found.
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
            out.append((self._entities[entity_id],)
                       + tuple(bucket[entity_id] for bucket in buckets))
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
            return bucket[entity_id]
        return None

    def components(self, entity: Entity) -> "list":
        """Everything on it, in the order the types were first seen."""
        return [bucket[entity.id] for bucket in self._by_type.values()
                if entity.id in bucket]

    def entities(self) -> "list":
        """Every entity, in the order it was spawned."""
        return [self._entities[i] for i in sorted(self._entities)]

    def show(self, entity: Entity) -> str:
        """`#7  Entry(folder=#1, name='todo.txt')  Size(bytes=17)`"""
        return "%-5s %s" % (entity, "  ".join(
            repr(c) for c in self.components(entity)))

    def __len__(self) -> int:
        return len(self._entities)

    def __contains__(self, entity) -> bool:
        return isinstance(entity, Entity) and entity.id in self._entities
