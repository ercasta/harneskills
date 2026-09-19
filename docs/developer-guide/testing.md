# Testing

```bash
.venv\Scripts\python -m pytest          # Windows
.venv/bin/python -m pytest              # Linux / macOS
```

`pyproject.toml` sets `testpaths = ["tests"]` and `pythonpath = ["../loopingrules"]`, so the sibling checkout is found without installing it.

| File | Covers |
|---|---|
| `test_fs.py`, `test_fs_intake.py`, `test_fs_chart.py` | the file-system domain and its propose/arbitrate intake |
| `test_automations.py` | `Call`-based rescans and the trust boundary |
| `test_context.py` | cross-domain "the X one" arbitration |
| `test_help.py` | help topics |
| `test_repl.py` | terminal channel and autocorrect |
| `test_serve.py`, `test_ws.py`, `test_client.py` | WebSocket door, codec, client |
| `test_config.py`, `test_main.py` | config file, argv parsing, wiring |

## Testing a domain

Build a `Loop`, install your domain, spawn a `Said`, run, and read the world:

```python
from loopingrules.loop import Loop
from loopingrules.world import Reply, Said
import mykitchen

def test_boil():
    loop = Loop()
    loop.install(mykitchen.install)
    loop.world.spawn(Said("user", "boil the kettle"))
    loop.run()
    assert [r.text for _, r in loop.world.each(Reply)] == ["the kettle is boiling"]
```

Assert on the settled world, not on call order. Because rules communicate only through components, the world after `run()` is the whole observable outcome.
