# Command line

```text
python -m harneskills [--config PATH | --no-config]
                      [--state PATH  | --no-state]
                      [--serve[=HOST:PORT]] [--token TOKEN] [--headless]
                      [module:callable ...]
```

Positional arguments are **domain specs**: `module:callable`, where the callable takes a `Loop` (`install(loop)`).

| Option | Meaning |
|---|---|
| `--config PATH` | Read standing domains from this file instead of the default. |
| `--no-config` | Ignore the config file, for when the standing domain is what you are debugging. |
| `--state PATH` | Keep the world in this file. |
| `--no-state` | Neither restore nor write; every run starts from nothing. |
| `--serve[=HOST:PORT]` | Also open a WebSocket door (default `127.0.0.1:8765`). The address may only be given with `=`. |
| `--token TOKEN` | Require this token from clients; otherwise one is generated. |
| `--headless` | No terminal; the process *is* the server. Requires `--serve`. |

Contradictory pairs (`--config` with `--no-config`, `--state` with `--no-state`) are rejected. A spec that fails to import, resolve, is not callable, or raises prints `! ...` on stderr and does not kill the session.

Domains install in this order: standing domains from the config file first, then those named on the command line, so a domain named now sees a world the standing ones already set up.

## Client

```text
python -m harneskills.client [ws://HOST:PORT] [--token TOKEN] [--server PATH]
```

With no address it reads `server.json` (see [Serving](serving.md)). Inside the client, `/world` prints the whole world and `/quit` leaves.
