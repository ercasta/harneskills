"""`ugm.request`: propose a request, let any number of oblivious responders
answer, retire it fulfilled or timed out -- with no channel back to the
asker but the facts a responder deposited itself.
"""
from __future__ import annotations

import pytest

# ⚠⚠ ON HOLD, not deleted: `request.py` sits on `ugm.facts`, which does not
# currently import. See `docs/TODO.md` and `ugm/__init__.py`'s own note.
pytest.importorskip("ugm.facts", exc_type=ImportError)
from ugm.facts import Facts
from ugm.request import extend, install, request


def load(timeout: int = 20):
    return Facts(lambda loop, f: install(loop, f, timeout=timeout))


# -- fulfilled: every responder that started, finished --------------------------


def test_a_request_is_fulfilled_once_every_responder_that_started_finishes():
    f = load()
    hub = f.node("hub")
    details = request(f, hub, "analyze", f.word("program"))

    @f.system
    def responder(world):
        if not f.holds("responding", details, f.word("alice")):
            f.fact("responding", details, f.word("alice"))
        else:
            f.fact("completed", details, f.word("alice"))

    f.run()
    assert f.text("outcome", details) == "fulfilled"
    assert f.of("request", hub) == [], "retired off the hub once settled"


def test_two_responders_both_have_to_finish():
    f = load()
    hub = f.node("hub")
    details = request(f, hub, "analyze", f.word("program"))
    for name in ("alice", "bob"):
        f.fact("responding", details, f.word(name))
    f.fact("completed", details, f.word("alice"))

    @f.system
    def slow_bob(world):
        # Finishes on the SECOND tick it is asked, not the first -- so the
        # request must still be open, and only alice done, for one tick.
        if f.holds("responding", details, f.word("bob")) and not f.has(
            "outcome", details
        ):
            if f.holds("done_thinking", details, f.word("bob")):
                f.fact("completed", details, f.word("bob"))
            else:
                f.fact("done_thinking", details, f.word("bob"))

    f.run()
    assert f.text("outcome", details) == "fulfilled"


# -- timed out: nobody (or not everybody) ever finishes --------------------------


def test_a_request_nobody_answers_times_out_rather_than_hanging_forever():
    f = load(timeout=3)
    hub = f.node("hub")
    details = request(f, hub, "analyze", f.word("program"))

    settled = f.run(budget=50)
    assert settled.hot == []
    assert f.text("outcome", details) == "timed_out"
    assert f.of("request", hub) == []


def test_a_responder_that_starts_but_never_finishes_still_times_out():
    f = load(timeout=3)
    hub = f.node("hub")
    details = request(f, hub, "analyze", f.word("program"))
    f.fact("responding", details, f.word("alice"))     # signals, then goes silent

    f.run(budget=50)
    assert f.text("outcome", details) == "timed_out"


# -- extension: a responder buys itself more time --------------------------------


def test_extend_widens_the_deadline_past_the_installed_timeout():
    f = load(timeout=2)
    hub = f.node("hub")
    details = request(f, hub, "analyze", f.word("program"))
    f.fact("responding", details, f.word("alice"))
    extend(f, details, f.word("alice"), 10)

    # Finishes on tick 5 -- inside the extended deadline, past the bare one.
    @f.system
    def slow(world):
        if f.has("outcome", details):
            return
        current = f.one("elapsed", details)
        age = 0 if current is None else f.payload(current)
        if age >= 4:
            f.fact("completed", details, f.word("alice"))

    f.run(budget=50)
    assert f.text("outcome", details) == "fulfilled"


def test_without_the_extension_the_same_slow_responder_times_out():
    f = load(timeout=2)
    hub = f.node("hub")
    details = request(f, hub, "analyze", f.word("program"))
    f.fact("responding", details, f.word("alice"))

    @f.system
    def slow(world):
        if f.has("outcome", details):
            return
        current = f.one("elapsed", details)
        age = 0 if current is None else f.payload(current)
        if age >= 4:
            f.fact("completed", details, f.word("alice"))

    f.run(budget=50)
    assert f.text("outcome", details) == "timed_out"


# -- several requests on one hub, oblivious to each other ------------------------


def test_several_requests_on_one_hub_are_retired_independently():
    f = load(timeout=5)
    hub = f.node("hub")
    quick = request(f, hub, "analyze", f.word("a"))
    slow = request(f, hub, "analyze", f.word("b"))
    f.fact("responding", quick, f.word("alice"))
    f.fact("completed", quick, f.word("alice"))

    f.run(budget=50)
    assert f.text("outcome", quick) == "fulfilled"
    assert f.text("outcome", slow) == "timed_out"
    assert f.of("request", hub) == []
