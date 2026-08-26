"""A terminal client for a served world.

    python -m harneskills.client            # finds the running server
    python -m harneskills.client ws://127.0.0.1:8765 --token abc123

Type a line, it goes out as `{"say": "..."}`; replies come back and are
printed. That is the whole of it -- this is `harneskills.repl`'s printing
half with a socket where the loop used to be, and it holds no world of
its own.

Two threads, because a line you are half way through typing must not
stop a reply arriving: one reads the socket and prints, one reads your
keyboard and sends. Nothing is shared between them but the socket, and
only one of them writes to it.

    /world   ask for the whole world and print it, entity by entity
    /quit    leave (so does EOF)

Where the server is, when you do not say: `server.json`, which a serving
`python -m harneskills --serve` writes beside the world it is keeping --
the port it actually bound and the token it wants. Which is also the
answer to "how does a client on this machine authenticate": by being
able to read a file only you can read.
"""

from __future__ import annotations

import json
import socket
import sys
import threading

from . import config as cfg
from . import ws


def _server_details(path: str) -> "dict":
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _render(message: dict) -> None:
    """One message from the server, as a line for a person. Anything not
    recognised is printed raw rather than swallowed -- a client that
    silently drops what it does not know is a client you cannot debug a
    new server message with."""
    if "reply" in message:
        reply = message["reply"]
        text, channel = reply.get("text", ""), reply.get("channel")
        print(text if channel == "user" else "[%s] %s" % (channel, text))
    elif "unheard" in message:
        print("  (nothing understood: %s)" % message["unheard"].get("text", ""))
    elif "error" in message:
        print("  ! %s" % message["error"].get("text", ""))
    elif "welcome" in message:
        print("  connected as %s" % message["welcome"].get("channel"))
    elif "world" in message:
        world = message["world"]
        for record in world.get("entities", ()):
            print("  #%-4s %s" % (record["id"], "  ".join(
                "%s(%s)" % (c["type"].rpartition(":")[2],
                            ", ".join("%s=%r" % kv for kv in c["fields"].items()))
                for c in record["components"])))
    elif "settled" in message:
        pass          # state moved; a richer client would redraw here
    else:
        print("  ? %s" % json.dumps(message))


# How long to wait, on the way out, for the reply to the LAST thing typed
# before quitting -- see `run`'s own note on why this exists at all.
_QUIT_GRACE = 2.0


def _listen(sock, stop, settled) -> None:
    reader = ws.Reader(sock, is_server=False)
    while not stop.is_set():
        try:
            message = reader.message()
        except (ws.ProtocolError, OSError, ConnectionError):
            break
        if message is None:
            break
        opcode, payload = message
        if opcode != ws.TEXT:
            continue
        try:
            parsed = json.loads(payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            print("  ! the server said something that was not JSON")
            continue
        _render(parsed)
        if "settled" in parsed:
            # The engine has finished saying everything THIS settle had to
            # say -- see `run`'s own docstring, "the reply to the last
            # thing typed".
            settled.set()
    stop.set()
    print("  -- the server is gone --")


def run(host: str, port: int, token=None, stdin=None,
        echo_prompt: bool = True) -> int:
    """Connect, relay lines out and messages in, until `/quit`, EOF, or the
    server hangs up.

    ## The reply to the last thing typed

    A reply is asynchronous -- it comes back on `_listen`'s own thread,
    some milliseconds after `say` sends the question, however long the
    engine's settle takes. An interactive person never notices: typing
    the next line, including `/quit`, takes them far longer than that.
    Piped input (`printf 'stale after 7 days\\n/quit\\n' | python -m
    harneskills.client`) has no such delay -- both lines are read and
    sent back to back, and closing the socket the instant `/quit` is seen
    would tear the connection down before the answer to the FIRST line
    had time to arrive.

    `settled` is cleared before every `say`/`get` and set by `_listen`
    when a `{"settled": ...}` message comes back -- the engine's own
    signal that it has finished saying everything this settle had to say
    (`harneskills.engine`'s own note). Quitting waits for it, up to
    `_QUIT_GRACE`, rather than assuming a person just typed it and has all
    the time in the world.
    """
    stdin = stdin or sys.stdin
    sock = socket.create_connection((host, port))
    ws.connect(sock, host, port)
    stop = threading.Event()
    settled = threading.Event()
    threading.Thread(target=_listen, args=(sock, stop, settled),
                     daemon=True).start()

    def say(message: dict) -> None:
        settled.clear()
        ws.send(sock, json.dumps(message), mask=True)

    if token:
        say({"hello": token})
    try:
        while not stop.is_set():
            if echo_prompt:
                sys.stdout.write("harneskills> ")
                sys.stdout.flush()
            line = stdin.readline()
            if line == "":
                break
            line = line.strip()
            if not line:
                continue
            if line in ("/q", "/quit", "/exit"):
                break
            if line == "/world":
                say({"get": "world"})
                continue
            say({"say": line})
    except (KeyboardInterrupt, OSError):
        pass
    finally:
        settled.wait(_QUIT_GRACE)
        stop.set()
        try:
            sock.sendall(ws.close_frame(mask=True))
        except OSError:
            pass
        sock.close()
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    where, token, rest = None, None, []
    while argv:
        arg = argv.pop(0)
        flag, _, inline = arg.partition("=")
        if flag == "--token":
            token = inline or (argv.pop(0) if argv else None)
        elif flag == "--server":
            where = inline or (argv.pop(0) if argv else None)
        else:
            rest.append(arg)
    if rest:
        address = rest[0].replace("ws://", "").replace("http://", "")
        host, _, port = address.partition(":")
        host, port = host or "127.0.0.1", int(port or 8765)
    else:
        try:
            details = _server_details(where or cfg.server_path())
        except (OSError, ValueError) as e:
            print("! no server to connect to: %s" % e, file=sys.stderr)
            print("! start one with `python -m harneskills --serve ...`,"
                  " or name it: `python -m harneskills.client ws://host:port`",
                  file=sys.stderr)
            return 2
        host, port = details.get("host", "127.0.0.1"), int(details["port"])
        token = token or details.get("token")
    try:
        return run(host, port, token)
    except (OSError, ws.ProtocolError) as e:
        print("! could not talk to %s:%s: %s" % (host, port, e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
