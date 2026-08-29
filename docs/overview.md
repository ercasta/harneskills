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
- **`loopingrules.save` is JSONL**, one record per line (a header, then one per
  component instance, or a bare `{"entity": id}`) — version 2, and a
  version-1 file is refused by name rather than mis-parsed. The
  `__ugm_save__`/`module:factory(arg)` mechanism (for a class minted at
  runtime, like `facts.relation()`'s) was dropped along with `facts.py`
  itself, below; nothing else needed it.
- **A rule writes to the world directly** — `spawn`/`attach`/`replace`/
  `detach`/`remove`/`destroy` — same as `install()` always did.
  `ugm.delta` (`Pending`, the six delta classes) is deleted, not
  deprecated; `Loop.tick` no longer applies anything after calling a
  rule because there is nothing left to apply. A "proposed" action is a
  component in the world (`fs.py`'s `RenameWish` + `NeedsApproval`), not
  a lower-level notion of "not yet real" underneath every write — see
  `loopingrules`'s own README.md's "Deltas removed" History entry for the
  argument in full, including a live example of the old contract silently
  not holding in this repo's own test suite.
- **"Systems" are "rules," everywhere** — `Loop.system`/`Facts.system` →
  `Loop.rule`/`Facts.rule`, `loop.systems` → `loop.rules`, the `/systems`
  REPL command → `/rules`. Not a rename for its own sake: "system" doubled
  as "the OS," "a filesystem," and the name of the one concept this
  package actually has, and only one of those meanings was ever this
  package's business.
- **`Loop.rule` takes `watches=` and `priority=`.** `watches=(Kind, ...)`
  skips calling a rule's body entirely on a tick where none of those
  component types exist yet (`World.populated`) — the fix for a large
  ruleset where most rules have nothing to do most ticks. `priority=N`
  — higher runs first, ties (the default, `0`) keep registration order —
  is the one deliberate override of "registration order is the whole of
  arbitration," for the one thing registration order can't express: two
  rules from domains that don't know about each other, both watching the
  same component type.

`facts.py` / `arbitration.py` / `request.py` are **deleted, not on
hold**: nothing in this repository ever imported any of the three
(`harneskills.examples.fs` writes its own components and its own
queries throughout), and once `world.py`'s rewrite left them unable to
import at all, there was no reason left to keep the code around waiting
on a decision the code itself couldn't inform. `loopingrules`'s own
`DECISION_PATTERNS.md` keeps the argument for a generic arbitration
reader; it is a design note now, not a description of shipped code.

## Open

- Helper functions for one-liner rules (lambdas) — the shape a rule
  keeps repeating by hand (`for entity, x in w.each(Kind): ...`) might
  want its own sugar; open whether that's a `World`/`Loop` method or a
  recipe left to a domain.
- ~~Moreover: i want the ugm engine in this repo to replace the ../ugm
  engine (but i thought we already migrated it to ../ugm) — unresolved;
  needs a look at what `../ugm` currently is before this is
  actionable.~~ Resolved, 2026-08-29: `../ugm` is `../loopingrules` now
  (carved out, renamed, published as its own repo). `./engine` (this
  repo's own embedded, pre-rename copy, importable as `ugm`) is deleted
  outright, not kept as a fallback — `dependencies = ["loopingrules"]`
  in `pyproject.toml`, `../loopingrules` a sibling checkout. See
  `README.md`'s Status, "The private `ugm` is gone."
