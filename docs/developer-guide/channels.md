# Channels & the wire protocol

## The channel contract

A channel is any object with four things (no base class):

```text
channel.name              unique str; the engine assigns one if unset (ch2, ch3, ...)
channel.start(engine)     called on attach; start your threads here
channel.deliver(message)  a dict, called from the engine's thread; must not block long
channel.close()           called on detach or shutdown
```

`harneskills.repl.Terminal` and `harneskills.serve.Listener` (which spawns one `Connection` per socket) implement it.

**One thread touches the world.** A channel's own thread only calls `engine.post(channel, kind, text)`; the engine thread alone spawns `Said`, runs ticks and writes components. That is why there is no lock around the world.

Inbound kinds for `post`: `say` (a line), `command` (a slash command, run on the engine thread), `get` (the world), `stop` (end the session, queued in order).

`/reload` works because a command handler may return a fresh `Loop`; every channel stays attached and only the world underneath changes.

## Outbound messages

```text
{"reply":   {"channel": "user", "text": "scan.pdf (4300 bytes)"}}
{"unheard": {"text": "what is for dinner"}}
{"error":   {"text": "fs.flag_big: KeyError: ..."}}
{"lines":   ["#1  Session(...)", ...]}
{"settled": {"revision": 412, "entities": 13}}
{"world":   [{"version": 2, ...}, ...]}
{"welcome": {"channel": "ch2", "needs_token": false}}
```

## WebSocket protocol

Client to server:

```text
{"hello": "<token>"}     first message, if the listener has a token
{"say": "show big"}      a typed line
{"get": "world"}         request the whole world once
```

Server to client: the messages above as JSON text frames. See `harneskills/ws.py` for the codec and `harneskills/serve.py` for the listener; `harneskills/client.py` is a complete reference client (two threads: one reads the socket, one reads the keyboard).

Reading `server.json` (from `harneskills.config.server_path()`) yields the bound host, port and token.

## Writing your own channel

Implement the four members and attach it: `engine.attach(my_channel)`. Anything that can turn `deliver` dicts into output and call `engine.post` for input (a chat bridge, a test harness) is a channel.
