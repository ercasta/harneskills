# Propose / arbitrate / act — one occasion, several rival readings

A pattern for the recurring shape "several rules might each have an opinion about
the same thing; exactly one opinion should become real." First applied to
understanding a typed line (`harneskills.examples.fs`'s `hear` used to be one
`_understand` function trying every reading in turn; it is now this pattern,
worked in full below). The name says what it is, not what domain it is for:
nothing about it is specific to parsing text, and it is expected to be
applied again — `../pystrider` is the next domain in line, where more than one
recognizer or generator rule can have an opinion about the same span of code.

## The shape

One **occasion** — an ordinary entity, meaning nothing more than "a thing to
decide about." Any number of **responder** rules may look at it and spawn a
**candidate**: a fresh entity, tagged `Proposal`, carrying whatever component
would make that reading real. One **arbiter** rule then picks a winner,
discards the rest, and detaches the tag — which is the literal *bind*: the
winning candidate's own component is now real, and every rule that consumes
it can finally see it, because it was written all along to skip anything
still tagged `Proposal`.

`Proposal` is `ugm.world.Proposal` — a shared tag, not a domain's own
component, and not something `fs.py` (or any domain) defines any more.
Two domains cannot recognize or correctly skip each other's unresolved
candidates without agreeing what the tag means, the same reason `Said`
and `Reply` live there rather than in whichever domain happened to need
a channel first. Nothing else here moved: the OCCASION type (`fs.py`'s
`ParseRequest`) and the ARBITER (`arbitrate_parse`) stay in the domain
that owns the conflict they resolve — see engine/README.md's History,
"Proposal, a shared tag."

```
ParseRequest              -- the occasion (fs.py's own type; call it
                              whatever the domain's occasion actually is)
Proposal(occasion)        -- tags a candidate entity: "one reading, not yet real"
<goal component>          -- rides alongside Proposal on the SAME candidate entity;
                              whatever a winning candidate should mean once real
```

A responder rule is `for occasion in w.each(Occasion): if I recognize it:
w.spawn(Proposal(occasion.id), MyReading(...))` — nothing more. It is not
aware of any other responder, does not know how many other candidates
exist, and does not decide who wins. That is what makes responders
addable and removable independently: `fs.py`'s four `propose_*` rules
already each cover one disjoint shape of line, added and (were they ever
wrong) removable one at a time, with the arbiter and everything
downstream untouched.

## The arbiter starts trivial, and mostly stays that way

**There is no general algorithm for this, and there will never be one.**
Reality does not obey the wishes of those who would like to find one. The
right arbiter for a domain is whatever the domain's own rules actually need,
discovered by hitting a real conflict — not designed up front against an
imagined one. Concretely:

- **Start with "first candidate registered wins."** `fs.py`'s
  `arbitrate_parse` is exactly this, in five lines, and it is very likely
  correct for a domain whose responders recognize genuinely disjoint shapes
  — which is the common case, because most of the time a proposer either
  reads the occasion or it doesn't.
- **Grow it only at the rule that actually collides.** A priority field on
  `Proposal`, a `ranked`-style score, a hard veto that a judge can name —
  add whichever ONE of these the actual conflict calls for, to the arbiter
  that owns it, when two real candidates actually compete for one occasion.
  Nothing about the pattern requires deciding this in advance for every
  future occasion a domain might ever have.
- **A generic, reusable "judge" module is not the goal**, and this repo has
  already tried and reversed that call once — `engine/DECISION_PATTERNS.md`
  is the design note for a fuller `candidate`/`ruled_out`/`ranked`/`winner`
  vocabulary, built as `ugm/arbitration.py`, and then deleted because nothing
  in this repository ever ended up needing it as *generic* infrastructure
  (`README.md`'s "Facts/arbitration/request removed" History entry). Reuse
  that vocabulary's NAMES when a domain's own arbiter grows past "first
  wins" — a `ruled_out`/`ranked` split is a good idea worth stealing — but
  write the rule inside the domain that needs it, not as a module every
  domain is expected to import.

## What "bind" means, concretely

The arbiter:

1. Collects every candidate whose `Proposal.request` names this occasion.
2. If there are none, the occasion itself is destroyed (nobody had a
   reading) — whatever spawned it (in `fs.py`, a `Said`) is left exactly as
   it was, for something else to notice or report.
3. If there is more than one, every candidate but the winner is destroyed
   outright — a losing candidate never gets to act, never gets to reply,
   never gets to leave a trace.
4. The winner has `Proposal` detached. Same entity, same goal component,
   now real. Whatever rule was already written to skip a `Proposal`-tagged
   entity (`w.each(Goal, without=Proposal)`) picks it up — this tick, if the
   arbiter is registered ahead of it, same as every other ordering question
   in this engine (**rule order is the whole of arbitration** for WHICH
   Python function runs when; this pattern is the answer for WHICH
   candidate a business decision resolves to — two different questions that
   happen to share a word).
5. The occasion entity itself is destroyed.

## Recursion falls out for free

An occasion is "any entity a `Proposal` was deposited against" — nothing
mints it specially, and nothing about resolving one occasion cares whether
it happened inside a responder rule that is, itself, in the middle of
answering a DIFFERENT occasion. A responder building a candidate reading for
one request may spawn a nested request of the same kind as one step in
building its answer — a chat-parsing responder recognizing "and then
explain the second part" can itself raise a fresh occasion for "the second
part" and let the SAME rules resolve it, one tick later, before the outer
candidate is complete. No special machinery for "nested" — it is the same
few rules asking the same few questions about one more entity.

## The worked example

`harneskills.examples.fs`'s `hear`/`propose_list`/`propose_big`/
`propose_stale`/`propose_typed_rename`/`arbitrate_parse` (see `fs.py`'s own
module docstring, "Understanding a line is the SAME propose/arbitrate/act
shape") is the full pattern, applied to turning a typed line into a goal.
It replaced one `_understand` function that tried every reading in a fixed
Python `if`/`elif` chain — behaviorally identical (each responder still
recognizes a disjoint shape, so there was never real rivalry to arbitrate),
but now four independently addable rules and one five-line arbiter instead
of one function that grows a new `if` branch, in the middle, every time this
domain learns one more thing to understand.

`fs.py` also already had a NARROWER version of "propose, then let something
else decide" before this pattern had a name: `RenameWish` + `NeedsApproval`
is one candidate, held or not, resolved by a person's own "y"/"n" rather
than by an automatic arbiter — the one-candidate, one-tick-per-answer
special case of the same idea. Reading that alongside `arbitrate_parse` is
the fastest way to see what is genuinely new here (several RIVAL
candidates, judged in the SAME tick) and what was already present (one
candidate, held until something outside the tick resolves it).

## Where this goes next

`../pystrider` is the second domain expected to use this shape, for the
place its own note already named the failure: "ANY rule family that decides
for itself whether to fire has an opinion about registration order, whether
or not its author meant it to" (`engine/DECISION_PATTERNS.md`). A pattern
match rule and a generation rule that can both apply to the same span
become two responders proposing against one occasion, judged by one small,
domain-owned arbiter — not a bug about which one happened to run first.
