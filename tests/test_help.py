"""`help files`, answered by `fs` alongside `loopingrules.help`'s own
occasion -- the propose/arbitrate/act shape working across two
`install()`s that know nothing about each other or this module's own
order. `help`/`help python` on their own (no `fs` involved) are
`loopingrules`'s own `tests/test_help.py`, since the occasion lives
there now."""

from loopingrules import help as help_
from loopingrules.loop import Loop
from loopingrules.world import Reply, Said

from harneskills.examples import fs


def say(loop, line):
    """One typed line, settled, and every reply it produced."""
    w = loop.world
    w.spawn(Said("user", line))
    loop.run()
    return [reply.text for entity, reply in w.each(Reply)
            if w.destroy(entity) or True]


def test_help_files_is_answered_by_fs_not_the_default(tmp_path):
    # Two `install()`s, in this order, neither aware of the other --
    # `loopingrules.help`'s own high-priority `hear_help` still claims
    # the line before `fs.hear` ever sees it, regardless of which
    # domain installed first.
    loop = Loop()
    help_.install(loop)
    fs.install(loop, clock=lambda: 0, cwd=lambda: str(tmp_path))
    assert say(loop, "help files") == [
        "show file(s) [in DIR], show big [in DIR], "
        "stale [in DIR] after N days, rename OLD to NEW, "
        "big over N bytes"]


def test_fs_installed_first_changes_nothing(tmp_path):
    loop = Loop()
    fs.install(loop, clock=lambda: 0, cwd=lambda: str(tmp_path))
    help_.install(loop)
    assert say(loop, "help files")[0].startswith("show file(s)")


def test_help_files_never_costs_fs_its_own_parse_request(tmp_path):
    # `fs.hear` wraps EVERY `Said` into a `ParseRequest` regardless of
    # content -- if `help_.hear_help` did not run first, "help files"
    # would still resolve (fs's own five `propose_*` recognize nothing
    # here, so `arbitrate_parse` would destroy an empty `ParseRequest`
    # quietly), but it would have cost one. This pins that it does not.
    loop = Loop()
    fs.install(loop, clock=lambda: 0, cwd=lambda: str(tmp_path))
    help_.install(loop)
    w = loop.world
    w.spawn(Said("user", "help files"))
    loop.run()
    assert w.each(fs.ParseRequest) == []


def test_bare_help_lists_files_once_fs_is_installed(tmp_path):
    # `fs` registers its own `propose_help_census_files` alongside
    # `propose_help_files` -- a bare `help` now names "files" because a
    # real domain offered it to the census, not because `loopingrules.help`
    # hard-coded it. `pystrider` is not installed here, so "python" never
    # appears -- this is `loopingrules`'s own `tests/test_help.py` pinning
    # the shape with synthetic responders; this is one real domain.
    loop = Loop()
    fs.install(loop, clock=lambda: 0, cwd=lambda: str(tmp_path))
    help_.install(loop)
    assert say(loop, "help") == ["try: help files"]


def test_bare_help_settling_leaves_nothing_behind(tmp_path):
    loop = Loop()
    fs.install(loop, clock=lambda: 0, cwd=lambda: str(tmp_path))
    help_.install(loop)
    say(loop, "help")
    w = loop.world
    assert w.each(help_.HelpCommandCensus) == []
    assert w.each(help_.HelpTopicName) == []
