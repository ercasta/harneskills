"""
The harneskills TUI — the way users drive the engine.

A thin REPL over `Session` (all engine logic lives there). Type CNL to assert facts,
native rules, and constraint declarations; type a question to query; load a `.cnl` file;
check consistency; explain a derivation. Lines no form recognizes are reported clearly
rather than silently ignored.

Run:  python -m harneskills.repl  [file.cnl ...]
Commands:
  :load FILE     load a .cnl corpus
  :facts         list the known facts
  :rules         how many domain rules are active
  :check         report contradictions (consistency)
  :unparsed      lines that matched no form this session
  :why S P O     explain a derivation
  :help  :quit
"""
from __future__ import annotations

import sys

from .interaction import terminal_oracle
from .session import LineResult, Session


def _print_result(r: LineResult) -> None:
    if r.error:
        print(f"   ! error: {r.error}")
        return
    if r.is_question:
        print("   ?", ", ".join(r.answer) if r.answer else "(no answer)")
        return
    if not r.recognized:
        print(f"   ?? no form recognized: {r.line!r}")
        return
    for f in r.new_facts:
        print("   +", f)
    if r.recognized and not r.new_facts:
        print("   (recognized; no new facts)")
    for c in r.contradictions:
        print(f"   ! CONTRADICTION: {', '.join(c['about'])} violates {', '.join(c['violates'])}")


def _command(session: Session, line: str) -> bool:
    """Handle a ':' command. Returns False to quit, True to continue."""
    parts = line.split()
    cmd = parts[0]
    if cmd == ":quit":
        return False
    if cmd == ":help":
        print(__doc__.split("Commands:")[1])
    elif cmd == ":facts":
        for f in session.facts():
            print("   ", f)
        if not session.facts():
            print("    (no facts yet)")
    elif cmd == ":rules":
        print(f"    {len(session.rules)} domain rule(s) active")
    elif cmd == ":check":
        cs = session.contradictions()
        if not cs:
            print("    consistent - no contradictions")
        for c in cs:
            print(f"   ! {', '.join(c['about'])} violates {', '.join(c['violates'])}")
    elif cmd == ":unparsed":
        for u in session.unparsed():
            print("   ??", u)
        if not session.unparsed():
            print("    (everything recognized)")
    elif cmd == ":load":
        if len(parts) != 2:
            print("    usage: :load FILE")
        else:
            try:
                results = session.load_file(parts[1])
            except OSError as e:
                print(f"    cannot load {parts[1]}: {e}")
                return True
            ok = sum(r.recognized for r in results)
            print(f"    loaded {parts[1]}: {ok}/{len(results)} lines recognized")
            for r in results:
                if not r.recognized:
                    print(f"   ?? {r.line!r}")
            cs = session.contradictions()
            for c in cs:
                print(f"   ! CONTRADICTION: {', '.join(c['about'])} violates {', '.join(c['violates'])}")
    elif cmd == ":why":
        if len(parts) == 4:
            for ln in session.explain(parts[1], parts[2], parts[3]):
                print("   ", ln)
        else:
            print("    usage: :why SUBJECT PREDICATE OBJECT")
    else:
        print(f"    unknown command {cmd!r} — try :help")
    return True


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    # An interactive oracle so the engine can ask the user to disambiguate / intervene when
    # reasoning leaves a coreference (or other uncertainty) genuinely undecided.
    session = Session(oracle=terminal_oracle())
    print("harneskills - enter CNL; :help for commands, :quit to exit")
    for path in argv:                                    # load any files given on the CLI
        _command(session, f":load {path}")
    print("try:  paul is a person /  every person is a mortal /  is paul a mortal")
    while True:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line.startswith(":"):
            if not _command(session, line):
                break
            continue
        _print_result(session.submit(line))


if __name__ == "__main__":
    main()
