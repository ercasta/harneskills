"""Read-only projections of a running `ugm.Machine`, for a person to look at.

Nothing here decides anything, mutates anything, or recomputes anything the
engine already concluded. Every function is a *rendering*: it walks the graph and
the chain and returns plain rows, so the TUI (or a plain terminal, or a test) can
display them without knowing what a `Moment` is.

That constraint is the point. UGM's own argument is that everything it does is
already in the graph and the only thing missing was a way to be told; a viewer
that starts deriving its own facts is a second engine with no provenance. So the
rule for this module is: **read, group, sort, format — never conclude.**

The one classification we do make is by *layer*, and it is drawn from the
engine's own vocabulary rather than from a list we invented. `Machine.reserved`
is the set of names the machinery coined; anything a corpus coined itself is
therefore `world`. Among the reserved ones, `_LAYER_OF` sorts them into what a
reader is actually asking about — the goal search, the boundary, the bookkeeping
— and anything reserved but unlisted falls to `meta`, which is the safe default
because a new engine relation showing up as machinery is right by construction.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, NamedTuple, Optional, Sequence, Tuple

# The layers, in the order a reader wants them: what the corpus is about first,
# what the agent is trying second, how it is trying third, and the plumbing last.
LAYERS: Tuple[str, ...] = ("world", "goal", "act", "search", "talk", "meta")

#: What a reader is looking at, per layer, in one line each -- used for the
#: filter legend so the vocabulary is explained where it is used.
LAYER_HELP: Dict[str, str] = {
    "world": "what the corpus is about -- relations it coined itself",
    "goal": "what is wanted, the plans for it, and what they need",
    "act": "what left the agent, what it did, and what it expected",
    "search": "how it is looking -- fits, checks, recall, verdicts",
    "talk": "what arrived, who said it, and where it was loaded from",
    "meta": "the bookkeeping: rules as data, tools, standing, silences",
}

_LAYER_OF: Dict[str, str] = {
    # What is wanted and how it decomposes.
    "goal": "goal", "plan": "goal", "subgoal": "goal", "expands": "goal",
    "binds": "goal", "achieved": "goal", "blocked": "goal", "excluded": "goal",
    "pursued": "goal", "root": "goal", "rooted": "goal", "open": "goal",
    "reached": "goal", "prefer": "goal",
    # How the search is going.
    "fit": "search", "fits": "search", "unfit": "search", "need": "search",
    "check": "search", "unmet": "search", "verdict": "search",
    "support": "search", "unsupported": "search", "recall": "search",
    "recalled": "search", "again": "search", "answered": "search",
    "widened": "search", "close": "search", "depth": "search",
    "budget": "search", "bounded": "search", "tolerance": "search",
    "hypotheses": "search", "suppose": "search", "concluded": "search",
    "dormant": "search", "due": "search",
    # The outbound boundary and what it committed the agent to.
    "doing": "act", "did": "act", "taken": "act", "emitted": "act",
    "refused": "act", "expects": "act", "deviates": "act",
    # The inbound boundary, and where authored knowledge came from.
    "arrived": "talk", "says": "talk", "scoped": "talk", "loaded": "talk",
    # Everything else reserved -- rule/conn/ant/con, answers, standing,
    # exercised, quiet, enough, stopped, left, helped, harmed, forgone, not --
    # is machinery, and falls through to `meta`.
}

#: `holds()` signs, as words. A proposition with claims but no resolved sign is
#: *unsettled* -- two entries that cancel -- which is a real state and not a gap.
STATUS_WORDS = {"+": "held", "-": "denied", "?": "unsure"}
_STATUS = STATUS_WORDS   # the name used below, kept short at the call sites


class Prop(NamedTuple):
    """One proposition, as a reader sees it.

    ⚠ There is no `grade` field, and its absence is the design rather than an
    omission. Modality used to be a member of the entry (`@likely`); it is now a
    *proposition* -- `likely(p)` -- because a program has to be able to compute
    and ask about the modality of its own conclusion, which an annotation cannot
    support. The practical consequence for a viewer is good: uncertainty needs no
    special column, because `likely(rain(monday))` is an ordinary world fact and
    shows up in the `world` layer beside everything else.
    """

    node: int
    text: str            # `g.show` -- the term as it would be written
    sign: str            # '+' | '-' | '?' | '' when unsettled
    status: str          # held | denied | unsure | unsettled | BLOCKED
    layer: str
    source: str          # the channel it came through: kb, user, a domain
    licence: str         # what produced it: applied(<R>), loaded(...), an utterance
    moment: int          # the locus's depth, so a reader can see when
    claims: int          # how many entries are about it -- >1 means it was argued
    mention: bool        # a claim ABOUT a statement, not a claim in its voice
    generic: bool        # contains a variable: a pattern, not an occasion


class RuleRow(NamedTuple):
    """One rule, and whether it has earned anything."""

    node: int
    name: str
    connective: str      # causes | implies
    antecedent: Tuple[str, ...]
    consequent: Tuple[str, ...]
    bundled: bool        # shipped with the engine rather than authored here
    exercised: bool      # it applied at least once


class TreeRow(NamedTuple):
    """One line of the goal tree, with its indent recovered as a depth."""

    depth: int
    text: str
    kind: str            # section | goal | plan | note
    status: str          # held | BLOCKED | open | ''


# -- propositions -----------------------------------------------------------


def layer_of(m, relation: Optional[int]) -> str:
    """Which layer a relation belongs to.

    A relation the corpus coined is `world` by construction -- we do not need a
    list of domain vocabulary, because the engine already has the list of its
    own. That is the whole reason this is robust across engine changes: a new
    reserved relation lands in `meta` and a new domain relation lands in
    `world`, and neither needs this file edited.
    """
    if relation is None:
        return "world"
    name = m.g.show(relation)
    if name not in m.reserved:
        return "world"
    return _LAYER_OF.get(name, "meta")


def _blocked_wants(m) -> frozenset:
    """The things the agent has concluded it cannot get.

    Read from `blocked(w)` instances that hold, exactly as `Machine.report`
    reads them -- not recomputed, because *no rule fits this* is an aggregate
    over a finished search and only the engine is entitled to say it.
    """
    out = []
    for n in m.g.instances_of(m.BLOCKED):
        if m.holds(n) == "+" and m.g.members(n):
            out.append(m.g.member(n, 0))
    return frozenset(out)


def propositions(
    m,
    layers: Optional[Iterable[str]] = None,
    generic: bool = False,
    settled_only: bool = True,
) -> List[Prop]:
    """Every proposition anything has claimed, newest node last.

    Mint order is the engine's own tie-break (§3's determinism), so iterating
    node ids gives a stable, reproducible order and a reader watching the pane
    sees new conclusions arrive at the bottom rather than shuffling.

    `generic` includes patterns -- `heat(?a, kettle)` -- which are what an
    unbound subgoal looks like and are worth seeing when a plan is stuck.
    `settled_only` drops propositions whose entries cancel out; turn it off to
    see a contradiction as a contradiction.
    """
    wanted = set(LAYERS if layers is None else layers)
    blocked = _blocked_wants(m)
    rows: List[Prop] = []
    for n in range(m.g.count()):
        rel = m.g.relation_of(n)
        if rel is None:                      # an atom, not a proposition
            continue
        is_generic = m.g.has_var(n)
        if is_generic and not generic:
            continue
        entries = m.chain.claims_about(n)
        if not entries:
            continue
        lay = layer_of(m, rel)
        if lay not in wanted:
            continue
        sign = m.holds(n)
        if sign is None and settled_only:
            continue
        e = _resolved_entry(entries, sign)
        status = "BLOCKED" if n in blocked else _STATUS.get(sign or "", "unsettled")
        rows.append(Prop(
            node=n,
            text=m.g.show(n),
            sign=sign or "",
            status=status,
            layer=lay,
            source=m.g.show(e.source) if e is not None and e.source is not None else "",
            licence=m.g.show(e.licence) if e is not None and e.licence is not None else "",
            moment=e.locus.depth if e is not None else 0,
            claims=len(entries),
            mention=bool(e.mention) if e is not None else False,
            generic=is_generic,
        ))
    return rows


def _resolved_entry(entries: Sequence, sign: Optional[str]):
    """The entry a reader should be shown: the latest one that agrees with the
    resolved sign, so grade and provenance describe *what is believed* rather
    than whatever was claimed last and lost."""
    if not entries:
        return None
    if sign is not None:
        for e in reversed(entries):
            if e.sign == sign:
                return e
    return entries[-1]


def counts(m) -> Dict[str, int]:
    """How many settled propositions there are per layer -- the pane's header,
    and the cheapest possible answer to *is it still doing anything*."""
    out = {k: 0 for k in LAYERS}
    for p in propositions(m, generic=True):
        out[p.layer] = out.get(p.layer, 0) + 1
    return out


# -- the goal tree ----------------------------------------------------------

_SECTIONS = ("asked for:", "did:", "refused:", "still open when it tried to stop:")


def goal_tree(m) -> List[TreeRow]:
    """The goal / plan / subgoal tree, from the engine's own `report()`.

    ⚠ Deliberately parsed back out of `report()`'s indentation rather than
    rebuilt from `expands` / `subgoal` here. Rebuilding it would mean a second
    copy of the engine's argument about where to indent (a choice is a branch, a
    single plan is not), and the two copies would drift the first time upstream
    changed its mind. The indentation IS the structure; recovering it is lossless
    and the traversal stays in one place, upstream, where it is tested.
    """
    rows: List[TreeRow] = []
    for line in m.report():
        text = line.strip()
        if not text:
            continue
        depth = (len(line) - len(line.lstrip(" "))) // 2
        if text in _SECTIONS:
            rows.append(TreeRow(0, text, "section", ""))
            continue
        status = ""
        for word in ("held", "BLOCKED", "open"):
            if text.endswith(f"[{word}]") or f"[{word}]" in text:
                status = word
                break
        kind = "plan" if text.startswith("via ") else "goal"
        rows.append(TreeRow(depth, text, kind, status))
    return rows


# -- provenance -------------------------------------------------------------


def why(m, node: int) -> List[str]:
    """*Why do you believe that, and on whose word?*

    Straight through to `Machine.why`, which walks supports and consumed entries.
    The empty case is answered rather than shown as an empty list, because a
    proposition nothing concluded has no trail and saying so is the answer.
    """
    lines = m.why(node)
    if lines:
        return lines
    return ["nothing concluded it -- look for it as BLOCKED, or ask what is missing"]


# -- rules and tools --------------------------------------------------------


def rules(m, bundled: bool = False) -> List[RuleRow]:
    """Every rule the machine can bring to mind.

    `bundled` includes the engine's own conventions -- `<intake>`, `<denial>`,
    `<assert-act>` and the rest. They are ordinary rules and a reader chasing a
    surprising conclusion will eventually need to see them, but they are not
    what the corpus author wrote, so they are off by default.
    """
    shipped = {r.node for r in m.bundle}
    exercised = {
        m.g.member(n, 0)
        for n in m.g.instances_of(m.EXERCISED)
        if m.holds(n) == "+" and m.g.members(n)
    }
    out: List[RuleRow] = []
    for r in m.rules.rules:
        is_bundled = r.node in shipped
        if is_bundled and not bundled:
            continue
        out.append(RuleRow(
            node=r.node,
            name=r.name or m.g.show(r.node),
            connective=r.connective,
            antecedent=tuple(f"{mem.sign}{m.g.show(mem.pattern)}" for mem in r.antecedent),
            consequent=tuple(f"{mem.sign}{m.g.show(mem.pattern)}" for mem in r.consequent),
            bundled=is_bundled,
            exercised=r.node in exercised,
        ))
    return out


def tools(m) -> List[Tuple[str, str, bool]]:
    """The registered answerers: name, the request each answers, and whether the
    corpus still trusts it. A tool is retired by denying `answers(<t>, req)`, so
    *trusted* is read from the graph and not from the registry."""
    out = []
    for a in m.answerers:
        prop = m.g.rel(m.ANSWERS, a.node, a.request)
        out.append((a.name, m.g.show(a.request), m.holds(prop) == "+"))
    return out


def channels(m) -> List[Tuple[str, int]]:
    """Every channel, with how much has arrived on it. Outbound channels
    (actuators) are included -- a channel is one relation read either way."""
    out = []
    for c in m.channels.known():
        n = sum(
            1 for i in m.g.instances_of(m.ARRIVED)
            if m.g.members(i) and m.g.member(i, 0) == c and m.holds(i) == "+"
        )
        out.append((m.g.show(c), n))
    return out


# -- credit -----------------------------------------------------------------


def credit(m) -> Dict[str, List[str]]:
    """What earned its keep and what is to blame, as the engine judges it.

    `review` and `blame` walk licences, so they reach tools as well as rules --
    which is why they are grouped here rather than folded into `rules()`.
    """
    def pairs(items):
        return [f"{getattr(r, 'name', None) or m.g.show(getattr(r, 'node', 0))}  ->  {m.g.show(p)}"
                for r, p in items]

    return {"review": pairs(m.review()), "blame": pairs(m.blame())}


# -- the tick feed ----------------------------------------------------------

#: What each `Step.state` means, so the log can say it rather than print a token.
STATE_HELP: Dict[str, str] = {
    "applied": "a rule applied",
    "supposed": "a supposition ended",
    "widened": "the shortlist ran dry, so it looked wider",
    "quiet": "nothing came to mind",
    "quiescent": "nothing left to do",
    "nothing-matched": "rules came to mind, none matched",
    "stopped": "it judged there was nothing more worth doing",
}


def step_lines(m, step) -> List[str]:
    """One tick, as a person reads it: what arrived, what was considered, and
    what it wrote. `wrote` is the delta, which is the only part most readers
    want -- the rest is there so *nothing happened* can say which nothing."""
    head = f"[{step.state}] {STATE_HELP.get(step.state, '')}".rstrip()
    detail = f"  arrivals {step.arrivals}, proposed {step.proposed}, matched {step.matched}"
    out = [head, detail]
    for e in step.wrote:
        out.append(f"  {e.sign}{m.g.show(e.proposition)}")
    return out
