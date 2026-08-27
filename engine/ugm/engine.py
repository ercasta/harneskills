"""The thing that runs: one world, one thread, and any number of channels.

    engine = Engine(loop)
    engine.attach(repl.Terminal())          # the tmux session
    engine.attach(serve.Listener(...))      # and every WebSocket client
    engine.run()

A CHANNEL is anything that can hand this engine lines and be handed
messages back. A terminal is one. Each WebSocket connection is one. They
are attached to a running engine, several at a time, and none of them own
it -- which is the whole point of this module existing: before it, the
prompt owned the loop and the server owned the loop, so you had to pick
one at startup and the other could never see that world.

## One thread owns the world

Channels are threads -- reading a socket, reading a keyboard. They never
touch the world. They `post()` onto a queue, and the engine's own thread
takes one, spawns a `Said`, settles the loop, and routes what came out.
So there is no lock around the world, no reentrancy, and a tick means the
same thing on every channel.

It also means nothing a system does may BLOCK. A system that stopped to
`input()` an approval would stop the world for every other channel, and
would be reading a keyboard the terminal channel is already reading. That
is why `fs.approve` asks by spawning a `Reply` and waiting for a `yes` --
the suspended state was already a component.

## What a channel is

Four things, and no base class to inherit -- this is the whole contract::

    channel.name              a str, unique; the engine sets it if unset
    channel.start(engine)     called on attach. Start your threads here.
    channel.deliver(message)  a dict, from this engine's thread.
    channel.close()           called on detach or shutdown.

`deliver` is called from the engine's thread and should not block for
long; a socket channel writes and moves on, and drops itself if the write
fails.

## What a message is

The same shapes on the way out to everyone -- a terminal renders them as
prose, a socket serialises them as JSON::

    {"reply":   {"channel": "user", "text": "scan.pdf (4300 bytes)"}}
    {"unheard": {"text": "what is for dinner"}}
    {"error":   {"text": "fs.flag_big: KeyError: ..."}}
    {"lines":   ["#1  Session(...)", ...]}        a command's own output
    {"settled": {"revision": 412, "entities": 13}}
    {"world":   {"version": 1, ...}}              `ugm.save`'s own

...and four on the way in, which is what `post` takes: `say` (a line),
`command` (a slash command, run on this thread so it may read the world),
`get` (the world, for a client that renders state), and `stop` (end the
session). `stop` is a message and not a direct call for the same reason
the other three are: posted through the queue, it lands in order behind
whatever a channel said just before it, rather than racing the engine's
own thread to decide which happens first. A channel MAY still call
`engine.stop()` directly if it truly means "right now, whatever is
queued" -- `Server.serve`'s own shutdown does -- but `post(..., "stop")`
is what an ordinary `/quit` should reach for.

## Channels, and who hears what

`user` is not a channel, it is EVERYONE. A domain that says
`Reply("user", ...)` -- which the shipped `fs` domain does -- is heard by
the terminal and by every connected client at once, because that is what
a shared world means. A reply addressed to a channel's own name
(`term`, `ws2`) goes only there, which is how a domain answers just the
asker: carry the channel off the `Said` you consumed.
"""

from __future__ import annotations

import queue
import threading

from . import save
from .world import Reply, Said

BROADCAST = "user"


class Engine:
    """One loop, one queue, and the channels attached to it."""

    def __init__(self, loop, on_settle=None, commands=None) -> None:
        self.loop = loop
        self.on_settle = on_settle
        # `{"/name": fn(engine, argument)}`. Run on THIS thread, so a
        # command may read the world, and may return a fresh `Loop` to
        # carry on with -- which is how `/reload` can exist without every
        # channel having to be told.
        self.commands = dict(commands or {})
        self.inbox: "queue.Queue" = queue.Queue()
        self.channels: "list" = []
        self._registry = threading.Lock()
        self._named = 0
        self._stop = threading.Event()

    # -- channels ------------------------------------------------------

    def attach(self, channel):
        """Register it, name it if it has not named itself, start it."""
        with self._registry:
            if not getattr(channel, "name", None):
                self._named += 1
                channel.name = "ch%d" % self._named
            if channel.name == BROADCAST:
                raise ValueError("%r is everyone, not a channel" % BROADCAST)
            self.channels.append(channel)
        start = getattr(channel, "start", None)
        if start is not None:
            start(self)
        return channel

    def detach(self, channel) -> None:
        with self._registry:
            if channel in self.channels:
                self.channels.remove(channel)
        close = getattr(channel, "close", None)
        if close is not None:
            close()

    def post(self, channel, kind: str, text=None) -> None:
        """A channel, from its own thread, handing the engine something to
        do. The only way in."""
        self.inbox.put((channel, kind, text))

    # -- routing -------------------------------------------------------

    def to_all(self, message: dict) -> None:
        with self._registry:
            channels = list(self.channels)
        for channel in channels:
            try:
                channel.deliver(message)
            except Exception:  # noqa: BLE001 -- a channel is not the world
                # A channel that cannot be delivered to is gone, and the
                # world is not the place to notice that: drop it and carry
                # on rather than let one dead socket end the session.
                self.detach(channel)

    def to(self, name: str, message: dict) -> None:
        """One channel by name -- or all of them, for `user`."""
        if name == BROADCAST:
            self.to_all(message)
            return
        with self._registry:
            channels = [c for c in self.channels if c.name == name]
        for channel in channels:
            try:
                channel.deliver(message)
            except Exception:  # noqa: BLE001 -- see `to_all`
                self.detach(channel)

    # -- the world -----------------------------------------------------

    def drain(self, unheard: bool = True) -> None:
        """Everything the world has to say, out to whoever it is for.

        Replies first, then whatever blew up, then the lines nobody
        claimed -- and `unheard=False` between ticks, because a line no
        system has claimed YET is not a line nobody understood. Only a
        settled world can say that.
        """
        world = self.loop.world
        for entity, reply in world.each(Reply):
            world.destroy(entity)
            self.to(reply.channel, {"reply": {"channel": reply.channel,
                                              "text": reply.text}})
        for name, error in self.loop.errors:
            self.to_all({"error": {"text": "%s: %s: %s"
                                   % (name, type(error).__name__, error)}})
        self.loop.errors.clear()
        if unheard:
            for entity, heard in world.each(Said):
                world.destroy(entity)
                self.to(heard.channel, {"unheard": {"text": heard.text}})

    def settle(self) -> None:
        """Run to quiescence, say what was said, then write the world down.

        Drained after every tick, not just at the end: a system that stops
        to ask a question must not do it over the top of what the same
        tick already said.
        """
        ticks, hot = self.loop.run(after_tick=lambda: self.drain(unheard=False))
        self.drain()
        if hot:
            self.to_all({"error": {"text": "gave up after %d ticks, still firing: %s"
                                   % (ticks, ", ".join(sorted(set(hot))))}})
        self.to_all({"settled": {"revision": self.loop.world.revision,
                                 "entities": len(self.loop.world)}})
        if self.on_settle is not None:
            self.on_settle(self.loop)

    # -- running -------------------------------------------------------

    def _do(self, channel, kind: str, text) -> None:
        if kind == "say":
            self.loop.world.spawn(Said(channel.name, text))
            self.settle()
        elif kind == "get":
            self.to(channel.name, {"world": save.dump(self.loop.world)})
        elif kind == "command":
            self._command(channel, text)
        elif kind == "stop":
            self.stop()

    def _command(self, channel, line: str) -> None:
        name, _, argument = line.partition(" ")
        if name == "/show":
            world = self.loop.world
            self.to(channel.name, {"lines": [world.show(e)
                                             for e in world.entities()]})
            return
        if name == "/systems":
            self.to(channel.name, {"lines": ["%2d. %s" % (i, n) for i, (n, _)
                                             in enumerate(self.loop.systems, 1)]})
            return
        handler = self.commands.get(name)
        if handler is None:
            self.to(channel.name, {"error": {"text": "no such command: %s" % name}})
            return
        fresh = handler(self, argument.strip())
        if fresh is not None:
            # A whole new loop handed back -- `/reload`. Every attached
            # channel stays attached; only the world under them changes,
            # which is exactly what the split buys.
            self.loop = fresh
            self.settle()

    def run(self) -> int:
        """Take from the queue and act, until stopped. THE thread that
        touches the world."""
        self.settle()      # a domain may have had something to say at install
        try:
            while not self._stop.is_set():
                try:
                    channel, kind, text = self.inbox.get(timeout=0.5)
                except queue.Empty:
                    continue
                self._do(channel, kind, text)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
        return 0

    def stop(self) -> None:
        self._stop.set()
        with self._registry:
            channels = list(self.channels)
            self.channels = []
        for channel in channels:
            close = getattr(channel, "close", None)
            if close is not None:
                try:
                    close()
                except Exception:  # noqa: BLE001 -- we are leaving anyway
                    pass

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()
