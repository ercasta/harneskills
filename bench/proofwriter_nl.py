"""
RAW-NL coverage probe — ProofWriter through the ACTUAL front-end (the "not a toy" milestone).

`proofwriter_coverage.py` measured reasoning by loading the FORMAL representation (atoms ->
triples + machine-rules). This probe instead feeds the NATURAL-LANGUAGE theory + questions through
the real `Session` pipeline (tokenize -> forms -> reason -> answer), so it measures how far the NL
SURFACE actually carries — the honest end-to-end test the earlier probe deliberately bypassed.

Each ProofWriter theory is NL like:
    "Anne is quiet. Anne is young. Dave is rough. If someone is rough then they are young."
and each question is a declarative ("Anne is young." / "Anne is not young.") judged true/false
under CWA. We assert every theory sentence via `Session`, convert each question to an interrogative
(`is anne young`), and compare the yes/no answer to the gold label.

Each theory's VERB CATALOG (the base forms of its non-`is` predicates) is DECLARED to the Session
first (`eat is a relation`, …) — the lexicon is DATA, not inferred from position (the engine has no
learning yet). English inflection (`eats`/`eat`) is folded to one base form here, in the
corpus-adaptation layer, so the CNL itself stays 'caveman' (one canonical verb form). Both copula
(`is X Y`) and relational (`does X V Y`) questions are asked.

Reports, by question depth: PARSE coverage (theory sentences the grammar recognized), question
recognition, and ACCURACY on recognized questions — and the failure breakdown, so the next grammar
gap is visible. Run:  python bench/proofwriter_nl.py [N_THEORIES] [DEPTH]
"""
from __future__ import annotations

import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

import json
import harneskills as h

ZIP = Path(r"C:\Users\ercas\AppData\Local\Temp\claude\C--Users-ercas-creazioni-harneskills"
           r"\66d3fcf7-9bca-4f56-9cb8-eb5074afaad2\scratchpad\pw.zip")

REP = re.compile(r'\(\s*"([^"]*)"\s+"([^"]*)"\s+"([^"]*)"\s+"([+\-~])"\s*\)')


def _base(verb: str) -> str:
    """The caveman base form of a verb — strip a trailing 3rd-person `-s` (`eats`->`eat`,
    `chases`->`chase`, `sees`->`see`). ProofWriter's verbs are all regular, so this one rule
    unifies the fact form (`the dog eats`) and the rule form (`they eat`) to ONE predicate. English
    morphology is DELIBERATELY out of the CNL (the 'caveman' decision) — it lives here, in the
    corpus-adaptation layer, exactly like the trailing-period + case normalization below."""
    return verb[:-1] if verb.endswith("s") and not verb.endswith("is") else verb


def _theories(depth: int, limit: int):
    """Yield (theory_sentences, questions, verb_bases) from the CWA meta-test file. `verb_bases`
    is the theory's VERB CATALOG — the base forms of every non-`is` predicate in its facts +
    questions (representations give the canonical predicate). We DECLARE this catalog to the
    Session (`V is a relation`) rather than infer verbs from position: the lexicon is DATA
    (vision), and the engine has no learning yet to induce it."""
    member = f"proofwriter-dataset-V2020.12.3/CWA/depth-{depth}/meta-test.jsonl"
    zf = zipfile.ZipFile(ZIP)
    n = 0
    with zf.open(member) as f:
        for line in f:
            rec = json.loads(line)
            sents = [v["text"] for v in rec.get("triples", {}).values()]
            sents += [v["text"] for v in rec.get("rules", {}).values()]
            qs = list(rec.get("questions", {}).values())
            verbs = set()
            for v in list(rec.get("triples", {}).values()) + qs:
                parsed = _query(v.get("representation", ""))
                if parsed and parsed[1] != "is":
                    verbs.add(_base(parsed[1]))
            yield sents, qs, verbs
            n += 1
            if n >= limit:
                return


def _query(rep: str) -> tuple[str, str, str, str] | None:
    """Parse a question representation `("subj" "is" "obj" POL)` -> (subj, pred, obj, pol)."""
    m = REP.match(rep.strip())
    return (m.group(1), m.group(2), m.group(3), m.group(4)) if m else None


def _caveman(line: str, bases: set) -> str:
    """Corpus-adaptation normalization: strip the trailing sentence period, lowercase, and fold
    every verb token to its declared base form (`eats`/`eat` -> `eat`). Keeps the CNL 'caveman'
    (one canonical verb form) while letting ProofWriter's inflected English through."""
    line = line.strip().rstrip(".").strip()
    forms = {f: b for b in bases for f in (b, b + "s")}
    return " ".join(forms.get(w.lower(), w) for w in line.split())


def run(limit: int = 40, depth: int = 1) -> None:
    stats = defaultdict(int)
    by_depth = defaultdict(lambda: defaultdict(int))
    fails: list[str] = []

    for sents, qs, verbs in _theories(depth, limit):
        s = h.Session()
        # Opt into DEFINITENESS: a `the X` reference denotes ONE individual (ProofWriter's entities
        # are unique). The Session marks such entities `is_unique` and MERGES their mentions to one
        # node — correct AND O(mentions), so coreference over relational facts no longer blows up
        # (without this, the same-named entities in `dog eat squirrel` / `squirrel eat cat` drive
        # O(k²) coref + `same_as` saturation → seconds/query). See memory decision_verb_catalog.
        s.submit("the is a definite")
        # DECLARE the theory's verb CATALOG (`V is a relation`) before asserting — the lexicon is
        # DATA, and a declared verb becomes a keyword that (a) stops the NP decomposition from
        # eating it and (b) folds inside a rule. Then ASSERT the theory, caveman-normalized
        # (period/case + verb base form). Count how many sentences the grammar recognized.
        for v in sorted(verbs):
            s.submit(f"{v} is a relation")
        for line in sents:
            line = _caveman(line, verbs)
            stats["sent_total"] += 1
            try:
                r = s.submit(line)
                stats["sent_ok"] += 1 if r.recognized and not r.is_question else 0
                if not (r.recognized and not r.is_question):
                    stats["sent_unrec"] += 1
                    if len(fails) < 25:
                        fails.append(f"SENT unrec: {line!r}")
            except Exception as e:
                stats["sent_err"] += 1
                if len(fails) < 25:
                    fails.append(f"SENT err: {line!r} -> {type(e).__name__}: {e}")

        # ASK each question — copula `is X Y` AND relational `does X V Y` (verb base form).
        for q in qs:
            parsed = _query(q.get("representation", ""))
            gold = q.get("answer")
            qd = q.get("QDep", -1)
            stats["q_total"] += 1
            by_depth[qd]["total"] += 1
            if parsed is None:
                stats["q_skip_nonis"] += 1
                by_depth[qd]["skip"] += 1
                continue
            subj, pred, obj, pol = parsed
            # Entities take `the` (as in the asserted sentences), so a multi-word entity (`the bald
            # eagle`) decomposes the SAME way on both sides and the query matches the merged node.
            if pred == "is":
                query = f"is the {subj.lower()} {obj.lower()}"          # obj is an attribute
            else:                                        # relational: `does the subj VERB the obj`
                query = f"does the {subj.lower()} {_base(pred.lower())} the {obj.lower()}"
            try:
                ans = s.submit(query)
            except Exception as e:
                stats["q_err"] += 1
                if len(fails) < 25:
                    fails.append(f"Q err: {query!r} -> {type(e).__name__}: {e}")
                continue
            if not ans.is_question:
                stats["q_unrec"] += 1
                by_depth[qd]["unrec"] += 1
                if len(fails) < 25:
                    fails.append(f"Q unrec: {query!r} (from {q.get('question')!r})")
                continue
            said_yes = ans.answer == ["yes"]
            expect_yes = bool(gold) if pol == "+" else (not bool(gold))
            correct = (said_yes == expect_yes)
            stats["q_ans"] += 1
            stats["q_correct"] += 1 if correct else 0
            by_depth[qd]["ans"] += 1
            by_depth[qd]["correct"] += 1 if correct else 0
            if not correct and len(fails) < 25:
                fails.append(f"Q wrong: {query!r} said={ans.answer} expect_yes={expect_yes} "
                             f"(gold={gold}, pol={pol})")

    print(f"\n=== ProofWriter RAW-NL probe — depth {depth}, {limit} theories ===")
    st = dict(stats)
    print(f"theory sentences: {st.get('sent_ok',0)}/{st.get('sent_total',0)} recognized "
          f"({st.get('sent_unrec',0)} unrec, {st.get('sent_err',0)} err)")
    print(f"questions: {st.get('q_total',0)} total; {st.get('q_skip_nonis',0)} unparseable-rep "
          f"skipped; {st.get('q_unrec',0)} unrec; {st.get('q_err',0)} err")
    ans = st.get('q_ans', 0)
    print(f"answered: {ans}; accuracy on answered: "
          f"{(st.get('q_correct',0)/ans*100 if ans else 0):.1f}% "
          f"({st.get('q_correct',0)}/{ans})")
    print("by QDep (answered/total, accuracy):")
    for qd in sorted(by_depth):
        d = by_depth[qd]
        a = d.get("ans", 0)
        print(f"  QDep {qd}: answered {a}/{d['total']}, "
              f"acc {(d.get('correct',0)/a*100 if a else 0):.0f}%")
    print("\n--- sample failures ---")
    for line in fails:
        print(" ", line)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    d = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    run(n, d)
