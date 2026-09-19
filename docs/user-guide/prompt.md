# At the prompt

Anything you type becomes a `Said` entity and the loop runs until nothing changes. Replies to `user` are printed once, then discarded.

If no rule claims a line, the prompt says so instead of guessing:

```text
(nothing understood: ...)
```

## Slash commands

| Command | Effect |
|---|---|
| `/show` | Every entity in the world and the components it carries. |
| `/rules` | The installed rules, in the order they run each tick. |
| `/reload` | Re-import the domains and restart the world, restoring the state file. Use after editing a rule. |
| `/reset` | Like `/reload`, but starts with an **empty** world. |
| `/help` (`/?`) | List commands. |
| `/quit`, `/q`, `/exit` | End the whole session (all channels). EOF does the same. |

`/show` and `/rules` are handled by the engine, so they work on every channel, including WebSocket clients.

## Autocorrect

A typed word within one edit (short words) or two edits (long words; a swapped pair counts as one) of exactly one registered word is corrected and echoed as `~ shwo -> show`. Ties are left alone. Correction stops at the first word that looks like a path, so paths are never rewritten.

## Give-up message

If rules keep feeding each other, the loop stops after 200 ticks and names them:

```text
  ! gave up after 200 ticks, still firing: kitchen.ping, kitchen.pong
```
