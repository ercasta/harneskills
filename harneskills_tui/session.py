"""
HarnessRunner — the TUI's glue to the current substrate (goal -> plan -> act -> replan).

This is the ONLY paradigm-coupled file in the TUI: the presentation layer (screen /
widgets / modals / messages) is engine-agnostic and talks to the runner purely through
the event vocabulary in `messages.py` (StepEvent / GoalReached / Impasse / Status / Error).
The old runner drove a deleted typed-KB + HTN planner; this one drives the current
`harneskills.planning` loop (operators = monotone facts; the plan + execution cursor are
control-layer scaffolding rewritten to a fixpoint — see docs/planning_design.md).

Two KB kinds are supported:

  * a Python module (``.py``) that authors a problem instance as graph data. It exports
    ``build()`` (or ``build_kb()``) returning a seeded ``Graph`` (operators + initial
    state; the goal may be seeded here or supplied via ``/goal``). It MAY also export
    ``build_actions(graph) -> {op_name: tool}`` (real §8 action tools), ``FAILURES``
    (``{op_name: withhold_count}`` for demoing divergence/replan), and ``DEFAULT_GOAL``
    (a condition name used when neither the graph nor ``/goal`` names one). This path
    works today (it is the `examples/coffee.py` shape) and gives a live goal-driving demo.

  * a CNL file (``.cnl``) declaring operators + state + goal. This routes through
    ``harneskills.planning_kb.load_planning_kb`` — the operator/goal CNL surface being
    built in parallel. Until that module lands the ``.cnl`` planning path reports that it
    is not yet wired (rather than pretending); the seam auto-activates on import success.

STEP EVENTS. Every operator is given an action wrapper in the ``actions`` dict handed to
``planning.solve``. Because ``_perform_op`` routes any op whose name is in ``actions``
through its tool, the wrapper is the single choke point where we (a) perform the op's
effect (a real tool if the KB supplies one, else ``simulate_effects``, else a withheld
effect for a seeded failure), (b) post a ``StepEvent`` so the user watches the plan drive
forward, and (c) honor step-mode pausing and stop. Acting stays folded into the canonical
solve fixpoint — we only observe it, we do not re-implement the loop.
"""
from __future__ import annotations

import importlib.util
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

import ugm
import harneskills as h
from harneskills import planning

from .messages import ErrorEvent, GoalReachedEvent, ImpasseEvent, StatusEvent, StepEvent

if TYPE_CHECKING:
    from .screen import CLIScreen


# ---------------------------------------------------------------------------
# Salvaged, paradigm-independent helpers (log / value parsing / KB scan)
# ---------------------------------------------------------------------------

class SessionLog:
    def __init__(self, session_dir: Path) -> None:
        self._path = session_dir / "session.log"
        self._lock = threading.Lock()
        self._t0 = time.time()

    @property
    def path(self) -> Path:
        return self._path

    def write(self, line: str) -> None:
        elapsed = time.time() - self._t0
        with self._lock:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(f"[+{elapsed:6.1f}s] {line}\n")


def parse_value(s: str) -> Any:
    """Parse a string value into bool / int / float / str."""
    if s == "True":
        return True
    if s == "False":
        return False
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def parse_goal_text(text: str) -> dict[str, Any]:
    """Parse a goal line into ``{condition_name: value}``.

    In the current planning model a goal is a set of CONDITION names (``<goal> --want--> C``),
    not typed slots. So each whitespace token is read as a goal condition:
      * ``have_coffee``            -> ``{"have_coffee": True}``   (bare condition)
      * ``have_coffee have_milk``  -> two conditions
      * ``slot=value``             -> ``{"slot": value}``  (the key is used as the condition;
                                       the value is retained only for display/back-compat)
    The runner seeds ``seed_goal(graph, key)`` for every key. Returning ``{}`` for empty
    input lets the screen fall back to the KB-declared goal.
    """
    result: dict[str, Any] = {}
    for token in text.split():
        if "=" in token:
            slot, val_str = token.split("=", 1)
            result[slot.strip()] = parse_value(val_str.strip())
        else:
            result[token.strip()] = True
    return result


def scan_corpus_kbs(root: Path | None = None, *, require_registry: bool = False) -> list[Path]:
    """Return runnable planning-KB modules under ``root`` (default cwd).

    A runnable KB is a ``.py`` file exporting ``build`` / ``build_kb`` and using the
    planning seeders (a cheap source-text check — ``seed_operator`` / ``seed_goal`` /
    ``DEFAULT_GOAL``). ``require_registry`` is accepted for call-site compatibility with the
    old scanner but ignored (the current contract has no ``build_registry``).
    """
    if root is None:
        root = Path.cwd()
    candidates: list[Path] = []
    for py in sorted(root.glob("**/*.py")):
        if any(part in {".venv", "__pycache__", ".git", ".claude"} for part in py.parts):
            continue
        try:
            src = py.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        has_build = ("def build_kb" in src or "def build(" in src
                     or "build_kb =" in src or "build =" in src)
        looks_planning = ("seed_operator" in src or "seed_goal" in src
                          or "DEFAULT_GOAL" in src)
        if has_build and looks_planning:
            candidates.append(py)
    return candidates


def _load_kb_module(path_str: str):
    """Import a KB module by file path so its relative imports resolve."""
    path = Path(path_str).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"KB module not found: {path}")
    spec = importlib.util.spec_from_file_location("_tui_kb_module", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from: {path}")
    module = importlib.util.module_from_spec(spec)
    parent = str(path.parent)
    added = parent not in sys.path
    if added:
        sys.path.insert(0, parent)
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    finally:
        if added and parent in sys.path:
            sys.path.remove(parent)
    return module


# ---------------------------------------------------------------------------
# Graph introspection — operators, goal, current state
# ---------------------------------------------------------------------------

_OP_KINDS = {"pre", "add", "del", "cost"}


def _operator_rels(graph: ugm.Graph, op_id: str) -> dict[str, list[str]]:
    """`{"pre": [...], "add": [...], "del": [...], "cost": [...]}` for an operator node."""
    out: dict[str, list[str]] = {"pre": [], "add": [], "del": [], "cost": []}
    for r, o in graph.relations_from(op_id):
        rn = graph.name(r)
        if rn in out:
            out[rn].append(graph.name(o))
    return out


def _operator_ids(graph: ugm.Graph) -> dict[str, str]:
    """`{operator_name: node_id}` for every node authored as an operator (has pre/add/del/cost)."""
    ops: dict[str, str] = {}
    for n in graph.nodes():
        if any(graph.name(r) in _OP_KINDS for r, _ in graph.relations_from(n)):
            ops.setdefault(graph.name(n), n)
    return ops


def _now_true(graph: ugm.Graph) -> list[str]:
    """Condition names currently observed true: `<now> --true--> C`."""
    out: list[str] = []
    for now in graph.nodes_named("<now>"):
        for r, o in graph.relations_from(now):
            if graph.name(r) == "true":
                out.append(graph.name(o))
    return sorted(set(out))


def _goal_conditions(graph: ugm.Graph) -> list[str]:
    """Condition names the goal wants: `<goal> --want--> C`."""
    out: list[str] = []
    for goal in graph.nodes_named("<goal>"):
        for r, o in graph.relations_from(goal):
            if graph.name(r) == "want":
                out.append(graph.name(o))
    return sorted(set(out))


class _GraphDMView:
    """Read-only 'domain model' view for `/dm`, `?` autocomplete and `_cmd_query`.

    Presents the observed world state (`<now>` true conditions) as flat slot=value pairs and
    exposes no entity scopes (the current substrate has none), so the screen's scope loop is a
    no-op. It quacks like the old DomainModel just enough for the inspection commands."""

    def __init__(self, graph: ugm.Graph) -> None:
        self._g = graph

    def keys(self) -> list[str]:
        return _now_true(self._g)

    def get(self, key: str) -> Any:
        return True if key in _now_true(self._g) else None

    def entity_scopes(self) -> list[str]:
        return []


class _GraphKBView:
    """Read-only KB view: operator names -> a short 'pre → add' descriptor (for `?`/`/dm`)."""

    def __init__(self, graph: ugm.Graph) -> None:
        self._g = graph

    def _ops(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for name, oid in _operator_ids(self._g).items():
            rels = _operator_rels(self._g, oid)
            pre = ", ".join(rels["pre"]) or "∅"
            add = ", ".join(rels["add"]) or "∅"
            out[name] = f"{pre} → {add}"
        return out

    def keys(self) -> list[str]:
        return sorted(self._ops())

    def get(self, key: str) -> Any:
        return self._ops().get(key)


# ---------------------------------------------------------------------------
# The runner
# ---------------------------------------------------------------------------

class _Stopped(Exception):
    """Raised inside an action wrapper to abort the solve fixpoint on /stop."""


def _short(v: object) -> str:
    s = repr(v).replace("\n", "↵")
    return (s[:80] + "…") if len(s) > 80 else s


class HarnessRunner:
    def __init__(self, screen: "CLIScreen") -> None:
        self._screen = screen
        self._graph: ugm.Graph | None = None
        self._dm: _GraphDMView | None = None
        self._kbv: _GraphKBView | None = None
        self._stop_flag = threading.Event()
        self._step_gate = threading.Event()
        self._step_gate.set()          # starts open (no pause)
        self._step_mode = False
        self._step_count = 0
        self._last_action: Any = None
        self._procedures: dict[str, list[str]] = {}

    # ---- properties the screen reads --------------------------------------
    @property
    def procedures(self) -> dict[str, list[str]]:
        return self._procedures

    @property
    def dm(self) -> _GraphDMView | None:
        return self._dm

    @property
    def kb(self) -> _GraphKBView | None:
        return self._kbv

    @property
    def step_count(self) -> int:
        return self._step_count

    @property
    def entity_label_to_scope(self) -> dict[str, str]:
        return {}

    @property
    def last_action(self) -> Any:
        return self._last_action

    @property
    def objective(self) -> Any:
        return None

    # ---- lifecycle --------------------------------------------------------
    def start(
        self,
        goal_slots: dict[str, Any],
        kb_path: str,
        dm_seed: dict[str, Any],
        max_steps: int,
        *,
        entity_scopes: dict[str, dict[str, Any]] | None = None,
        suppose_sentences: list[str] | None = None,
        step_mode: bool = False,
        procedure: str | None = None,
    ) -> None:
        self._stop_flag.clear()
        self._step_gate.set()
        self._step_mode = step_mode
        self._step_count = 0
        self._last_action = None
        self._procedures = {}
        t = threading.Thread(
            target=self._run,
            args=(goal_slots, kb_path, dm_seed, max_steps, procedure),
            daemon=True,
        )
        t.start()

    def stop(self) -> None:
        self._stop_flag.set()
        self._step_gate.set()          # unblock if paused mid-step

    def continue_step(self) -> None:
        self._step_gate.set()

    # ---- worker -----------------------------------------------------------
    def _run(self, goal_slots, kb_path, dm_seed, max_steps, procedure=None) -> None:
        try:
            self._do_run(goal_slots, kb_path, dm_seed, max_steps, procedure)
        except _Stopped:
            return                     # /stop — screen already reset by _cmd_stop
        except Exception as exc:
            if not self._stop_flag.is_set():
                self._screen.post_message(
                    ErrorEvent(f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")
                )

    def _do_run(self, goal_slots, kb_path, dm_seed, max_steps, procedure=None) -> None:
        graph, actions, failures = self._load(kb_path, goal_slots, dm_seed)
        self._graph = graph
        self._dm = _GraphDMView(graph)
        self._kbv = _GraphKBView(graph)
        wrapped = self._wrap_actions(graph, actions, failures)

        if procedure is not None:
            self._drive_procedure(graph, procedure, wrapped, max_steps)
            return

        if not _goal_conditions(graph):
            self._screen.post_message(ImpasseEvent(
                "no goal", ["No goal condition seeded. Use /goal <condition> "
                            "or a KB that seeds one."]))
            return

        result = planning.solve(graph, actions=wrapped, max_cycles=max(max_steps, 20))

        if self._stop_flag.is_set():
            return
        if result == "done":
            self._screen.post_message(GoalReachedEvent(
                self._step_count,
                [f"{c} is true" for c in _goal_conditions(graph)]))
        else:
            wants = _goal_conditions(graph)
            have = set(_now_true(graph))
            missing = [c for c in wants if c not in have]
            self._screen.post_message(ImpasseEvent(
                "planning quiesced short of the goal",
                [f"still needed: {', '.join(missing) or '(none?)'}",
                 f"reached {self._step_count} step(s)"]))

    def _drive_procedure(self, graph, name, wrapped, max_steps) -> None:
        """Run a named procedure declared in the KB: stage its steps and execute them in order,
        letting the planner gap-fill any unmet precondition (run_procedure gap_fill=True). The
        step wrappers still fire, so the user watches the sequence drive exactly like a goal."""
        steps = self._procedures.get(name)
        if not steps:
            self._screen.post_message(ImpasseEvent(
                f"unknown procedure '{name}'",
                [f"procedures in this KB: {', '.join(sorted(self._procedures)) or '(none)'}"]))
            return
        result = h.run_procedure(graph, name, self._procedures,
                                 actions=wrapped, max_cycles=max(max_steps, 20))
        if self._stop_flag.is_set():
            return
        if result == "done":
            self._screen.post_message(GoalReachedEvent(
                self._step_count, [f"procedure '{name}' ran: {' → '.join(steps)}"]))
        else:
            self._screen.post_message(ImpasseEvent(
                f"procedure '{name}' stalled",
                [f"declared steps: {' → '.join(steps)}",
                 "an unmet precondition had no producer (see /dm for observed state)"]))

    # ---- KB loading -------------------------------------------------------
    def _load(self, kb_path: str, goal_slots: dict, dm_seed: dict):
        """Return `(graph, actions, failures)` ready for solve. Seeds the user's goal + state."""
        is_cnl = kb_path.lower().endswith(".cnl")
        actions: dict[str, Callable] = {}
        failures: dict[str, int] = {}

        if is_cnl:
            graph = self._load_cnl(kb_path)
        else:
            module = _load_kb_module(kb_path)
            builder = getattr(module, "build", None) or getattr(module, "build_kb", None)
            if builder is None:
                raise AttributeError(
                    f"KB module {kb_path!r} must define build() or build_kb() -> Graph")
            graph = builder()
            if hasattr(module, "build_actions"):
                actions = dict(module.build_actions(graph) or {})
            if hasattr(module, "FAILURES"):
                failures = dict(module.FAILURES or {})
            if not _goal_conditions(graph) and not goal_slots and hasattr(module, "DEFAULT_GOAL"):
                goal_slots = {module.DEFAULT_GOAL: True}

        # Seed the user's goal conditions + any /seed state on top of what the KB authored.
        for cond in goal_slots:
            h.seed_goal(graph, cond)
        if dm_seed:
            h.seed_state(graph, list(dm_seed.keys()))
        return graph, actions, failures

    def _load_cnl(self, kb_path: str) -> ugm.Graph:
        text = Path(kb_path).expanduser().resolve().read_text(encoding="utf-8")
        try:
            from harneskills.planning_kb import load_planning_program  # type: ignore
        except Exception:
            load_planning_program = None                     # planning CNL surface not present
        if load_planning_program is None:
            raise RuntimeError(
                "The planning CNL surface (harneskills.planning_kb.load_planning_program) isn't "
                "available. Drive planning from a .py KB (e.g. examples/coffee_kb.py), or explore "
                "this .cnl for Q&A via the REPL (python -m harneskills.repl).")
        graph, procedures = load_planning_program(text)
        self._procedures = procedures                        # {name: [ordered steps]} for /do
        return graph

    # ---- step instrumentation --------------------------------------------
    def _wrap_actions(self, graph: ugm.Graph, actions: dict, failures: dict) -> dict:
        """Wrap EVERY operator so acting emits a StepEvent + honors step-mode / stop.

        The wrapper is what `planning._perform_op` calls for any op named in the returned
        dict, so it is the one place effects are produced: a real KB tool if supplied, a
        withheld effect for a seeded failure (drives divergence -> replan), else the
        operator's declared effects via `simulate_effects` (the default)."""
        wrapped: dict[str, Callable] = {}
        for name, _oid in _operator_ids(graph).items():
            wrapped[name] = self._make_wrapper(name, actions.get(name), failures)
        return wrapped

    def _make_wrapper(self, name: str, real: Callable | None, failures: dict) -> Callable:
        screen = self._screen

        def wrapper(g: ugm.Graph, op_id: str) -> None:
            if self._stop_flag.is_set():
                raise _Stopped()

            rels = _operator_rels(g, op_id)
            before = set(_now_true(g))
            pre_values = {c: ("true" if c in before else "missing") for c in rels["pre"]}

            withheld = False
            if real is not None:
                real(g, op_id)                       # real §8 action observes its own effects
            elif failures.get(name, 0) > 0:
                failures[name] -= 1                  # divergence: withhold effects this once
                withheld = True
            else:
                planning.simulate_effects(g, op_id)  # default: declared effects materialize

            after = set(_now_true(g))
            committed = [c for c in rels["add"] if c in after]
            residuals = [c for c in rels["add"] if c not in after]
            post_values = {c: ("withheld" if withheld and c in residuals else "true")
                           for c in rels["add"]}

            self._step_count += 1
            self._last_action = name
            lhs = ", ".join(rels["pre"]) or "∅"
            rhs = ", ".join(rels["add"]) or "∅"
            screen.post_message(StepEvent(
                self._step_count, name, committed, residuals,
                rule_line=f"{lhs} → {rhs}",
                pre_values=pre_values, post_values=post_values,
            ))
            screen.post_message(StatusEvent("step", self._step_count))

            if self._step_mode:
                self._step_gate.clear()
                self._step_gate.wait()               # block until continue_step() / stop()
                if self._stop_flag.is_set():
                    raise _Stopped()

        return wrapper
