# Standing domains & persistence

## Config file

Typing the same specs every session gets old. List them, one `module:callable` per line:

```text
# ~/.config/harneskills/config
harneskills.examples.fs:install
mykitchen:install
```

Blank lines and `#` comments are ignored; a duplicate spec installs once.

| Platform | Config | State |
|---|---|---|
| Linux/macOS | `$XDG_CONFIG_HOME` or `~/.config/harneskills/config` | `$XDG_STATE_HOME` or `~/.local/state/harneskills/world.json` |
| Windows | `%APPDATA%\harneskills\config` (roaming) | `%LOCALAPPDATA%\harneskills\world.json` (local) |

The split on Windows is deliberate: which domains you install should follow you between machines; a world full of absolute disk paths should not.

## World state

The world is written as JSONL every time it settles and restored at start (`restored 7 entities from ...`). Restored data is authoritative for what was *concluded* (`Stale`, `Focus`, ...), while things that belong to *this process* (such as the current directory and clock) are re-set by the domain at install.

Use `--state PATH` to relocate it and `--no-state` for throwaway runs.

!!! note
    Components must hold only `None`, `bool`, `int`, `float`, `str` and lists/dicts/tuples of those, so any world can be saved. See [The world](../developer-guide/world.md).
