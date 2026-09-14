"""A SECOND way a `Folder` gets rescanned -- not a person typing `show`,
not `fs.py`'s own hand-written rules, but a `loopingrules.circuits`
spec: plain data, dispatching to real disk I/O only through
`loopingrules.circuits.Call`. This module is `fs.py`'s worked answer to
a question `loopingrules` itself only ever tested against a toy
(`examples/files.py`, in that repo): does `Call` generalize to a real,
independently-authored domain's OWN tools, at runtime -- not just
against a synthetic stand-in.

## Why `ls`, and specifically not `rename`

`fs.py` already draws exactly the line this module needs: `fs_tools.
rename` is called from exactly one place, `do_rename`, gated on
`without=(NeedsApproval, Proposal)` -- an AUTOMATED proposal is always
held for a person to approve; only a person typing the rename
themselves skips the gate. `fs_tools.ls`/`stat` have no such gate,
because reading the real disk and updating `Entry`/`Size`/`Modified`/
`Contents` to match it is not an action a person needs to approve --
it is the same "recompute fresh, never lie" observation `flag_stale`/
`flag_big` already trust implicitly. That existing split is what makes
this module's own trust boundary easy to draw correctly: `TOOLS`,
below, registers `ls` and stops. A `Call`-bearing spec compiled against
it can refresh what the domain believes about the real filesystem; it
can NEVER reach `fs_tools.rename`, because the string `"rename"` is not
a key in this dict -- checked at `compile_circuit` time, by name, not
by convention (see `tests/test_automations.py::
test_a_spec_naming_rename_is_refused_before_touching_a_world`).

This is the actual motivating case `loopingrules.circuits.Call` was
built for: something outside developer control -- a user-authored
policy, an LLM composing one -- should be able to ask this domain to
look again at reality, without ever being handed enough rope to rename
anything itself. `do_rescan_spec`, below, is one such policy, still
written as a Python literal for now (the same honest caveat `examples/
files.py`'s own docstring in `loopingrules` names): nothing here reads
a spec from a config file, from an LLM, or from anywhere but this
module's own source. What this proves is that the MECHANISM composes
correctly with a real, three-tool domain someone else already wrote --
not that the authoring surface exists yet.

## `Call` deposits, `install()` must answer

`loopingrules.circuits.Call` no longer runs `ls` in place -- it spawns
a `ToolRequest`, and `loopingrules.circuits.compile_answerer(TOOLS)` is
the rule that actually calls it, on whichever later tick sees the
request (see that module's own docstring, "`Call`: a request,
deposited, not a tool invoked in place"). `install()`, below, registers
BOTH rules against the same `TOOLS`, for the same reason `examples/
files.py` does in `loopingrules` itself: a `Call`-bearing spec compiled
without its own answerer installed alongside it leaves every request
standing, unanswered, forever -- caught here by `tests/
test_automations.py`, not just assumed.
"""

from __future__ import annotations

from loopingrules import circuits

from . import fs_tools
from .model import RescanWanted

# The one capability a DATA-authored spec may reach through Call, ever:
# real-but-read-only. `fs_tools.rename` is deliberately absent -- see
# the module docstring, "Why `ls`, and specifically not `rename`."
TOOLS = {"ls": fs_tools.ls}

do_rescan_spec = circuits.ActionCircuit(
    require=(RescanWanted,),
    without=(),
    effects=(
        circuits.Call("ls", (circuits.Self(RescanWanted, "folder"),)),
        circuits.Destroy(),
    ),
)
"""Claim a `RescanWanted`, deposit a `ToolRequest("ls", (folder,))` (`Call`
-- the actual `ls` call happens later, on whichever tick `automations.
do_rescan_answers` sees it, not this one), destroy the `RescanWanted` --
the same claim-then-destroy shape `loopingrules.circuits`'s own
`reply_*`/`examples/files.py` restatements already use. `fs_tools.ls`
does the rest, exactly as it would for a person typing `show`: entries
added, sized, dated; entries no longer on disk, destroyed; `Contents`
replaced. Everything downstream of that (`flag_stale`, `propose_rename`,
`do_rename`, the whole approval-gated pipeline) reads what `ls` wrote
the same way it reads what a typed `show` produced -- oblivious to
which one asked, and oblivious to the request/answer hop in between."""


def install(loop) -> None:
    """Register `do_rescan_spec`, compiled against `TOOLS` and nothing
    wider, plus the answerer that is the only place `"ls"` and the
    function `fs_tools.ls` ever actually meet -- see the module
    docstring, "`Call` deposits, `install()` must answer." Meant to be
    installed ALONGSIDE `fs.install` (this module reads `RescanWanted`/
    writes through `fs_tools.ls` the same as `fs.py` itself does, and
    shares its `Folder`/`Entry`/`Contents` vocabulary), never in place
    of it -- `fs.py` still owns every rule that can propose or perform
    a rename."""
    loop.rule(circuits.compile_circuit(do_rescan_spec, tools=TOOLS),
              name="automations.do_rescan")
    loop.rule(circuits.compile_answerer(TOOLS), name="automations.do_rescan_answers")
