# Overview

- **Components are plain `@dataclasses.dataclass` instances.** No
  `Component` base class to inherit — `dataclasses.is_dataclass` is the
  whole test. Free `__init__`/`__eq__`/`__repr__`; `frozen=True` is the
  convention for "never mutate in place," not yet enforced.
- **An entity may carry several components of one type.** `attach`
  appends (deduped by value); `replace` clears a type down to one value,
  for the naturally-singular case (`Session`, `Contents`); `remove` takes
  off one specific value, leaving siblings of the same type standing.
  `get` refuses to guess between several (`ValueError`); `get_all`/`all`
  read the plural case, per-entity and world-wide respectively.
- **A component field holds no live `Entity`.** Only
  `None`/`bool`/`int`/`float`/`str` and `list`/`dict`/`tuple` of those — a
  reference to another entity is its plain id. `World.attach` lowers a
  handle passed in and refuses anything else, naming the field, so this
  is enforced once, not documented and hoped for. `world.entity(id)`
  turns an id back into a handle.
- **`ugm.save` is JSONL**, one record per line (a header, then one per
  component instance, or a bare `{"entity": id}`) — version 2, and a
  version-1 file is refused by name rather than mis-parsed. The
  `__ugm_save__`/`module:factory(arg)` mechanism (for a class minted at
  runtime, like `facts.relation()`'s) was dropped along with `facts.py`'s
  quarantine below; nothing else needed it.

`facts.py` / `arbitration.py` / `request.py` are **on hold, not deleted**:
they do not currently import (`Relation` subclassed the removed
`Component`), `ugm/__init__.py` no longer imports them, and their tests
are `pytest.importorskip`'d rather than fixed. `harneskills.examples.fs`
— the one real domain on this engine — was ported to the new core and its
own suite is green, which is the case for "the five core files are
enough" that this rewrite was making.

## Open

- **The facts/relations question, deferred by design.** Does a
  `fact`/`state`/`deny` vocabulary belong in `ugm` at all — as a thin,
  clearly-optional helper library for a documented pattern — or does
  every domain on this engine write its own components and its own
  `each()` queries, the way `harneskills.examples.fs` already does with
  no such layer? `arbitration.py`'s `DECISION_PATTERNS.md` argument (why
  a generic reader beats agency in the base rule) stands regardless of
  the answer; what's undecided is whether it ships as code in this
  package. `request.py` is the same question, one layer up.
- Helper functions for one-liner rules (lambdas) — the shape a rule
  keeps repeating by hand (`for entity, x in w.each(Kind): ...`) might
  want its own sugar; open whether that's a `World`/`Loop` method or a
  recipe left to a domain.
- Moreover: i want the ugm engine in this repo to replace the ../ugm
  engine (but i thought we already migrated it to ../ugm) — unresolved;
  needs a look at what `../ugm` currently is before this is actionable.
