"""`fs.py`'s token-composition swarm, pinned directly -- one `Said` line
turned into `Token`/`Marker`/`Number`/`AfterThreshold`/`Located`, without
going through the full `ParseRequest`/`Proposal`/`arbitrate_parse` chain
every `test_fs.py` end-to-end test drives instead.

This is `loopingrules`'s `DECISION_PATTERNS.md` chart-parsing note, built
for `propose_stale`: no single rule here reads a whole line and decides
what it means. `tokenize` mints one entity per word; `mark_keyword`/
`mark_number` are oblivious, per-token recognizers; `after_threshold`/
`located` are the compose step, each reading two independently-deposited
facts and, only by finding them adjacent, producing one bigger claim.
`test_fs.py`'s own `test_stale_finds_the_old_file_and_asks_before_
touching_it` and `test_stale_without_a_number_of_days_is_not_a_guess`
already exercise this end to end; these tests isolate WHICH rule is
responsible for each part of that behavior.
"""

from loopingrules.loop import Loop
from loopingrules.world import Said

from harneskills.examples import fs
from harneskills.examples.model import (AfterThreshold, Located, Marker,
                                        Number, ParseRequest, Token)


def _heard(text):
    """A loop that has recognized one line as far as `located` -- `hear`
    and the token-composition swarm, nothing past it. No `propose_*`, no
    `arbitrate_parse`, so the `ParseRequest` and its `Token`s are still
    standing afterward, to inspect directly."""
    loop = Loop()
    for rule in (fs.hear, fs.tokenize, fs.mark_keyword, fs.mark_number,
                 fs.after_threshold, fs.located):
        loop.rule(rule)
    loop.world.spawn(Said("user", text))
    loop.run()
    return loop.world


def _one_request(w):
    request, req = w.each(ParseRequest)[0]
    return request, req


def test_tokenize_mints_one_token_per_word_in_order():
    w = _heard("stale after 7 days")
    request, _req = _one_request(w)
    tokens = sorted((tok.index, tok.word) for _e, tok in w.each(Token)
                    if tok.request == request.id)
    assert tokens == [(0, "stale"), (1, "after"), (2, "7"), (3, "days")]


def test_mark_keyword_and_mark_number_ride_on_the_token_entity():
    w = _heard("stale after 7 days")
    request, _req = _one_request(w)
    by_index = {tok.index: entity for entity, tok in w.each(Token)
                if tok.request == request.id}
    assert w.get(by_index[1], Marker).word == "after"
    assert w.get(by_index[2], Number).value == 7
    assert not w.has(by_index[0], Marker)  # "stale" is not a control word
    assert not w.has(by_index[3], Number)  # "days" is not a digit


def test_mark_keyword_lowercases_so_typed_case_does_not_matter():
    w = _heard("stale AFTER 7 days")
    request, _req = _one_request(w)
    by_index = {tok.index: entity for entity, tok in w.each(Token)
                if tok.request == request.id}
    assert w.get(by_index[1], Marker).word == "after"


def test_after_threshold_composes_marker_and_the_next_number():
    w = _heard("stale after 7 days")
    request, _req = _one_request(w)
    assert w.get(request, AfterThreshold).days == 7


def test_after_threshold_abstains_when_nothing_follows_the_marker():
    # The exact shape test_fs.py's own
    # test_stale_without_a_number_of_days_is_not_a_guess pins end to end
    # -- isolated here to the one rule actually responsible for it.
    w = _heard("stale after a while")
    request, _req = _one_request(w)
    assert w.get(request, AfterThreshold) is None


def test_after_threshold_abstains_when_the_marker_is_the_last_token():
    w = _heard("stale after")
    request, _req = _one_request(w)
    assert w.get(request, AfterThreshold) is None


def test_located_reads_everything_between_in_and_the_next_marker():
    w = _heard("stale in some folder after 7 days")
    request, _req = _one_request(w)
    assert w.get(request, Located).text == "some folder"


def test_located_is_absent_with_no_in_marker():
    w = _heard("stale after 7 days")
    request, _req = _one_request(w)
    assert w.get(request, Located) is None


def test_arbitrate_parse_leaves_no_token_behind(tmp_path):
    """Full domain install -- `Token`/`Marker`/`Number` are intake
    scaffolding, not durable facts: once `arbitrate_parse` resolves (or
    discards) the `ParseRequest` they were minted for, none of them
    should still be standing to leak, tick after tick."""
    loop = Loop()
    fs.install(loop, cwd=lambda: str(tmp_path))
    loop.world.spawn(Said("user", "stale after 7 days"))
    loop.run()
    assert loop.world.each(Token) == []
    assert loop.world.each(ParseRequest) == []
