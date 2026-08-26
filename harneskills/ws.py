"""WebSocket, the part of RFC 6455 this needs and no more.

A handshake and a frame codec, both directions -- `harneskills.serve`
speaks the server half, `harneskills.client` the client half, and the
tests speak both at each other. It is here rather than in either because
a codec that only one end can exercise is a codec whose bugs you find in
production.

Hand-rolled rather than depending on `websockets` or `aiohttp` for the
reason this repo has no dependencies at all: the subset is small enough
to read in one sitting, and everything it needs -- `hashlib`, `base64`,
`struct`, `os.urandom` -- is already in the box.

## What a frame is

    byte 0:  FIN(1) RSV(3) opcode(4)
    byte 1:  MASK(1) length(7)      length 126 -> 2 more bytes, 127 -> 8
    then:    a 4-byte masking key, if MASK
    then:    the payload, XORed with that key if MASK

A client MUST mask what it sends and a server MUST NOT -- not a
convention, a requirement, and a server that masks is one a browser
disconnects from without explaining why. Hence `mask` being an argument
here and not a setting.

## What this does NOT do

No TLS (bind loopback and tunnel if you need more), no
`permessage-deflate`, no outgoing fragmentation, no subprotocol
negotiation, and no HTTP served beside the socket. Incoming fragments ARE
reassembled and `ping` IS answered, because those two are not optional in
practice: a browser fragments a large send whenever it feels like it, and
a proxy that pings an unanswering socket eventually closes it.
"""

from __future__ import annotations

import base64
import hashlib
import os
import socket
import struct

# RFC 6455 §1.3. The one magic constant in the protocol: the server proves
# it understood the handshake by hashing the client's key with this.
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

CONTINUE, TEXT, BINARY, CLOSE, PING, PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA
CONTROL = (CLOSE, PING, PONG)

MAX_MESSAGE = 8 << 20   # 8 MiB. A world snapshot is large; a lie is larger.


class ProtocolError(ValueError):
    """The other end is not speaking WebSocket, or not speaking it well."""


def accept_key(key: str) -> str:
    """The `Sec-WebSocket-Accept` for a client's `Sec-WebSocket-Key`."""
    digest = hashlib.sha1((key.strip() + GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


# -- the handshake -------------------------------------------------------

def _read_headers(sock) -> "tuple[str, dict]":
    """The request (or status) line, and the headers, off a fresh socket.

    Read a byte at a time to the blank line. Slow and completely correct:
    the alternative is buffering past the end of the headers and having to
    hand those bytes to the frame reader, which is a seam this does not
    need to have.
    """
    raw = b""
    while not raw.endswith(b"\r\n\r\n"):
        byte = sock.recv(1)
        if not byte:
            raise ProtocolError("connection closed during the handshake")
        raw += byte
        if len(raw) > 16384:
            raise ProtocolError("handshake headers are absurd")
    lines = raw.decode("latin-1").split("\r\n")
    headers = {}
    for line in lines[1:]:
        name, _, value = line.partition(":")
        if name:
            headers[name.strip().lower()] = value.strip()
    return lines[0], headers


def handshake(sock) -> "dict":
    """The server half: read the upgrade, answer 101, return the headers.

    A request that is not an upgrade gets a 400 and a `ProtocolError` --
    which is what someone pointing a browser at `http://host:port/` will
    see, and it is better than a hung socket.
    """
    request, headers = _read_headers(sock)
    key = headers.get("sec-websocket-key")
    upgrade = headers.get("upgrade", "").lower()
    if not key or upgrade != "websocket":
        sock.sendall(b"HTTP/1.1 400 Bad Request\r\n"
                     b"Content-Type: text/plain\r\n"
                     b"Connection: close\r\n\r\n"
                     b"this is a WebSocket endpoint\n")
        raise ProtocolError("not a WebSocket upgrade: %s" % request)
    sock.sendall(b"HTTP/1.1 101 Switching Protocols\r\n"
                 b"Upgrade: websocket\r\n"
                 b"Connection: Upgrade\r\n"
                 b"Sec-WebSocket-Accept: " + accept_key(key).encode("ascii")
                 + b"\r\n\r\n")
    return headers


def connect(sock, host: str, port: int, path: str = "/") -> None:
    """The client half: send the upgrade and check what comes back."""
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    sock.sendall(("GET %s HTTP/1.1\r\n"
                  "Host: %s:%d\r\n"
                  "Upgrade: websocket\r\n"
                  "Connection: Upgrade\r\n"
                  "Sec-WebSocket-Key: %s\r\n"
                  "Sec-WebSocket-Version: 13\r\n\r\n"
                  % (path, host, port, key)).encode("latin-1"))
    status, headers = _read_headers(sock)
    if "101" not in status:
        raise ProtocolError("server said %r" % status)
    if headers.get("sec-websocket-accept") != accept_key(key):
        # Either not a WebSocket server or one that did not understand the
        # key -- and believing it would mean framing bytes at something
        # that is going to answer in a different language.
        raise ProtocolError("the accept key does not match the one we sent")


# -- frames --------------------------------------------------------------

def frame(payload: bytes, opcode: int = TEXT, mask: bool = False) -> bytes:
    """One whole frame. `mask=True` from a client, never from a server."""
    length = len(payload)
    head = bytes([0x80 | opcode])
    flag = 0x80 if mask else 0x00
    if length < 126:
        head += bytes([flag | length])
    elif length < (1 << 16):
        head += bytes([flag | 126]) + struct.pack("!H", length)
    else:
        head += bytes([flag | 127]) + struct.pack("!Q", length)
    if not mask:
        return head + payload
    key = os.urandom(4)
    return head + key + bytes(b ^ key[i % 4] for i, b in enumerate(payload))


def close_frame(code: int = 1000, reason: str = "", mask: bool = False) -> bytes:
    return frame(struct.pack("!H", code) + reason.encode("utf-8"), CLOSE, mask)


class Reader:
    """Messages off a socket: fragments reassembled, pings answered.

    `message()` blocks until there is a whole one and returns
    `(opcode, payload)`, or None when the other end closes -- which is a
    `close` frame or simply a dead socket, and this does not distinguish
    them because nothing above it treats them differently.
    """

    def __init__(self, sock, is_server: bool = True) -> None:
        self.sock = sock
        # Which way the masking rule points for what we RECEIVE: a server
        # reads masked frames, a client reads unmasked ones.
        self.expect_mask = is_server

    def _exact(self, n: int) -> bytes:
        out = b""
        while len(out) < n:
            chunk = self.sock.recv(n - len(out))
            if not chunk:
                raise ConnectionError("closed mid-frame")
            out += chunk
        return out

    def _frame(self) -> "tuple[bool, int, bytes]":
        first, second = self._exact(2)
        final, opcode = bool(first & 0x80), first & 0x0F
        masked, length = bool(second & 0x80), second & 0x7F
        if length == 126:
            length, = struct.unpack("!H", self._exact(2))
        elif length == 127:
            length, = struct.unpack("!Q", self._exact(8))
        if masked != self.expect_mask:
            raise ProtocolError(
                "a %s frame must%s be masked"
                % ("client" if self.expect_mask else "server",
                   "" if self.expect_mask else " not"))
        if length > MAX_MESSAGE:
            raise ProtocolError("frame of %d bytes is over the limit" % length)
        key = self._exact(4) if masked else b""
        payload = self._exact(length)
        if masked:
            payload = bytes(b ^ key[i % 4] for i, b in enumerate(payload))
        if opcode in CONTROL and not final:
            raise ProtocolError("a control frame may not be fragmented")
        return final, opcode, payload

    def message(self):
        parts, kind = b"", None
        while True:
            try:
                final, opcode, payload = self._frame()
            except socket.timeout:
                # NOT a close -- `socket.timeout` has been a subclass of
                # `OSError` since Python 3.10 (it IS `TimeoutError`), so a
                # bare `except OSError` below would swallow "nothing
                # arrived within the deadline" as "the peer is gone",
                # which is a different fact a caller who set a timeout is
                # entitled to tell apart. Only a caller's own socket has a
                # timeout to raise this in the first place -- neither
                # `harneskills.serve` nor `harneskills.client` sets one --
                # so this re-raise is for whoever else reaches for one.
                raise
            except (ConnectionError, OSError):
                return None
            if opcode == CLOSE:
                return None
            if opcode == PING:
                self.sock.sendall(frame(payload, PONG, not self.expect_mask))
                continue
            if opcode == PONG:
                continue
            if opcode == CONTINUE:
                if kind is None:
                    raise ProtocolError("a continuation with nothing to continue")
            else:
                if kind is not None:
                    raise ProtocolError("a new message inside a fragmented one")
                kind = opcode
            parts += payload
            if len(parts) > MAX_MESSAGE:
                raise ProtocolError("message is over the limit")
            if final:
                return kind, parts


def send(sock, text: str, mask: bool = False) -> None:
    sock.sendall(frame(text.encode("utf-8"), TEXT, mask))
