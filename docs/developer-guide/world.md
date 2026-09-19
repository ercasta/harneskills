# The world

Provided by `loopingrules.world`; summarised here because every domain leans on it.

## Components

A component is a plain `@dataclasses.dataclass`, conventionally `frozen=True`. No base class.

```python
@dataclasses.dataclass(frozen=True)
class Size:
    bytes: int

@dataclasses.dataclass(frozen=True)
class Stale:      # a tag: no fields, every instance equal
    pass
```

- **Values only.** Fields may hold `None`, `bool`, `int`, `float`, `str` and `list`/`dict`/`tuple` of those. Another entity is referenced by its plain id; `World.attach` lowers a handle and rejects anything else, naming the field.
- **Replace, don't mutate.** `attach(e, Size(4300))`, never `size.bytes = 4300`; a mutation in place is a change nothing can see.
- **An entity may carry several components of one type.** `attach` appends (deduped by value), `replace` clears the type to one value, `remove` takes off one value, `detach` takes off the type. `get` raises `ValueError` if there are several; use `get_all`.

## Writing

```python
entry = w.spawn(Entry(folder, "notes.txt"), Size(2048))
w.attach(entry, Stale())
w.replace(entry, Size(4300))
w.detach(entry, Stale)
w.remove(entry, some_component)
w.destroy(entry)
```

## Reading

```python
w.each(Entry, Size, without=IsDir)   # [(entity, entry, size), ...] rarest type first, oldest entity first
w.first(Kind)                        # first match or None
w.the(BigFloor)                      # the single instance (raises otherwise)
w.all(Kind)                          # every instance world-wide
w.get(entity, Kind); w.get_all(entity, Kind); w.has(entity, Kind)
w.components(entity); w.entities(); w.show(entity)
```

Queries are intersections. Relationships are just component fields holding an entity id (`Entry(folder=#1, name='todo.txt')`).

## Shared vocabulary

`loopingrules.world` provides `Said(user, text)`, `Reply(channel, text)` and `Proposal`, plus helpers `propose`, `reply`, `arbitrate`, `census`. They are shared so independently installed domains agree on what an unresolved candidate is. `w.learn(...)` registers words for autocorrect.

## Persistence

`loopingrules.save` writes JSONL (version 2; older versions are refused by name). `@loopingrules.world.transient` marks a component that must not be saved. `loopingrules.share` exports a named subset between worlds, remapping ids (fields holding entity ids must be marked `share.ref()`).
