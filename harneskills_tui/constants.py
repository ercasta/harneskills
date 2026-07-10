from __future__ import annotations

from pathlib import Path
from typing import Any

PROFILES_PATH = Path.home() / ".harneskills" / "profiles.toml"

DEFAULT_CONFIG: dict[str, Any] = {
    "goal": "",               # raw text, parsed into goal_slots on /run
    "goal_slots": {},         # parsed GoalCondition dict
    "kb_path": "",            # path to KB module or .cnl file
    "dm_seed": {},            # initial DM slot → value (session scope)
    "entity_scopes": {},      # label → {slot: value} for entity-scoped seeds
    "suppose_sentences": [],  # Form 14 suppose sentences applied before /run
    "max_steps": 20,
}

SLASH_COMMANDS: dict[str, str] = {
    "/help":    "Show available commands",
    "/run":     "Start a session — /run [goal text]",
    "/do":      "Run a procedure declared in a .cnl KB — /do <procedure-name>",
    "/stop":    "Stop the running session",
    "/goal":    "Set goal condition — /goal slot=value [slot2=value2 ...]",
    "/seed":    "Seed initial DM slot — /seed slot=value  or  /seed @label slot=value",
    "/unseed":  "Remove a seeded slot — /unseed slot  or  /unseed @label slot",
    "/entity":  "Add entity scope — /entity <label>  (then /seed @label slot=value)",
    "/suppose": "Queue a Form 14 entity — /suppose ?var is_a TYPE [with slot val ...]",
    "/kb":      "Set KB path — /kb path/to/kb.py  or  /kb path/to/corpus.cnl",
    "/steps":   "Set max loop steps — /steps <n>",
    "/step":    "Toggle step mode — pause after each loop step until Enter",
    "/dm":      "Dump current domain model state",
    "/explain": "Explain why the last step was chosen",
    "/config":  "Show current configuration",
    "/verbose": "Set verbosity 0-2 — /verbose [0|1|2]",
    "/save":    "Save config as profile — /save <name>",
    "/profile": "Load a saved profile — /profile <name>",
    "/profiles":"List all saved profiles",
    "/delete":  "Delete a saved profile — /delete <name>",
    "/logs":    "List recent session logs",
    "/log":     "View a session log — /log [n]",
    "/clear":   "Clear the output log",
    "/quit":    "Quit the application",
}

_HELP_TEXT = """\
[bold]Available commands:[/bold]  (Tab = autocomplete, Up/Down = history, Ctrl+T = multiline)
  [cyan]/run [goal][/cyan]              Start a session (uses current goal; CNL uses KB-declared goal)
  [cyan]/do <procedure>[/cyan]          Run a procedure declared in a .cnl KB (ops + procedures mix)
  [cyan]/stop[/cyan]                    Stop the running session
  [cyan]/goal slot=value ...[/cyan]     Set goal condition  (e.g. all_customers_served=True)
  [cyan]/seed slot=value[/cyan]         Seed a session-level domain-model slot
  [cyan]/seed @label slot=value[/cyan]  Seed a slot in an entity scope (create with /entity first)
  [cyan]/unseed slot[/cyan]             Remove a session-level seed
  [cyan]/unseed @label slot[/cyan]      Remove a slot from an entity scope seed
  [cyan]/entity <label>[/cyan]          Add a named entity scope (e.g. /entity alice)
  [cyan]/suppose ?var is_a TYPE ...[/cyan]  Queue a Form 14 entity (applied at /run time)
  [cyan]/kb <path>[/cyan]               Set KB — .py module (build_kb) or .cnl corpus file
  [cyan]/steps <n>[/cyan]               Set maximum loop steps (default 20)
  [cyan]/step[/cyan]                    Toggle step mode (pause after each step — Enter to advance)
  [cyan]/dm[/cyan]                      Dump current domain model (session + all entity scopes)
  [cyan]/explain[/cyan]                 Explain why the last step was selected
  [cyan]/config[/cyan]                  Show current configuration
  [cyan]/verbose [0-2][/cyan]           Verbosity: 0=steps only  1=+slots  2=+residuals+evidence
  [cyan]/save <name>[/cyan]             Save current config as a profile
  [cyan]/profile <name>[/cyan]          Load a saved profile
  [cyan]/profiles[/cyan]                List all saved profiles
  [cyan]/delete <name>[/cyan]           Delete a saved profile
  [cyan]/logs[/cyan]                    List recent session logs
  [cyan]/log [n][/cyan]                 View a session log
  [cyan]/clear[/cyan]                   Clear the output log
  [cyan]/quit[/cyan]                    Quit

[bold]Slot explorer:[/bold]
  [cyan]?<prefix>[/cyan]                Autocomplete DM/KB slot names — Tab to complete, Enter to inspect"""
