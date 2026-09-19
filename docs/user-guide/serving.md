# Serving over WebSocket

`--serve` adds a second door to the **same** running world:

```bash
python -m harneskills --serve harneskills.examples.fs:install
```

```text
serving on 127.0.0.1:8765 -- details in ~/.local/state/harneskills/server.json
```

From another terminal, cron job or `ssh` session on the same machine:

```bash
python -m harneskills.client
```

Both prompts are channels on one engine. A reply to `user` reaches **every** attached channel, so `show file` at either prompt is printed at both.

## Running as a service

```bash
python -m harneskills --serve --headless mykitchen:install
```

No terminal is attached; clients drive the process.

## Security

- The listener binds **loopback only**. Nothing is encrypted, so do not expose it beyond loopback.
- If a token is set, a connection's first message must be `{"hello": "<token>"}`.
- With no `--token`, one is generated and written with the bound host and port to `server.json` (mode `0600` where supported). `harneskills.client` reads that file, so a client run by the same account connects with no ceremony.

To reach a remote machine, tunnel with `ssh -L` rather than binding a public address.
