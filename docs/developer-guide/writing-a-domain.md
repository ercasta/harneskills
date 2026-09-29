# Writing a domain

A domain is a callable `install(loop)` in an importable module. Save this as `mykitchen.py` on your path:

```python
import dataclasses
from loopingrules.world import Reply, Said

@dataclasses.dataclass(frozen=True)
class Kettle:
    name: str

@dataclasses.dataclass(frozen=True)
class WantBoiled:
    pass

@dataclasses.dataclass(frozen=True)
class Boiling:
    pass

def install(loop):
    loop.rule(hear)
    loop.rule(boil)
    loop.world.spawn(Kettle("kettle"))   # install runs once, before any rule
    loop.world.learn("kettle", "boil")   # words for autocorrect

def hear(w):
    for entity, said in w.each(Said):
        if said.text == "boil the kettle":
            w.destroy(entity)
            for kettle, _ in w.each(Kettle):
                w.attach(kettle, WantBoiled())

def boil(w):
    for entity, kettle, _ in w.each(Kettle, WantBoiled):
        w.detach(entity, WantBoiled)
        w.attach(entity, Boiling())
        w.spawn(Reply("user", "the %s is boiling" % kettle.name))
```

```text
$ python -m harneskills --no-config mykitchen:install
harneskills> boil the kettle
the kettle is boiling
```

A rule calls the world directly, and `Loop.tick` runs one rule fully before the next, so `boil` sees what `hear` just did in the same tick.

## Conventions (none enforced)

- **`Said(user, "...")`** is what a typed line arrives as. A line no rule claims is reported as unheard.
- **`Reply(channel, "...")`** is the only thing printed unasked. Print once, then it is destroyed. `"user"` reaches every channel; a channel's own name reaches only it.
- **Destroy what you act on**, so the rule fires once and the loop settles.
- **Goals are components; tags mark state.** Model approval as a tag (`Approved`) that a person's answer attaches, rather than a callback -- and require it, so a wish nobody marked waits instead of running.
- **Name rules uniquely.** Rules are named `module.function`; a factory producing several closures must pass `name=`.
- **Never block.** Ask a question by spawning a `Reply` and record that you asked.

## Rival readings of one line: propose / arbitrate / act

When several rules might understand the same input, do not have them call each other. Each *responder* spawns a candidate tagged `Proposal`, an *arbiter* picks a winner and detaches the tag, and every consuming rule skips anything still tagged `Proposal`. Start with "first candidate wins". See [Propose / arbitrate / act](../intake processing.md); `fs.py` implements it with `propose_*` rules and `arbitrate_parse`.

## Tunable values

Model thresholds as components seeded in `install()` only if the restored world lacks one, so they persist and can be changed by rules. See [Tunable knobs](../tunable knobs.md).

## Process state vs. world state

State that belongs to *this process* (cwd, clock) must be replaced unconditionally at install, since a restored copy is stale. State that is a conclusion or a preference should be seeded only if absent.

## Exposing real tools

Put I/O in tool functions (like `fs_tools.ls`) and let a rule decide when one is warranted. `examples/automations.py` shows how to expose a *restricted* tool set through `loopingrules.circuits.Call`, where the trust boundary is the tools registered (a spec naming `rename` is refused at compile time).

## Trying it

- Add the spec to your [config file](../user-guide/config-and-state.md) or pass it on the command line.
- `/rules` shows registration order; `/show` shows the world; `/reload` re-imports your module after an edit.
- `Loop(trace=True)` traces which rules fired per tick.
