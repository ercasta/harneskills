"""
Pins the real-corpus recall/precision of the mutate-during-iteration detector THROUGH THE LIVE JOERN
PIPELINE (bench/joern_corpus.py). A labeled corpus (tests/fixtures/joern_corpus_source.py) compiled by
real pysrc2cpg + joern-export (captured in joern_corpus_graphson.json) is decoded and run through the
shape-B recognizer. This is the end-to-end validation the earlier probes deferred: real extraction, real
decode, real recognition. Reproducible offline from the fixture (no live joern needed).

Ground truth = function-name prefix: pos_ (real bug, must flag), neg_ (safe, must stay silent), hard_
(real bug expected to miss). Result at capture time: recall 8/8, precision 8/8 (0 false positives), 0
hard_ cases remaining — the former alias miss was closed by `same_as` alias resolution (see below).
"""
from bench import joern_corpus as jc


def test_real_corpus_recall_precision_through_live_joern():
    m = jc.measure()
    assert len(m["pos"]) == 8 and len(m["neg"]) == 8 and len(m["hard"]) == 0
    # 100% recall: every real MDI bug is caught across shapes (list/dict/set; remove/pop/discard/
    # append/insert; nested inner-mutates-inner and inner-mutates-outer; mutation through an alias).
    assert m["recall"] == 1.0, m["missed_pos"]
    # 100% precision: zero false positives on the safe patterns (copy idiom x2, accumulator,
    # different-collection, read-only, comprehension, mutate-before-loop, nested read-loop in a
    # mutating loop).
    assert m["false_pos"] == [], m["false_pos"]
    assert m["precision"] == 1.0


def test_nested_readloop_not_flagged():
    # Regression pin for the bounded-`looptmp` fix (finding-real-corpus-django): an outer loop that
    # appends to a separate accumulator with a read-only `for a in acc` NESTED inside must stay silent.
    # Pre-fix the outer loop absorbed the inner iterator via `?w ast_star ?nc`, so `acc.append` false-
    # flagged; this was the real FP shape found in django/utils translation/template.py.
    m = jc.measure()
    assert "neg_readloop_nested_in_mutating_loop" not in m["flagged"], m["flagged"]


def test_alias_mutation_now_caught():
    # Mutation through an ALIAS (`a = xs; for x in xs: a.remove(x)`) — the alias is a distinct LOCAL, so
    # the receiver's REF resolves to a different decl than the iterated collection. Closed by the
    # `same_as` alias-resolution rules (cpg.JOERN_RECOGNIZER_RULES) + `consumes`-propagation across
    # `same_as` (cpg.MECHANISM_RULES): the EXISTING hazard rule then composes unchanged. Precision is
    # preserved because `same_as` links distinct decls ONLY for a two-identifier plain assignment — a
    # `list(xs)`/`xs[:]` copy has a CALL rhs (one `asgnvar`), so copies stay silent (asserted above).
    m = jc.measure()
    assert "pos_alias_mutate" in m["flagged"], m["missed_pos"]
