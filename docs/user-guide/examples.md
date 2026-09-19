# The example domains

All live in `harneskills/examples/` and are demonstrations, not shipped features.

| Module | What it shows |
|---|---|
| `fs` (with `model`, `fs_tools`) | The worked domain: list, age (`stale after N days`), flag `big`, rename with approval. Rescans the real disk. |
| `automations` | A second way a folder gets rescanned: a `loopingrules.circuits` spec that may call only `ls`, never `rename`. |
| `context` | A trail of turns and confidence ranking, so an ambiguous phrase like "the big one" can be resolved between independently installed domains. |
| `market` | A toy second domain (apples on a shelf) used with `context` to prove cross-domain arbitration. |

Try the cross-domain pair:

```bash
python -m harneskills --no-config harneskills.examples.fs:install \
    harneskills.examples.market:install harneskills.examples.context:install
```

`fs` owns `show`, `stale` and `rename`; `market` understands qualifiers such as `red`, which mean nothing to `fs`.

The fs domain is tunable: the `BigFloor` component (bytes that make an entry "big") is seeded from `HARNESKILLS_FS_BIG_FLOOR` if the restored world does not already have one. See [Tunable knobs](../tunable knobs.md).
