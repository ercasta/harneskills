"""The context pilot, end to end: `fs` and `market`, two domains that
have never heard of each other, both answering `"the big one"` --
`harneskills.examples.context`'s shared occasion, arbitrated by a trail
of turns rather than by whichever domain happened to register first.
"""

import os
import time

import pytest

from loopingrules.loop import Loop
from loopingrules.world import Reply, Said

from harneskills.examples import context, fs, market

DAY = 86400


@pytest.fixture
def folder(tmp_path):
    """A folder with one old small file, one fresh big one, and a
    subfolder -- the same shape `tests/test_fs.py`'s own fixture uses."""
    (tmp_path / "alpha.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "huge.bin").write_bytes(b"x" * 5000)
    (tmp_path / "sub").mkdir()
    old = time.time() - 30 * DAY
    os.utime(tmp_path / "alpha.txt", (old, old))
    return str(tmp_path)


def say(loop, line):
    """One typed line, settled, and every reply it produced."""
    w = loop.world
    w.spawn(Said("user", line))
    loop.run()
    return [reply.text for entity, reply in w.each(Reply)
            if w.destroy(entity) or True]


def test_apples_context_picks_the_market_reading(folder):
    """`show apples` establishes the topic; `"the big one"` then means
    the heaviest item on the shelf, not the biggest file."""
    loop = Loop()
    fs.install(loop, clock=lambda: time.time(), cwd=lambda: folder)
    market.install(loop)
    context.install(loop)

    say(loop, "show apples")
    assert say(loop, "the big one") == ["honeycrisp (180 g)"]


def test_files_context_picks_the_files_reading(folder):
    """`show files` establishes the topic; `"the big one"` then means
    the biggest FILE, not an apple."""
    loop = Loop()
    fs.install(loop, clock=lambda: time.time(), cwd=lambda: folder)
    market.install(loop)
    context.install(loop)

    say(loop, "show files")
    assert say(loop, "the big one") == ["huge.bin (5000 bytes)"]


def test_confidence_decays_and_reverts_to_the_registration_order_default(folder):
    """One flowing conversation, three checkpoints:

    1. No topic has ever been noted -- both domains' confidence is
       `0.0`, a genuine tie, and `arbitrate` falls back to plain
       registration order. `market` is installed FIRST here specifically
       to make that default legible: it wins with no context at all.
    2. `show files` notes the files topic on THIS turn; the very next
       "the big one" is one turn later, `context.confidence` is still
       well above zero, and it now beats market's `0.0`.
    3. Several unrelated turns later (more than `context.TOPIC_HORIZON`),
       that same files confidence has decayed back to `0.0` -- a tie
       again, and the conversation reverts to the exact same
       registration-order default as step 1, not to whatever was true a
       moment before.
    """
    loop = Loop()
    market.install(loop)   # installed first: the tie-break default
    fs.install(loop, clock=lambda: time.time(), cwd=lambda: folder)
    context.install(loop)

    assert say(loop, "the big one") == ["honeycrisp (180 g)"]

    say(loop, "show files")
    assert say(loop, "the big one") == ["huge.bin (5000 bytes)"]

    for _ in range(5):
        say(loop, "blah")
    assert say(loop, "the big one") == ["honeycrisp (180 g)"]
