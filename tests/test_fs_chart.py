"""`fs.py`'s second parsing layer -- `loopingrules.chart`, proven against
this domain's real `propose_stale`, not a synthetic stand-in. What's
pinned: only a `"stale ..."` line ever gets a `chart.Intake`; `compose_
stale_reading` wraps `AfterThreshold`/`Located` into ONE whole-line
`Interpretation` and marks it active; a stale line genuinely takes more
than one tick to resolve, unlike every other line shape (`arbitrate_
parse`'s own new wrinkle); and the world truly settles afterward -- no
oscillation between `propose_stale` re-attaching `Proposal` and
`arbitrate_parse` detaching it, the bug `StaleProposed` exists to
prevent (see its own docstring in `model.py`).
"""

from loopingrules import chart
from loopingrules.loop import Loop
from loopingrules.world import Reply, Said

from harneskills.examples import fs
from harneskills.examples.model import ParseRequest, PendingStaleHunt, Session, StaleHunt


def _heard(text, tmp_path):
    """A loop that has recognized one line as far as `chart.select` --
    everything up through the second parsing layer, nothing past it.
    No `propose_*`, no `arbitrate_parse` -- the `ParseRequest` is still
    standing afterward, to inspect directly. `Session` is seeded by
    hand (the same way `fs.install` would) because `compose_stale_
    reading` falls back to `fs.here`, which reads it, whenever a line
    has no "in DIR" of its own."""
    loop = Loop()
    loop.world.spawn(Session(str(tmp_path), 0))
    for rule in (fs.hear, fs.mark_stale_intake, fs.tokenize, fs.mark_keyword,
                 fs.mark_number, fs.after_threshold, fs.located,
                 fs.compose_stale_reading, chart.select, chart.settle):
        loop.rule(rule)
    loop.world.spawn(Said("user", text))
    loop.run()
    return loop.world


def _one_request(w):
    request, req = w.each(ParseRequest)[0]
    return request, req


def test_mark_stale_intake_only_tags_a_stale_shaped_line(tmp_path):
    w = _heard("stale after 7 days", tmp_path)
    request, _req = _one_request(w)
    assert w.has(request, chart.Intake)


def test_mark_stale_intake_leaves_every_other_line_shape_alone():
    loop = Loop()
    for rule in (fs.hear, fs.mark_stale_intake):
        loop.rule(rule)
    loop.world.spawn(Said("user", "show file"))
    loop.run()
    request, _req = loop.world.each(ParseRequest)[0]
    assert not loop.world.has(request, chart.Intake)


def test_compose_stale_reading_spans_the_whole_line_and_marks_active(tmp_path):
    w = _heard("stale after 7 days", tmp_path)
    request, _req = _one_request(w)
    entity, interp = [(e, i) for e, i in w.each(chart.Interpretation)
                      if i.utterance == request.id][0]
    span = w.get(entity, chart.Span)
    assert (span.start, span.end) == (0, 3)   # "stale", "after", "7", "days"
    assert w.get(entity, PendingStaleHunt).days == 7


def test_compose_stale_reading_never_spawns_a_real_stalehunt():
    """The bug `PendingStaleHunt` exists to prevent, pinned directly: a
    reading that is only COMPOSED, not yet `chart.select`-judged, must
    never look like a real `StaleHunt` to `fs.flag_stale` -- its own
    `without=Proposal` gate would grab and destroy it immediately,
    skipping arbitration (and the whole two-idle-tick wait) entirely.
    Checked with `chart.select`/`fs.propose_stale` deliberately NOT
    installed, so nothing could turn `PendingStaleHunt` into the real
    thing even after settling."""
    loop = Loop()
    loop.world.spawn(Session(".", 0))
    for rule in (fs.hear, fs.mark_stale_intake, fs.tokenize, fs.mark_keyword,
                 fs.mark_number, fs.after_threshold, fs.located,
                 fs.compose_stale_reading):
        loop.rule(rule)
    loop.world.spawn(Said("user", "stale after 7 days"))
    loop.run()
    assert loop.world.each(StaleHunt) == []
    assert loop.world.each(PendingStaleHunt) != []


def test_compose_stale_reading_never_fires_without_a_threshold(tmp_path):
    w = _heard("stale after a while", tmp_path)
    request, _req = _one_request(w)
    assert [i for _e, i in w.each(chart.Interpretation) if i.utterance == request.id] == []


def test_a_stale_line_needs_more_than_one_tick_unlike_every_other_line_shape(tmp_path):
    """The real cost `DECISION_PATTERNS.md`'s 2026-09-14 entry accepted,
    checked directly rather than just asserted: `arbitrate_parse` no
    longer resolves a `stale ...` line the same tick its candidate is
    composed, the way it still does for everything else."""
    loop = Loop()
    fs.install(loop, cwd=lambda: str(tmp_path))
    loop.world.spawn(Said("user", "show file"))
    loop.tick()
    assert loop.world.each(ParseRequest) == []   # resolved in ONE tick, same as ever

    loop.world.spawn(Said("user", "stale after 7 days"))
    loop.tick()
    requests = loop.world.each(ParseRequest)
    assert requests != []   # NOT resolved in one tick any more
    request, _req = requests[0]
    interpretations = [i for _e, i in loop.world.each(chart.Interpretation)
                       if i.utterance == request.id]
    assert len(interpretations) == 1   # composed already, just not yet judged
    settled = loop.run()
    assert settled.hot == []
    assert loop.world.each(ParseRequest) == []   # resolved eventually


def test_the_world_settles_with_no_oscillation_between_propose_and_arbitrate(tmp_path):
    """The bug `StaleProposed` exists to prevent, pinned directly: once
    `arbitrate_parse` detaches `Proposal` from the winning `Interpretation`
    and `flag_stale` claims and destroys it (`without=Proposal`, its own
    long-standing gate), `propose_stale` must NOT have re-attached
    `Proposal` first, mistaking the detach for "never proposed" -- if it
    had, `flag_stale` would never have seen `without=Proposal` true and
    the report below would never be said at all. Checked by ticking well
    past settling and confirming nothing fires again, not just that
    `loop.run()` returned once."""
    loop = Loop()
    fs.install(loop, cwd=lambda: str(tmp_path))
    loop.world.spawn(Said("user", "stale after 7 days"))
    settled = loop.run()
    assert settled.hot == []
    for _ in range(5):
        fired = loop.tick()
        assert fired == [], "still ticking after settling: %r" % (fired,)
    replies = [r.text for _e, r in loop.world.each(Reply)]
    assert any(text.startswith("0 of 0 older than 7 day(s)") for text in replies)
    # the winning candidate itself is gone too -- `flag_stale` claims and
    # destroys it once `Proposal` is off, the same as it always did
    assert loop.world.each(chart.Interpretation) == []
