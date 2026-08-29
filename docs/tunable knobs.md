# Knobs are components, seeded once, mutable forever after

A pattern for a value that shapes a decision (a threshold, a floor, a preference)
and needs to be: tunable without a code change, changeable by a rule reacting to
what a person says, and — eventually — adjustable by something that has learned
from past sessions. First applied to `harneskills.examples.fs`'s `BigFloor` (how
many bytes make an entry `Big`), which used to be a bare module constant
(`BIG_BYTES`) baked in at import time.

## The shape

A knob is an ordinary component, in the SAME group `model.py` already names
"what a rule has concluded" (`Focus`, `Stale`) — not a process fact like
`Session`, and not a hidden Python global a rule reads around the world's
back. `flag_big` reads it exactly the way it reads anything else:

```python
floor = w.the(BigFloor).bytes
```

`install()` seeds it — but only if the restored world doesn't already have
one:

```python
if world.first(BigFloor) is None:
    world.spawn(BigFloor(int(os.environ.get("HARNESKILLS_FS_BIG_FLOOR", BIG_BYTES))))
```

That is the whole of it. No new engine feature, no separate persistence
path, no config-file format: `BigFloor` is written to `world.json` and
restored from it exactly like `Folder` or `Stale`, because it IS state of
that kind, not configuration threaded in from outside every time the
process starts.

## Why this is NOT the `Session` pattern

`fs.py` already had a component that looks superficially similar —
`Session`, replaced unconditionally at every install regardless of what was
restored, because `cwd`/`now` belong to *this process* and a restored copy
is always stale. It is tempting to treat a knob the same way ("read the env
var, replace the component, done") — resist that: `cwd` never accumulates
anything, and a knob is supposed to. Replacing `BigFloor` unconditionally at
every install would silently discard any preference a rule ever wrote and
anything a future tuner ever learned, every single restart. `model.py`'s
`Session` docstring and `BigFloor`'s own now say this explicitly, pointing
at each other, because the two policies sitting one class apart with no
comment between them is exactly the trap.

The rule of thumb: **replace unconditionally** for a value that is a fact
about the process running right now and never a conclusion; **seed only if
absent** for a value that is a conclusion — a knob included — that ought to
accumulate across restarts the same way `Stale`/`Big`/`Focus` already do.

## A rule can change a knob, and that costs nothing new

Because `BigFloor` is ordinary state, "the user expressed a preference that
changes a knob" is not a new mechanism — it is one more rule writing one
more component, mechanically identical to `_focus` moving `Focus` or
`do_rename` detaching `Stale`:

```python
w.replace(floor_entity, BigFloor(2000))
```

Whether that rule is reached directly (a typed command, no different from
`rename a to b` needing no approval) or through the propose/arbitrate
pattern (`docs/intake processing.md`) — if recognizing the preference could
ever collide with another responder in the same tick — is the same
decision as any other typed command; nothing about `BigFloor` forces either
choice.

## Where this goes: learned, not just told

An automatic tuner — something that reads past sessions or recorded
episodes and concludes a knob should be different — is a THIRD writer of
the exact same component. Whether it runs as a rule reacting to an
`Episode`/`Outcome`-shaped component this domain would need to start
recording, or as an external process that reads `world.json`, computes a
new `BigFloor`, and writes it back before the next `install()`, it uses
`attach`/`replace` the same as every rule already does. Nothing here is
built yet, and nothing needs to be built ahead of it: the moment a domain
has a real source of "what should this knob be," writing the answer costs
one line, because the substrate — a knob as a component, not a constant —
was already the whole of what building it required.

**Worth flagging, not yet building:** if a typed preference and a tuner's
own conclusion could ever land on the same knob in the same tick, that is a
literal instance of `docs/intake processing.md`'s occasion/candidate/
arbiter shape — two candidates, one `BigFloor`. Leave it until that
collision is real, the same call already made for `arbitrate_parse` itself.
