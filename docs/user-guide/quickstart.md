# Quick start

HarneSkills ships **no** domain of its own; you name the one you want. `harneskills.examples.fs` lists, ages and renames real files:

```bash
python -m harneskills --no-config harneskills.examples.fs:install
```

```text
installed: harneskills.examples.fs:install
harneskills> show file
archive/
draft.txt (6 bytes)
old.md (4 bytes)
5 item(s) in /tmp/notes
harneskills> show big
scan.pdf (4300 bytes)
```

## Things worth trying

**Typos are corrected, and say so.** A word close to exactly one known word is fixed and echoed:

```text
harneskills> shwo file in /tmp/notes/archive
  ~ shwo -> show
```

**Focus.** `show big` answers about the folder you last *looked* at.

**Automations propose, you approve.** An automated rename is held for a yes/no:

```text
harneskills> stale after 7 days
2 of 5 older than 7 day(s) in /tmp/notes
approve rename draft.txt -> stale-draft.txt in /tmp/notes? [y/N] y
renamed draft.txt -> stale-draft.txt
```

Typing the rename yourself (`rename huge.bin to enormous.bin`) asks nothing.

**Memory.** The world is saved every time it settles. Restart without `--no-state` and it remembers the folder, the entries and what you were looking at.

Leave with `/quit` (or EOF). See [At the prompt](prompt.md) for the rest.
