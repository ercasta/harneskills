"""The dungeon, made playable.

`ugm/rules/dungeon.ugm` is a turn-based fight authored entirely in the surface --
initiative, hit resolution, damage, fleeing, death and victory are all ordinary
rules, and the engine has never heard of a goblin. Upstream drives it as a batch
*expressibility test* (`python -m ugm.dungeon`): the player's three declarations
are `say` lines at the bottom of the corpus, the fight runs to quiescence, and
what is measured is whether the corpus could be written at all.

What is missing for a person is only the middle of that: somewhere to stand while
it happens. This module supplies it, and supplies nothing else -- the corpus is
loaded **unmodified** apart from the two changes upstream's own runner makes, and
every rule of the game stays where it was authored.

**The two changes, both upstream's own.**

1. `causes` → `implies`. `ugm.dungeon.fight` does this and explains why: a wound
   is an event, so `causes` is what it *means*, and `causes` makes the engine
   deposit a predicted moment per consequent member so a later observation can
   disagree with it. That is exactly right for an agent heating a kettle and dead
   weight for a game whose rules are never wrong -- measured upstream at 2.08s vs
   0.17s for the same fight. Which connective is *correct* is a separate question
   from which is affordable, and the corpus keeps `causes` as authored.
2. The three scripted `say player:` lines are dropped, because the player is now
   a person rather than a fixture.

**The three tools, and why they are here.** The surface has no arithmetic, no
ordering and no randomness, so the corpus asks for them by name:

    <dice>     roll(die, what, when)   the world, which nobody controls
    <arith>    calc(op, a, b)
    <compare>  beats(a, b)

They are reimplemented here rather than imported because upstream defines them as
closures inside `fight()`, which is a test harness and not a deployment. ⚠ That
is a real duplication and it is the kind that rots: if the corpus starts asking
for `d8` or `mul`, this file is the second place that has to learn about it. It
is accepted because these three are *boundary*, which is the harness's job --
dice are the world speaking, and arithmetic is a service. ⚠⚠ The clamp in `sub`
is upstream's judgement, kept verbatim and flagged there as the one rule of the
game stated in Python rather than in the corpus: a numeral is an atom whose name
reads as a number, and `-2` is not a name the surface can write.
"""

from __future__ import annotations

import os
import random
from typing import Dict, List, Optional

from .play import Cue, Scenario, first_arg_match, held, members_of, register
from .runner import Runner

SCOPE = "dungeon"

#: The dice the corpus names. A die it asks for that is not here is a decline --
#: *I have nothing to say* -- and not a crash, which is the one honest thing a
#: tool can do about a question outside its competence.
DICE = {"d4": 4, "d6": 6, "d20": 20}

#: How far a fight may run before we call it a runaway. Upstream's own limit.
LIMIT = 6000


def corpus_path() -> Optional[str]:
    """Where the engine keeps the corpus.

    Found through the installed `ugm` package rather than by a relative path, so
    it works from any working directory and follows the engine wherever it is
    checked out. Returns `None` if the demo is not in this engine build -- the
    scenario then simply does not offer itself.
    """
    try:
        import ugm
    except ImportError:
        return None
    path = os.path.join(os.path.dirname(ugm.__file__), "rules", "dungeon.ugm")
    return path if os.path.isfile(path) else None


def _install_tools(r: Runner, seed: Optional[int]) -> None:
    """⚠⚠⚠ Registered through the LOADER, never `Machine.answerer` with a bare
    string. A request relation minted beside the corpus's name table is a request
    nobody can write, and an answer built with `g.atom` is a node no rule can
    name. Both failures are silent -- the fight simply never lands a blow."""
    kb = r.loader(SCOPE)
    rng = random.Random(seed)

    def dice(mach, frame, e):
        die, _what, _when = mach.g.members(e.proposition)
        sides = DICE.get(mach.g.show(die))
        if sides is None:
            return None
        return kb.atom(str(rng.randint(1, sides)))

    def arith(mach, frame, e):
        op, a, b = (mach.g.show(x) for x in mach.g.members(e.proposition))
        if not (a.isdigit() and b.isdigit()):
            return None
        # ⚠ `add`/`sub`, NOT `plus`/`minus`: the machine's reserved vocabulary
        # binds those two names to the SIGN atoms and every corpus's table is
        # seeded from it, so `calc(minus, 5, 2)` resolves its operator to the
        # minus sign and the tool declines a request it should have answered.
        if op == "add":
            return kb.atom(str(int(a) + int(b)))
        if op == "sub":
            return kb.atom(str(max(0, int(a) - int(b))))   # THE CLAMP -- see above
        return None

    def compare(mach, frame, e):
        a, b = (mach.g.show(x) for x in mach.g.members(e.proposition))
        if not (a.isdigit() and b.isdigit()):
            return None
        return kb.atom("yes" if int(a) >= int(b) else "no")

    kb.answerer("dice", "roll", dice)
    kb.answerer("arith", "calc", arith)
    kb.answerer("compare", "beats", compare)


def setup(r: Runner, seed: Optional[int] = None) -> None:
    """Load the fight and wire its tools. Does not think -- `/run` does that."""
    path = corpus_path()
    if path is None:
        raise FileNotFoundError(
            "this ugm build has no rules/dungeon.ugm -- the demo is not in it"
        )
    _install_tools(r, seed)
    with open(path, "r", encoding="utf-8") as fh:
        src = fh.read()
    src = src.replace("= causes(", "= implies(")
    src = "\n".join(l for l in src.splitlines() if not l.startswith("say player:"))
    r.feed(src, scope=SCOPE, label=path)
    if seed is not None:
        # On the record as a fact, so the fight is reproducible and `why` can
        # reach the roll that killed you. `seed=None` is the genuinely external
        # die -- a fight nobody can replay is a fight nobody can argue about.
        r.feed(f"fact +seeded(<dice>, {seed})\n", scope=SCOPE)


# -- reading the fight -------------------------------------------------------


def combatants(r: Runner) -> List[str]:
    """The hero, then the monsters, in the order the corpus named them."""
    monsters = [members_of(r, n)[0] for n in held(r, "monster", SCOPE)]
    return ["hero"] + monsters


def hp_of(r: Runner, who: str) -> Optional[str]:
    args = first_arg_match(r, "hp", 0, who, SCOPE)
    return args[1] if args else None


def standing(r: Runner, who: str) -> bool:
    return r.machine.holds(r.term(f"present({who})", scope=SCOPE)) == "+"


def whose_turn(r: Runner) -> Optional[Dict[str, str]]:
    """Who is up, and in which round."""
    for n in held(r, "turn", SCOPE):
        who, rnd = members_of(r, n)
        return {"who": who, "round": rnd}
    return None


def verdict(r: Runner) -> Optional[str]:
    for n in held(r, "over", SCOPE):
        return members_of(r, n)[0]
    return None


def status(r: Runner) -> List[str]:
    """The scoreboard, read from the graph and from nowhere else."""
    out: List[str] = []
    up = whose_turn(r)
    end = verdict(r)
    if end:
        out.append(f"the fight is over: {end}")
    elif up:
        out.append(f"round {up['round']} -- {up['who']} to act")
    else:
        out.append("not started")
    out.append("")
    for who in combatants(r):
        hp = hp_of(r, who)
        if standing(r, who):
            where = "standing"
        elif any(members_of(r, n)[0] == who for n in held(r, "fled", SCOPE)):
            where = "fled"
        else:
            where = "down"
        marker = ">" if up and up["who"] == who and not end else " "
        out.append(f"{marker} {who:<9} hp {hp if hp is not None else '?':<3} {where}")
    return out


# -- where the player speaks -------------------------------------------------


def _spoken_for(r: Runner, rnd: str) -> bool:
    """Has the player already declared for this round?

    ⚠⚠⚠ Read from `arrived`, **not** from `intends`. An intention is three ticks
    downstream of the utterance -- `arrived` → `says` → `intends` -- and the cue
    is checked between ticks, so a cue that waited for the intention re-fired the
    instant it was answered and asked again, and again, for ever. `arrived` is
    the record the channel writes at the moment of delivery, which is exactly the
    question being asked here: *has this person spoken yet.* Whether the corpus
    goes on to believe them is `<trust-player>`'s business and none of ours.
    """
    g = r.machine.g
    for n in held(r, "arrived", SCOPE):
        args = g.members(n)
        if len(args) != 3 or g.show(args[0]) != "player":
            continue
        said = args[1]
        rel = g.relation_of(said)
        parts = g.members(said)
        if rel is None or not parts:
            continue
        # `declares(what, round)` or `passes(round)` -- either way this round has
        # been spoken to, which is the only thing the cue needs to know.
        if g.show(rel) == "declares" and len(parts) == 2 and g.show(parts[1]) == rnd:
            return True
        if g.show(rel) == "passes" and g.show(parts[0]) == rnd:
            return True
    return False


def _awaiting(r: Runner) -> Optional[Dict[str, str]]:
    """The hero is up, has not spent the turn, and nothing has been declared.

    ⚠ All three conditions matter. `turn` alone is a standing fact, so a cue on
    it would fire again the moment the machine came back; `may` is the right to
    act and acting spends it, which is what makes the turn an occasion.
    """
    if verdict(r) is not None:
        return None
    up = whose_turn(r)
    if up is None or up["who"] != "hero":
        return None
    rnd = up["round"]
    if r.machine.holds(r.term(f"may(hero, {rnd})", scope=SCOPE)) != "+":
        return None
    if _spoken_for(r, rnd):
        return None
    return {"round": rnd}


def _targets(r: Runner, ctx: Dict[str, str]) -> List[str]:
    return [f"attack({m})" for m in combatants(r)[1:] if standing(r, m)]


def _prompt(ctx: Dict[str, str]) -> str:
    return f"round {ctx['round']} -- what does the hero do?"


def _utterance(ctx: Dict[str, str], reply: str) -> Optional[str]:
    """The reply, as the corpus's own vocabulary.

    A bare monster name is accepted as shorthand for attacking it, because that
    is what a person types. Anything else is passed through untouched: the input
    language is the corpus language here as everywhere, so `attack(goblin2)` is
    the real form and a scenario that only accepted a menu choice would be a
    smaller game than the one that is authored.
    """
    text = reply.strip()
    if not text:
        return None                       # declining to declare is a move
    if "(" not in text:
        text = f"attack({text})"
    return f"declares({text}, {ctx['round']})"


def _passed(ctx: Dict[str, str]) -> str:
    """*I was asked and I said nothing.*

    ⚠ `passes` is vocabulary the corpus does not know, and that is deliberate
    rather than sloppy: a channel is where the world says things, and what the
    corpus makes of any of them is its own affair. `dungeon.ugm` has no rule for
    `passes`, so nothing follows from it and `<hero-holds>` -- the standing
    policy that acts when the player has declared nothing -- takes the turn,
    which is exactly the intended behaviour. What the utterance buys is that the
    pass is *on the record*, so the fight can be replayed and `why` can show that
    the hero swung on policy rather than on an order.
    """
    return f"passes({ctx['round']})"


DECLARE = Cue(
    name="declare",
    channel="player",
    detect=_awaiting,
    prompt=_prompt,
    options=_targets,
    utterance=_utterance,
    declined=_passed,
)


register(Scenario(
    name="dungeon",
    blurb="a turn-based fight, authored entirely in rules -- you are the hero",
    setup=setup,
    cues=(DECLARE,),
    status=status,
    over=verdict,
    scope=SCOPE,
))
