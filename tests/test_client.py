"""What the client promises: it is a plain WebSocket+JSON speaker, holds
no world of its own, and finds a running server the same way
`harneskills.__main__ --serve` tells it to."""

import io
import json
import threading
import time

import pytest

from harneskills import client
from harneskills.engine import Engine
from harneskills.loop import Loop
from harneskills.serve import Listener
from harneskills.world import Reply, Said


@pytest.fixture
def served():
    """A running engine, one Listener attached, torn down after."""
    loop = Loop()

    @loop.system
    def echo(w):
        for entity, said in w.each(Said):
            w.destroy(entity)
            w.spawn(Reply("user", "echo: %s" % said.text))

    engine = Engine(loop)
    bound = {}
    listener = Listener(host="127.0.0.1", port=0,
                        announce=lambda h, p, t: bound.setdefault("addr", (h, p)))
    engine.attach(listener)
    thread = threading.Thread(target=engine.run, daemon=True)
    thread.start()
    for _ in range(50):
        if "addr" in bound:
            break
        time.sleep(0.02)
    yield bound["addr"]
    engine.stop()
    thread.join(2)


# --- rendering ----------------------------------------------------------

def test_render_prints_a_bare_reply_and_a_prefixed_one(capsys):
    client._render({"reply": {"channel": "user", "text": "hi"}})
    client._render({"reply": {"channel": "gauge", "text": "97%"}})
    out = capsys.readouterr().out
    assert "hi" in out.splitlines()
    assert "[gauge] 97%" in out


def test_render_shows_what_nobody_understood(capsys):
    client._render({"unheard": {"text": "what is for dinner"}})
    assert "what is for dinner" in capsys.readouterr().out


def test_render_shows_an_unrecognised_message_raw_rather_than_swallow_it(capsys):
    client._render({"something-new": {"value": 1}})
    assert "something-new" in capsys.readouterr().out


# --- an end-to-end session, over a real socket --------------------------

def test_a_client_can_talk_to_a_served_engine(served, monkeypatch):
    out = io.StringIO()
    monkeypatch.setattr(client.sys, "stdout", out)
    host, port = served
    code = client.run(host, port, stdin=io.StringIO("hi\n/quit\n"),
                      echo_prompt=False)
    assert code == 0
    assert "echo: hi" in out.getvalue()


def test_the_wrong_token_is_reported_not_silently_ignored(monkeypatch):
    from harneskills.engine import Engine as _Engine
    from harneskills.loop import Loop as _Loop
    from harneskills.serve import Listener as _Listener
    engine = _Engine(_Loop())
    bound = {}
    listener = _Listener(host="127.0.0.1", port=0, token="secret",
                         announce=lambda h, p, t: bound.setdefault("addr", (h, p)))
    engine.attach(listener)
    thread = threading.Thread(target=engine.run, daemon=True)
    thread.start()
    for _ in range(50):
        if "addr" in bound:
            break
        time.sleep(0.02)
    out = io.StringIO()
    monkeypatch.setattr(client.sys, "stdout", out)
    client.run(*bound["addr"], token="wrong",
              stdin=io.StringIO(""), echo_prompt=False)
    assert "wrong token" in out.getvalue()
    engine.stop()
    thread.join(2)


# --- finding a server -----------------------------------------------------

def test_main_reads_server_json_when_nothing_is_named(tmp_path, monkeypatch, served):
    host, port = served
    details = tmp_path / "server.json"
    details.write_text(json.dumps({"host": host, "port": port, "token": None}),
                       encoding="utf-8")
    monkeypatch.setenv("HARNESKILLS_SERVER", str(details))
    monkeypatch.setattr(client.sys, "stdin", io.StringIO("hi\n/quit\n"))
    out = io.StringIO()
    monkeypatch.setattr(client.sys, "stdout", out)
    assert client.main([]) == 0
    assert "echo: hi" in out.getvalue()


def test_main_takes_an_address_named_on_the_command_line(served, monkeypatch):
    host, port = served
    monkeypatch.setattr(client.sys, "stdin", io.StringIO("hi\n/quit\n"))
    out = io.StringIO()
    monkeypatch.setattr(client.sys, "stdout", out)
    assert client.main(["ws://%s:%d" % (host, port)]) == 0
    assert "echo: hi" in out.getvalue()


def test_no_server_found_is_a_message_not_a_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HARNESKILLS_SERVER", str(tmp_path / "nope.json"))
    assert client.main([]) == 2
    assert "no server to connect to" in capsys.readouterr().err


# --- --help --------------------------------------------------------------

@pytest.mark.parametrize("flag", ["--help", "-h", "-?"])
def test_help_prints_usage_and_touches_nothing_else(flag, capsys, monkeypatch):
    # Checked before the network or even server discovery -- `--help`
    # parsed as a server address used to fail with a confusing
    # DNS-lookup-shaped error instead of the usage it actually asked for.
    monkeypatch.delenv("HARNESKILLS_SERVER", raising=False)
    assert client.main([flag]) == 0
    assert "usage:" in capsys.readouterr().out


def test_help_wins_over_other_arguments_on_the_line():
    assert client.main(["ws://nope:1", "--help"]) == 0


def test_an_unknown_flag_is_refused_with_usage_not_read_as_an_address(capsys):
    assert client.main(["--bogus"]) == 2
    err = capsys.readouterr().err
    assert "no such option: --bogus" in err and "usage:" in err
