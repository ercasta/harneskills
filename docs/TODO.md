# TODO

Reviewed 2026-08-29, twice: first against the pre-existing `engine/ugm`
code (deltas/systems/request-response), then again after a core rewrite
the same day settled a more basic question — see "The core rewrite"
below. Resolved items are kept, struck through, with a pointer to what
answered them, so this file stays a record of what was asked, not just
what's left.

- ~~Maybe we don't need Deltas technically...~~ **Done.** `ugm.delta`
  (`spawn`/`attach`/`detach`/`destroy` as returned data, applied only by
  `Loop.tick`) shipped 2026-08-27; `replace`/`remove` joined it in the
  core rewrite below. `Loop.run` settles on a whole pass changing
  nothing, bounded by `budget` as the circuit breaker.
- ~~The engine must allow rules (systems)~~ **Done.** `Loop.system`, and
  a system may now declare `watches=` — the component types it could
  possibly act on — to stay uncalled entirely on a tick where none of
  them exist yet (`World.populated`).
- ~~General request/response protocol~~ Built as `engine/ugm/request.py`
  (request/respond/complete, a generic tick-ageing watchdog), but it sat
  on `ugm.facts`, which is itself now on hold — see below. Kept, not
  deleted; needs re-expressing in plain entities/components (or as an
  explicitly optional pattern library) once the facts/relations question
  resolves, same as `arbitration.py`.
- ~~Represent components as plain dicts... or as dataclasses~~ **Done**,
  as dataclasses — see the core rewrite below.
- ~~Allow multiple components of the same type on an entity (a list)~~
  **Done** — see the core rewrite below.

## The core rewrite, 2026-08-29

Working through the request/response item above surfaced a more basic
objection: `facts.py`/`arbitration.py`/`request.py` add real API surface
(`fact`/`state`/`deny`/`of`/`one`/`holds`, interning) on top of the five
files that are supposed to be the whole engine — and the engine's own
vocabulary should be entities and components, full stop, with a helper
library justified only if it is a genuine, optional aid for a documented
pattern rather than a second way to write a system.

The core landed first, before that question was decided:

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
- Helper functions for one-liner rules (lambdas) — the shape a system
  keeps repeating by hand (`for entity, x in w.each(Kind): ...`) might
  want its own sugar; open whether that's a `World`/`Loop` method or a
  recipe left to a domain.
- Moreover: i want the ugm engine in this repo to replace the ../ugm
  engine (but i thought we already migrated it to ../ugm) — unresolved;
  needs a look at what `../ugm` currently is before this is actionable.
