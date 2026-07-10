"""
Human-in-the-loop — the user as an external source (vision §8 / §12.5).

When reasoning cannot settle something on its own — which mentions corefer, which of
several options to commit to, whether a low-confidence fact holds — the substrate must
not silently guess. It surfaces the uncertainty to the *user*, through exactly the
request/dispatcher handshake of `external.py`, with the external source being a human
`Oracle` instead of a price DB / web call:

    a RULE emits a CLARIFY request token  ──▶  the DISPATCHER routes it to the
    user-backed handler  ──▶  the user answers  ──▶  the answer lands as nodes  ──▶
    RULES fire on it.

So "ask the user" is not a special control path — it is the §8 calculator pattern with
the calculator being a person. The driver stays dumb: WHICH uncertainties are surfaced,
and WHEN, is decided by rules emitting clarify tokens, never by Python deciding on its
own to interrupt the user.

An `Oracle` is any callable `(prompt, options) -> answer` (options may be None for a
free-text question). The REPL supplies one that prompts at the terminal; tests / headless
runs supply a canned one (`auto_oracle`). Coreference disambiguation is the first
consumer (`disambiguation_resolver`), but the same oracle answers any clarify request
(`ask_user_handler`).
"""
from __future__ import annotations

from typing import Callable, Optional

from ugm.dispatch import call_arg, call_tool
from ugm.external import ARG, CLARIFY_DEFAULT_KIND, emit_result
from ugm.world_model import Graph

# An Oracle answers a posed question. `options`, when given, are the allowed answers.
Oracle = Callable[[str, Optional[list[str]]], str]


# ---------------------------------------------------------------------------
# Oracles — where the answers come from
# ---------------------------------------------------------------------------

def auto_oracle(answer: str = "same") -> Oracle:
    """A non-interactive oracle (tests / headless): always returns `answer`. The default
    'same' makes coref keep a consistent link (the no-user behaviour)."""
    def oracle(prompt: str, options: list[str] | None = None) -> str:
        return answer
    return oracle


def scripted_oracle(answers: list[str]) -> Oracle:
    """An oracle that returns successive `answers` (then repeats the last) — for tests that
    pose several questions."""
    box = {"i": 0}

    def oracle(prompt: str, options: list[str] | None = None) -> str:
        i = min(box["i"], len(answers) - 1)
        box["i"] += 1
        return answers[i]
    return oracle


def terminal_oracle(read: Callable[[str], str] = input,
                    write: Callable[[str], None] = print) -> Oracle:
    """An oracle that prompts the user at a terminal. `read`/`write` are injected so the
    REPL (or a test) controls the I/O; the default uses builtin input/print."""
    def oracle(prompt: str, options: list[str] | None = None) -> str:
        write(prompt + (f" [{' / '.join(options)}]" if options else ""))
        return read("> ").strip()
    return oracle


# ---------------------------------------------------------------------------
# Coreference disambiguation — ask the user only for the ambiguous residue
# ---------------------------------------------------------------------------

def disambiguation_resolver(oracle: Oracle) -> Callable[[Graph, str, str, str], str]:
    """Build a coref resolver that consults the user.

    It is invoked by `coref_walk.resolve_coref` ONLY for a link that is CONSISTENT but
    identity-underdetermined — reasoning has already auto-rejected provably-distinct
    mentions (two Pauls in disjoint categories), with no user involvement. So the user is
    asked only about the genuine residue. Returns 'same' or 'distinct'."""
    def resolve(graph: Graph, name: str, a: str, b: str) -> str:
        answer = oracle(
            f"Do both mentions of '{name}' refer to the same thing?",
            ["same", "distinct"],
        )
        return "distinct" if answer.strip().lower().startswith("d") else "same"
    return resolve


# ---------------------------------------------------------------------------
# General clarify handler — any rule-emitted <clarify-request> token
# ---------------------------------------------------------------------------

def ask_user_handler(oracle: Oracle, *, kind: str = CLARIFY_DEFAULT_KIND) -> Callable:
    """A tool (dispatch.py: `handler(graph, call_id) -> touched ids`) for a rule-emitted
    clarify request `<call> --tool--> clarify --arg--> X`.

    The user is asked about the arg's NAME, and the answer is emitted as an ordinary lookup
    RESULT fact (`external.emit_result`) so rules read it with `results_for`/`result_value`
    like any other external value; `service_calls` consumes the call. This is the general
    uncertainty/intervention tool — coreference is one consumer; planning ambiguity or a
    low-confidence fact would emit the same call."""
    def handler(graph: Graph, call_id: str) -> set[str]:
        request_kind = call_tool(graph, call_id) or kind
        arg = call_arg(graph, call_id, ARG)
        if arg is None:
            return set()
        answer = oracle(f"Clarify '{graph.name(arg)}':", None)
        return {arg, emit_result(graph, request_kind, arg, answer)}
    return handler
