"""What a `Listener` promises: a real WebSocket door onto a running
engine, gated by a token, that behaves like any other channel once a
connection is through it -- proven over real loopback sockets, not
mocks, the same discipline `test_ws.py` holds the codec to."""

import json
import socket
import threading
import time

import pytest

from ugm.engine import Engine
from ugm.loop import Loop
from ugm.world import Reply, Said

from harneskills import ws
from harneskills.serve import Listener


@pytest.fixture
def echoing_loop():
    """A loop that replies `echo: TEXT` to anything said, to any channel
    that said it -- and answers "y"/"n" as this domain would never
    understand, exercising the ordinary unheard path too."""
    loop = Loop()

    @loop.system
    def echo(w):
        for entity, said in w.each(Said):
            if said.text == "silence":
                continue   # left standing: the drain reports it unheard
            w.destroy(entity)
            w.spawn(Reply("user", "echo: %s" % said.text))
    return loop


def serving(loop, token=None):
    """A running `Engine` with one `Listener` attached, on its own thread.
    Returns `(engine, thread, (host, port))`."""
    engine = Engine(loop)
    bound = {}
    listener = Listener(host="127.0.0.1", port=0, token=token,
                        announce=lambda h, p, t: bound.setdefault("addr", (h, p)))
    engine.attach(listener)
    thread = threading.Thread(target=engine.run, daemon=True)
    thread.start()
    for _ in range(50):
        if "addr" in bound:
            break
        time.sleep(0.02)
    assert "addr" in bound, "the listener never bound"
    return engine, thread, bound["addr"]


class Client:
    """The client half of the wire protocol, over a real socket, kept
    minimal -- this is a test fixture, not `harneskills.client`."""

    def __init__(self, addr, timeout=3):
        self.sock = socket.create_connection(addr, timeout=timeout)
        ws.connect(self.sock, *addr)
        self.reader = ws.Reader(self.sock, is_server=False)

    def send(self, message):
        ws.send(self.sock, json.dumps(message), mask=True)

    def recv(self):
        opcode, payload = self.reader.message()
        assert opcode == ws.TEXT
        return json.loads(payload.decode("utf-8"))

    def close(self):
        self.sock.close()


def stop(engine, thread):
    engine.stop()
    thread.join(2)
    assert not thread.is_alive()


# --- connecting -----------------------------------------------------------

def test_a_connection_is_welcomed_and_named(echoing_loop):
    engine, thread, addr = serving(echoing_loop)
    client = Client(addr)
    welcome = client.recv()
    assert "welcome" in welcome and welcome["welcome"]["channel"]
    client.close()
    stop(engine, thread)


def test_without_a_token_nothing_is_gated(echoing_loop):
    engine, thread, addr = serving(echoing_loop, token=None)
    client = Client(addr)
    client.recv()   # welcome
    client.send({"say": "hi"})
    assert client.recv()["reply"]["text"] == "echo: hi"
    client.close()
    stop(engine, thread)


def test_the_right_token_is_accepted(echoing_loop):
    engine, thread, addr = serving(echoing_loop, token="secret")
    client = Client(addr)
    client.recv()
    client.send({"hello": "secret"})
    client.send({"say": "hi"})
    assert client.recv()["reply"]["text"] == "echo: hi"
    client.close()
    stop(engine, thread)


def test_the_wrong_token_is_refused_and_the_connection_ends(echoing_loop):
    engine, thread, addr = serving(echoing_loop, token="secret")
    client = Client(addr)
    client.recv()
    client.send({"hello": "nope"})
    assert client.recv()["error"]["text"] == "wrong token"
    assert client.reader.message() is None, "the connection should be over"
    client.close()
    stop(engine, thread)


def test_before_a_token_is_given_nothing_else_is_even_looked_at(echoing_loop):
    # A `say` typed before `hello` is not a jump-the-queue shortcut -- it
    # is read as a failed attempt at the one thing this connection may
    # say first, same as a wrong token would be.
    engine, thread, addr = serving(echoing_loop, token="secret")
    client = Client(addr)
    client.recv()
    client.send({"say": "hi"})
    assert client.recv() == {"error": {"text": "wrong token"}}
    assert client.reader.message() is None, "the connection should be over"
    client.close()
    stop(engine, thread)


# --- talking to the shared world ----------------------------------------

def test_say_gets_a_reply_and_get_gets_the_world(echoing_loop):
    engine, thread, addr = serving(echoing_loop)
    client = Client(addr)
    client.recv()
    client.send({"get": "world"})
    world = client.recv()
    assert "world" in world and world["world"]["entities"] == []
    client.close()
    stop(engine, thread)


def test_a_line_nobody_understands_is_reported_unheard(echoing_loop):
    engine, thread, addr = serving(echoing_loop)
    client = Client(addr)
    client.recv()
    client.send({"say": "silence"})
    assert client.recv()["unheard"]["text"] == "silence"
    client.close()
    stop(engine, thread)


def test_two_connections_share_one_broadcast(echoing_loop):
    engine, thread, addr = serving(echoing_loop)
    a, b = Client(addr), Client(addr)
    a.recv(); b.recv()
    a.send({"say": "hi"})
    assert a.recv()["reply"]["text"] == "echo: hi"
    assert b.recv()["reply"]["text"] == "echo: hi"
    a.close(); b.close()
    stop(engine, thread)


def test_a_connection_that_drops_does_not_take_the_engine_with_it(echoing_loop):
    engine, thread, addr = serving(echoing_loop)
    gone = Client(addr)
    gone.recv()
    gone.close()
    time.sleep(0.2)
    still_here = Client(addr)
    still_here.recv()
    still_here.send({"say": "hi"})
    assert still_here.recv()["reply"]["text"] == "echo: hi"
    still_here.close()
    stop(engine, thread)


def test_a_message_that_is_not_json_is_named_not_silently_dropped(echoing_loop):
    engine, thread, addr = serving(echoing_loop)
    client = Client(addr)
    client.recv()
    ws.send(client.sock, "not json at all", mask=True)
    assert "JSON" in client.recv()["error"]["text"]
    client.close()
    stop(engine, thread)


def test_a_json_array_is_refused_a_message_is_an_object(echoing_loop):
    engine, thread, addr = serving(echoing_loop)
    client = Client(addr)
    client.recv()
    client.send([1, 2, 3])
    assert "object" in client.recv()["error"]["text"]
    client.close()
    stop(engine, thread)
