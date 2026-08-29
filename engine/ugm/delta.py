"""What a rule RETURNS instead of touching a world: a description of a
change, not the change itself. `ugm.loop.Loop.tick` is the only thing
that ever applies one.

    def flag_big(w):
        deltas = []
        for entity, hunt in w.each(BigHunt):
            deltas.append(destroy(entity))
            for e, entry, size in w.each(Entry, Size):
                if entry.folder == hunt.folder and size.bytes >= hunt.floor:
                    deltas.append(attach(e, Big()))
        return deltas

Four kinds, one free function each, mirroring `World`'s own four writing
methods by name -- `spawn`, `attach`, `detach`, `destroy` -- so porting a
rule that used to call `w.spawn(...)` is `spawn(...)`, appended to a
list, rather than a new vocabulary to learn. A rule may still call
`w.each`, `w.get`, `w.has`, `w.first`, `w.the` and every other READING
method exactly as before; only the four that move `world.revision` are
no longer its to call.

## A `spawn` you can use before it is real

`spawn(*components)` hands back a `Spawn`, and `.entity` on it is a
`Pending` -- not an `Entity`, and not usable to READ the world with (it
is not there yet), but usable everywhere a delta or a component asks for
the entity it names: `attach(e, Foo())` where `e` is that same
`Pending`, or embedded inside another component's own field
(`ListWanted(e)`), even nested in a `dict` or `tuple` a component holds
(`Contents.by_name`'s values, say). `Loop.tick` resolves every `Pending`
the moment its `Spawn` is applied, walking every later delta in the SAME
list, and every field of every component in it, for the same token --
see `_resolve`. It is built the way `ugm.save` already rebuilds a
component coming back off disk: `object.__new__` and a fresh `__dict__`,
because there is no constructor signature this could call in general
(see `_resolve_component`).

A `Pending` is *sugar for staying inside one rule's own turn*, not a
second kind of entity. `Loop.tick` applies one rule's deltas right
after calling it, before the next rule runs -- so a `Pending` never
needs to survive past the list it was born in, and a rule that wants
to act on something ANOTHER rule just made waits for the next tick and
reads it back off the world, an ordinary `Entity`, the same as always.
"""

from __future__ import annotations


class Pending:
    """A stand-in for an entity a `Spawn` in the SAME list of deltas is
    about to make real. Never touches a world -- `Loop.tick` is the only
    thing that ever resolves one, to the `Entity` its `Spawn` becomes.

    Compares by identity, on purpose: two `Pending`s are two DIFFERENT
    entities-to-be even if nothing yet distinguishes them, the same as
    two blank `Entity` ids never collide only because both are unmade.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return "Pending(#%d)" % id(self)


class Delta:
    """Nothing of its own -- a common ancestor so `Loop.tick` can refuse
    anything that is not one of the four kinds below, by name, rather
    than fail three frames later on whatever it was mistaken for."""

    def _apply(self, world, resolved: dict):
        raise NotImplementedError


class Spawn(Delta):
    """A new entity, carrying these components, once applied. `.entity`
    is a `Pending` -- usable right away in the rest of THIS list."""

    def __init__(self, *components) -> None:
        self.components = components
        self.entity = Pending()

    def __repr__(self) -> str:
        return "Spawn(%s) -> %r" % (", ".join(repr(c) for c in self.components),
                                    self.entity)

    def _apply(self, world, resolved: dict) -> None:
        components = [_resolve_component(c, resolved) for c in self.components]
        resolved[self.entity] = world.spawn(*components)


class Attach(Delta):
    """These components, onto that entity -- an `Entity` from an earlier
    tick, or a `Pending` an earlier `Spawn` in THIS list named."""

    def __init__(self, entity, *components) -> None:
        self.entity = entity
        self.components = components

    def __repr__(self) -> str:
        return "Attach(%r, %s)" % (self.entity,
                                   ", ".join(repr(c) for c in self.components))

    def _apply(self, world, resolved: dict) -> None:
        entity = _resolve_value(self.entity, resolved)
        components = [_resolve_component(c, resolved) for c in self.components]
        world.attach(entity, *components)


class Detach(Delta):
    """Every component of these types, off that entity."""

    def __init__(self, entity, *kinds) -> None:
        self.entity = entity
        self.kinds = kinds

    def __repr__(self) -> str:
        return "Detach(%r, %s)" % (self.entity,
                                   ", ".join(k.__name__ for k in self.kinds))

    def _apply(self, world, resolved: dict) -> None:
        entity = _resolve_value(self.entity, resolved)
        world.detach(entity, *self.kinds)


class Replace(Delta):
    """These components, each replacing every existing component of ITS
    OWN type on that entity -- `World.replace`, for a kind meant to stay
    singular (`Session`, `Contents`, a folder's `Size`)."""

    def __init__(self, entity, *components) -> None:
        self.entity = entity
        self.components = components

    def __repr__(self) -> str:
        return "Replace(%r, %s)" % (self.entity,
                                    ", ".join(repr(c) for c in self.components))

    def _apply(self, world, resolved: dict) -> None:
        entity = _resolve_value(self.entity, resolved)
        components = [_resolve_component(c, resolved) for c in self.components]
        world.replace(entity, *components)


class Remove(Delta):
    """One component equal to this value, off that entity -- leaving any
    other instances of the same type standing. `World.detach` still clears
    a whole type; this is the one-value counterpart a multi-valued type
    needs."""

    def __init__(self, entity, component) -> None:
        self.entity = entity
        self.component = component

    def __repr__(self) -> str:
        return "Remove(%r, %r)" % (self.entity, self.component)

    def _apply(self, world, resolved: dict) -> None:
        entity = _resolve_value(self.entity, resolved)
        component = _resolve_component(self.component, resolved)
        world.remove(entity, component)


class Destroy(Delta):
    """That entity, and everything on it, gone."""

    def __init__(self, entity) -> None:
        self.entity = entity

    def __repr__(self) -> str:
        return "Destroy(%r)" % (self.entity,)

    def _apply(self, world, resolved: dict) -> None:
        entity = _resolve_value(self.entity, resolved)
        world.destroy(entity)


def spawn(*components) -> Spawn:
    """`deltas.append(spawn(Size(4300)))`. `.entity` on the result is the
    `Pending` naming what it makes -- read it the same call:
    `s = spawn(Entry(folder, name)); deltas.append(s); entity = s.entity`.
    """
    return Spawn(*components)


def attach(entity, *components) -> Attach:
    return Attach(entity, *components)


def detach(entity, *kinds) -> Detach:
    return Detach(entity, *kinds)


def replace(entity, *components) -> Replace:
    return Replace(entity, *components)


def remove(entity, component) -> Remove:
    return Remove(entity, component)


def destroy(entity) -> Destroy:
    return Destroy(entity)


# -- resolving `Pending`, including inside a component's own fields ------

def _resolve_value(value, resolved: dict):
    """Any value a component field might hold: the SAME generic walk
    `ugm.save` does for an `Entity` coming back off disk (`$entity`,
    `$tuple`, a plain `dict`/`list`) -- a `Pending` embedded in one is
    exactly as ordinary as an `Entity` embedded there, and for the same
    reason: relationships are spelled by holding the thing they are
    about, not by a name a delta cannot see inside.
    """
    if isinstance(value, Pending):
        try:
            return resolved[value]
        except KeyError:
            raise ValueError(
                "%r is not the entity of a Spawn earlier in this same "
                "list of deltas -- a Pending only resolves within the "
                "list its own Spawn was returned in" % (value,)) from None
    if isinstance(value, tuple):
        return tuple(_resolve_value(v, resolved) for v in value)
    if isinstance(value, list):
        return [_resolve_value(v, resolved) for v in value]
    if isinstance(value, dict):
        return {k: _resolve_value(v, resolved) for k, v in value.items()}
    return value


def _resolve_component(component, resolved: dict):
    """The SAME component, if none of its fields named a `Pending`; a
    FRESH one, with each resolved, otherwise. Built without its
    `__init__` -- `object.__new__` and a restored `__dict__` -- because a
    component's constructor takes whatever arguments its author wrote,
    not necessarily its field names (`ugm.save.load` rebuilds one the
    same way, for the same reason).
    """
    fields = vars(component)
    resolved_fields = {name: _resolve_value(value, resolved)
                       for name, value in fields.items()}
    if resolved_fields == fields:
        return component
    fresh = object.__new__(type(component))
    fresh.__dict__.update(resolved_fields)
    return fresh
