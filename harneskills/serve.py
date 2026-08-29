"""A WebSocket door onto a running `loopingrules.engine.Engine`.

    listener = Listener(host="127.0.0.1", port=0, token="...")
    engine.attach(listener)

`Listener` is a CHANNEL in `loopingrules.engine`'s sense -- attach it to a
running engine the same way you would a `harneskills.repl.Terminal` -- but
one that spawns a NEW channel (`Connection`) for every socket that
connects, each named by the engine the same way any other channel is
(`Engine.attach`'s own counter -- `ch2`, `ch3`, whichever is next,
alongside every terminal already attached). It is a door, not a room:
nothing here is "the" connection, and `deliver` on the `Listener` itself
is never called, because the engine never addresses a message to "every
socket that might ever connect" -- only to channels that exist.

## What goes over the wire

In, from a connected browser or `harneskills.client`::

    {"hello": "<token>"}      first, if the listener was given one
    {"say": "show big"}       a line, exactly as typed
    {"get": "world"}          ask for the whole world once

Out, the same shapes any channel renders, as JSON instead of prose -- see
`loopingrules.engine`'s own docstring for the full list::

    {"welcome": {"channel": "ch2", "needs_token": false}}
    {"reply": {"channel": "user", "text": "scan.pdf (4300 bytes)"}}
    {"settled": {"revision": 412, "entities": 13}}

## The token

Loopback TCP has no filesystem permissions to lend a socket the way a
Unix socket would, so any local process can open the port. The first
message from a fresh connection must therefore be `{"hello": "<token>"}`
if the listener was given one, and `harneskills.__main__` writes that
token -- with the port -- to a file only the account running this process
can read (`harneskills.config.server_path`). That is the whole of the
security story: it keeps another user's process off your world, and it
is not TLS. Do not bind this to an interface anyone else can reach.

## One thread accepts, one reads each connection, none of them touch the
## world

Exactly the discipline `loopingrules.engine` documents for every channel:
a `Connection`'s reading thread only ever calls `engine.post`, and the
engine's own thread is the only one that spawns a `Said`, runs a tick, or
writes a component. `deliver` sends under the connection's own lock,
which is there because the engine's thread and this connection's reading
thread (answering a WebSocket `ping`) can both want the same socket at
once.
"""

from __future__ import annotations

import json
import socket
import threading

from . import ws

VERSION = 1


class Connection:
    """One WebSocket client, as a channel. Spawned by `Listener`, never
    constructed directly."""

    def __init__(self, sock) -> None:
        self.sock = sock
        self.name = None          # set by `Engine.attach`
        self.greeted = False      # has an acceptable `hello` arrived yet
        self._send_lock = threading.Lock()
        self._stop = threading.Event()
        self.engine = None
        self.token = None

    # -- the channel contract (see loopingrules.engine) -----------------

    def start(self, engine) -> None:
        self.engine = engine
        self._send({"welcome": {"channel": self.name, "needs_token": bool(self.token)}})
        threading.Thread(target=self._read_loop, daemon=True).start()

    def deliver(self, message: dict) -> None:
        if not self._send(message):
            self.close()

    def close(self) -> None:
        self._stop.set()
        try:
            with self._send_lock:
                self.sock.sendall(ws.close_frame())
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass

    # -- the socket -------------------------------------------------------

    def _send(self, message: dict) -> bool:
        try:
            with self._send_lock:
                ws.send(self.sock, json.dumps(message))
            return True
        except (OSError, ValueError):
            return False

    def _read_loop(self) -> None:
        reader = ws.Reader(self.sock, is_server=True)
        try:
            while not self._stop.is_set():
                try:
                    message = reader.message()
                except ws.ProtocolError as e:
                    self._send({"error": {"text": "protocol: %s" % e}})
                    break
                if message is None:
                    break
                opcode, payload = message
                if opcode != ws.TEXT:
                    continue
                if not self._heard(payload):
                    break
        except (OSError, ConnectionError):
            pass
        finally:
            if self.engine is not None:
                self.engine.detach(self)

    def _heard(self, payload: bytes) -> bool:
        """One text frame. False if this connection should end."""
        try:
            message = json.loads(payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._send({"error": {"text": "that was not JSON"}})
            return True
        if not isinstance(message, dict):
            self._send({"error": {"text": "a message is a JSON object"}})
            return True
        if self.token is not None and not self.greeted:
            # Nothing but `hello` is even looked at until the token is
            # right -- and a wrong one ends the connection outright rather
            # than inviting a second guess.
            if message.get("hello") != self.token:
                self._send({"error": {"text": "wrong token"}})
                return False
            self.greeted = True
            return True
        if "say" in message:
            self.engine.post(self, "say", str(message["say"]))
        elif message.get("get") == "world":
            self.engine.post(self, "get", None)
        elif "hello" in message:
            self.greeted = True
        else:
            self._send({"error": {"text": "expected say, get or hello"}})
        return True


class Listener:
    """A channel that is really a door: attaching it starts an accept loop,
    and every socket that connects becomes its own `Connection`, attached
    to the same engine in its own right.

    Not itself ever the target of `deliver` -- the engine only ever
    addresses a channel that exists, and a `Listener` is not one; see this
    module's docstring.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8765,
                token=None, announce=None) -> None:
        self.host = host
        self.port = port
        self.token = token
        self.announce = announce
        self.name = None
        self._listener = None
        self._stop = threading.Event()

    def start(self, engine) -> None:
        self.engine = engine
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.listen(8)
        self._listener = sock
        self.port = sock.getsockname()[1]
        if self.announce is not None:
            self.announce(self.host, self.port, self.token)
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def deliver(self, message: dict) -> None:
        pass   # see the class docstring: nothing addresses a Listener

    def close(self) -> None:
        self._stop.set()
        if self._listener is not None:
            try:
                self._listener.close()
            except OSError:
                pass

    def _accept_loop(self) -> None:
        while not self._stop.is_set():
            try:
                sock, _ = self._listener.accept()
            except OSError:
                return          # closed: the engine is stopping
            threading.Thread(target=self._greet, args=(sock,),
                             daemon=True).start()

    def _greet(self, sock) -> None:
        """The handshake, off the accept thread so one slow or hostile
        client cannot hold up the next connection. The `Connection` itself
        is attached only once the handshake succeeds."""
        try:
            ws.handshake(sock)
        except (ws.ProtocolError, OSError):
            try:
                sock.close()
            except OSError:
                pass
            return
        connection = Connection(sock)
        connection.token = self.token
        self.engine.attach(connection)
