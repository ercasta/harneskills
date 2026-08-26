"""The world, on disk, so a restart is not an amnesia.

    save.write(world, "~/.local/state/harneskills/world.json")
    save.read(world, path)          # into an EMPTY world, before any domain

An entity is an integer and a component is a value with named fields, so
there is nothing here but that::

    {"version": 1, "next": 23, "entities": [
       {"id": 3, "components": [
          {"type": "harneskills.examples.model:Folder",
           "fields": {"path": "/tmp/notes"}}]}]}

## A component is rebuilt WITHOUT its `__init__`

`Entry(folder, name)` takes positional arguments that are not its field
names, and `Contents()` takes none at all -- there is no signature a
loader could call in general. So a component comes back as
`object.__new__(cls)` with its `__dict__` restored: the same fields it
was saved with, whatever its constructor happens to want. A domain is
free to write any `__init__` it likes and this keeps working.

The cost is that `__init__`'s own coercions do not run on the way back.
`Size(num_bytes="17")` stores `17` because its constructor says
`int(...)`; a `Size` restored from a file gets exactly what was written,
which is the `17` that was stored. Save what you mean.

## What a field may hold

`None`, `bool`, `int`, `float`, `str`, `list`, `tuple`, `dict` with
string keys, and an `Entity` -- nested however deep. An entity is written
`{"$entity": 3}` and comes back as a handle on the world being loaded
into, which is what makes `Entry(folder=#3)` and `Contents.by_name` mean
the same thing after a restart as before it. A tuple is written
`{"$tuple": [...]}` rather than as a bare list, because a field that goes
in a tuple and comes out a list is the kind of change nothing notices
until something compares them.

Anything else -- a set, an open file, a domain's own class -- is refused
by name when saving, rather than written as something it is not.

## Ids are preserved, and so is the counter

Restoring `#3` as `#3` is the whole point: every reference in every
component is that number. And `next` comes back too -- a world that
resumed its counter at 1 would hand a new entity an id some component is
still pointing at, and the two would silently become one thing.

## What is NOT saved

The vocabulary: a domain registers it in `install()`, from code, every
time. Anything a domain would rather recompute than restore is its own
business to reconcile -- see `fs.install`, which attaches a fresh
`Session` over the restored one so that the clock and the working
directory are this process's, while every folder and entry it had
already learned stays exactly where it was.
"""

from __future__ import annotations

import json
import os

from .world import Entity

VERSION = 1


class SaveError(ValueError):
    """A component this module will not pretend it can write."""


# -- writing -------------------------------------------------------------

def _field(value, where: str):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Entity):
        return {"$entity": value.id}
    if isinstance(value, list):
        return [_field(v, where) for v in value]
    if isinstance(value, tuple):
        return {"$tuple": [_field(v, where) for v in value]}
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                raise SaveError("%s: a dict key must be a string, not %s"
                                % (where, type(key).__name__))
            if key.startswith("$"):
                # `{"$entity": ...}` is this format's own spelling for a
                # reference; a field holding that key would come back as
                # something it never was.
                raise SaveError("%s: a dict key may not start with '$' (%r)"
                                % (where, key))
        return {k: _field(v, where) for k, v in value.items()}
    raise SaveError("%s: cannot save a %s" % (where, type(value).__name__))


def dump(world) -> dict:
    """The whole world, as plain data. Raises `SaveError` naming the
    component and field if anything in it will not go."""
    entities = []
    for entity in world.entities():
        components = []
        for component in world.components(entity):
            kind = type(component)
            name = "%s:%s" % (kind.__module__, kind.__qualname__)
            components.append({"type": name, "fields": {
                field: _field(value, "%s %s.%s" % (entity, kind.__name__, field))
                for field, value in vars(component).items()}})
        entities.append({"id": entity.id, "components": components})
    return {"version": VERSION, "next": world._next, "entities": entities}


def write(world, path: str) -> None:
    """Save it, atomically. The directory is made if it is not there.

    Written to a temporary file beside the real one and then renamed,
    because the thing most likely to interrupt this is the restart it
    exists to survive -- and a half-written world is worse than an old
    one.
    """
    path = os.path.abspath(os.path.expanduser(path))
    data = dump(world)
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    temporary = path + ".tmp"
    # `newline=""` so text mode does not turn every `\n` into `\r\n` on
    # Windows. JSON would not mind, but a state file that is different
    # bytes depending on which machine wrote it is a file you cannot
    # compare, and this one is meant to be readable.
    with open(temporary, "w", encoding="utf-8", newline="") as fh:
        json.dump(data, fh, indent=1, sort_keys=False)
        fh.write("\n")
    os.replace(temporary, path)


# -- reading -------------------------------------------------------------

def _rebuild(value, world):
    if isinstance(value, dict):
        if "$entity" in value:
            return world._adopt(int(value["$entity"]))
        if "$tuple" in value:
            return tuple(_rebuild(v, world) for v in value["$tuple"])
        return {k: _rebuild(v, world) for k, v in value.items()}
    if isinstance(value, list):
        return [_rebuild(v, world) for v in value]
    return value


def _kind(name: str):
    """`module:ClassName` -> the class. Imported here and nowhere else --
    a state file names a domain's classes, and reading one is what makes
    that domain's module load."""
    import importlib
    module_name, _, attr = name.partition(":")
    kind = importlib.import_module(module_name)
    for part in attr.split("."):
        kind = getattr(kind, part)
    return kind


def load(world, data) -> "list[str]":
    """Put it all back, into a world that is empty. Returns problems.

    A component whose class no longer exists -- a domain renamed, a
    version behind -- is SKIPPED and named, not raised: the entity keeps
    everything else it carried, and a state file outliving one refactor
    should cost you that component, not the session.
    """
    if len(world) or world._next:
        raise ValueError("load() wants an empty world")
    if data.get("version") != VERSION:
        return ["state file is version %r, this is version %d"
                % (data.get("version"), VERSION)]
    problems, classes = [], {}
    # Adopt every id FIRST: a component may hold a reference to an entity
    # that appears later in the file, and a handle has to be to something.
    for record in data.get("entities", ()):
        world._adopt(int(record["id"]))
    for record in data.get("entities", ()):
        entity = world._adopt(int(record["id"]))
        for saved in record.get("components", ()):
            name = saved["type"]
            if name not in classes:
                try:
                    classes[name] = _kind(name)
                except (ImportError, AttributeError, ValueError) as e:
                    classes[name] = None
                    problems.append("%s: %s" % (name, e))
            kind = classes[name]
            if kind is None:
                continue
            component = object.__new__(kind)
            component.__dict__.update(
                {k: _rebuild(v, world) for k, v in saved.get("fields", {}).items()})
            world.attach(entity, component)
    # After the entities, never before: `_adopt` keeps the counter above
    # every id it has seen, and the file's own `next` is what a world that
    # destroyed its highest entity before saving needs to come back to.
    world._next = max(world._next, int(data.get("next", 0)))
    return problems


def read(world, path: str) -> "list[str]":
    """`load` what is at `path`. Returns problems -- and a file that is not
    there is not one: it is the ordinary case for a first run, and it
    means an empty world, exactly as if it held nothing."""
    path = os.path.abspath(os.path.expanduser(path))
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as e:
        # Corrupt, truncated, unreadable. An empty world and a message
        # beats refusing to start -- the file is still there to look at.
        return ["%s: %s" % (path, e)]
    return load(world, data)
