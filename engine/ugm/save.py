"""The world, on disk, so a restart is not an amnesia.

    save.write(world, "~/.local/state/harneskills/world.json")
    save.read(world, path)          # into an EMPTY world, before any domain

An entity is an integer and a component is a value with named fields, so
there is nothing here but that -- one JSON object PER LINE (JSONL), which is
what "an entity can carry several components of one type" wants: every
instance is already its own record, so there is no nested list to grow one
entry at a time. The first line is a header; every line after it is either a
component or a bare, component-less entity::

    {"version": 2, "next": 23}
    {"entity": 3, "type": "harneskills.examples.model:Folder", "fields": {"path": "/tmp/notes"}}
    {"entity": 7}

## A component is rebuilt WITHOUT its `__init__`

A dataclass's constructor takes its fields in declaration order, but
`object.__new__(cls)` plus setting each field straight into `__dict__` (or,
for a frozen one, via `object.__setattr__`) does not need to know that
order, or call `__init__` at all -- which also means a component saved
before a field was renamed comes back with exactly the fields it was saved
with, not a `TypeError` from a constructor that no longer matches.

## What a field may hold

`None`, `bool`, `int`, `float`, `str`, `list`, `tuple`, `dict` with string
keys -- nested however deep -- and nothing else. There is no `$entity`
wrapper here any more: `World.attach` already guarantees a component field
never holds a live `Entity`, only its plain id, so a reference to another
entity is already exactly the JSON-native int this format wants, with no
translation at either end. A tuple still needs `{"$tuple": [...]}`, because
JSON itself cannot tell a tuple from a list.

Anything else -- a set, an open file, a domain's own class instance -- is
refused by name when saving, rather than written as something it is not.
`World.attach` should have refused it long before it got this far; this is
the second, cheaper line of defence, not the first.

## Ids are preserved, and so is the counter

Restoring `#3` as `#3` is the whole point: every reference in every
component is that number. And `next` comes back too -- a world that
resumed its counter at 1 would hand a new entity an id some component is
still pointing at, and the two would silently become one thing.

## What is NOT saved

The RULES: a domain registers those in `install()`, from code, every
time. Anything a domain would rather recompute than restore is its own
business to reconcile -- see `fs.install`, which attaches a fresh `Session`
over the restored one so that the clock and the working directory are this
process's, while every folder and entry it had already learned stays
exactly where it was.

## Version 2, deliberately not silent about it

Version 1 was one JSON document holding a nested tree; this is one JSON
object per line. A version-1 file cannot be read a line at a time and a
version-2 file is not one `json.load` -- there is no way to mis-read one as
the other by accident, so a version that does not match is refused by name
rather than guessed at, the same policy version 1 already had for its own
future.
"""

from __future__ import annotations

import json
import os

VERSION = 2


class SaveError(ValueError):
    """A component this module will not pretend it can write."""


# -- writing -------------------------------------------------------------

def _field(value, where: str):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
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
                # `{"$tuple": ...}` is this format's own spelling for a
                # tuple; a field holding that key would come back as
                # something it never was.
                raise SaveError("%s: a dict key may not start with '$' (%r)"
                                % (where, key))
        return {k: _field(v, where) for k, v in value.items()}
    raise SaveError("%s: cannot save a %s" % (where, type(value).__name__))


def _name_of(kind) -> str:
    return "%s:%s" % (kind.__module__, kind.__qualname__)


def dump(world) -> "list[dict]":
    """The whole world, as a list of records -- a header first, then one
    per component instance, then a bare `{"entity": id}` for any entity
    that carries none. `write`/`read` are this, one record per line;
    `dump`/`load` are the pure, file-free form, for a caller (or a test)
    that wants the records themselves. Raises `SaveError` naming the
    component and field if anything in it will not go.
    """
    records = [{"version": VERSION, "next": world._next}]
    for entity in world.entities():
        components = world.components(entity)
        if not components:
            records.append({"entity": entity.id})
            continue
        for component in components:
            kind = type(component)
            fields = {}
            for f in component.__dataclass_fields__:
                value = getattr(component, f)
                fields[f] = _field(value, "%s %s.%s" % (entity, kind.__name__, f))
            records.append({"entity": entity.id, "type": _name_of(kind),
                            "fields": fields})
    return records


def write(world, path: str) -> None:
    """Save it, atomically. The directory is made if it is not there.

    Written to a temporary file beside the real one and then renamed,
    because the thing most likely to interrupt this is the restart it
    exists to survive -- and a half-written world is worse than an old
    one.
    """
    path = os.path.abspath(os.path.expanduser(path))
    records = dump(world)
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    temporary = path + ".tmp"
    # `newline=""` so text mode does not turn every `\n` into `\r\n` on
    # Windows. JSON would not mind, but a state file that is different
    # bytes depending on which machine wrote it is a file you cannot
    # compare, and this one is meant to be readable.
    with open(temporary, "w", encoding="utf-8", newline="") as fh:
        for record in records:
            fh.write(json.dumps(record, sort_keys=False))
            fh.write("\n")
    os.replace(temporary, path)


# -- reading -------------------------------------------------------------

def _rebuild(value, world):
    if isinstance(value, dict):
        if "$tuple" in value:
            return tuple(_rebuild(v, world) for v in value["$tuple"])
        return {k: _rebuild(v, world) for k, v in value.items()}
    if isinstance(value, list):
        return [_rebuild(v, world) for v in value]
    return value


def _kind(name: str):
    """`module:ClassName` -> the class.

    ⚠ The result is checked to BE a class. An attribute that resolves to
    something else reaches `object.__new__` and raises `TypeError` out of
    `load`, which costs the session rather than the component `load`
    promises to cost.
    """
    import importlib
    module_name, _, attr = name.partition(":")
    kind = importlib.import_module(module_name)
    for part in attr.split("."):
        kind = getattr(kind, part)
    if not isinstance(kind, type):
        raise ValueError("names a %s, not a class" % type(kind).__name__)
    return kind


def load(world, records: "list[dict]") -> "list[str]":
    """Put it all back, into a world that is empty. `records` is `dump`'s
    own shape: a header first, then one record per component or bare
    entity. Returns problems.

    A component whose class no longer exists -- a domain renamed, a
    version behind -- is SKIPPED and named, not raised: the entity keeps
    everything else it carried, and a state file outliving one refactor
    should cost you that component, not the session.
    """
    if len(world) or world._next:
        raise ValueError("load() wants an empty world")
    if not records or records[0].get("version") != VERSION:
        got = records[0].get("version") if records else None
        return ["state file is version %r, this is version %d" % (got, VERSION)]
    header, body = records[0], records[1:]
    problems: "list[str]" = []
    classes: dict = {}
    # Adopt every id FIRST: a component may hold a reference to an entity
    # that appears later in the file, and a handle has to be to something.
    for record in body:
        world._adopt(int(record["entity"]))
    for record in body:
        entity = world._adopt(int(record["entity"]))
        if "type" not in record:
            continue        # a bare entity -- nothing further to rebuild
        name = record["type"]
        if name not in classes:
            try:
                classes[name] = _kind(name)
            except (ImportError, AttributeError, ValueError, TypeError) as e:
                classes[name] = None
                problems.append("%s: %s" % (name, e))
        kind = classes[name]
        if kind is None:
            continue
        component = object.__new__(kind)
        for field_name, value in record.get("fields", {}).items():
            object.__setattr__(component, field_name, _rebuild(value, world))
        world.attach(entity, component)
    # After the entities, never before: `_adopt` keeps the counter above
    # every id it has seen, and the file's own `next` is what a world that
    # destroyed its highest entity before saving needs to come back to.
    world._next = max(world._next, int(header.get("next", 0)))
    return problems


def read(world, path: str) -> "list[str]":
    """`load` what is at `path`. Returns problems -- and a file that is not
    there is not one: it is the ordinary case for a first run, and it
    means an empty world, exactly as if it held nothing."""
    path = os.path.abspath(os.path.expanduser(path))
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except FileNotFoundError:
        return []
    except OSError as e:
        return ["%s: %s" % (path, e)]
    try:
        records = [json.loads(line) for line in lines if line.strip()]
    except ValueError as e:
        # Corrupt, truncated, unreadable. An empty world and a message
        # beats refusing to start -- the file is still there to look at.
        return ["%s: %s" % (path, e)]
    return load(world, records)
