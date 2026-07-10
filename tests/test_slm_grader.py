"""
SLM NL->CNL exact-reward harness (docs/vision_agentic.md §9, harneskills/slm.py). De-risks the
LINCHPIN of the final arc pillar: the parser gives a free, exact, automatic grade for a candidate CNL
translation, so no model/GPU is needed to validate the reward signal the fine-tune will train on.

The tests pin the property that makes frame-graph matching the right grader (vs parse-success or
string similarity): it catches CONFIDENTLY-WRONG CNL — valid, parses cleanly, but denotes a different
frame — and it scores the SLM's copy-through-vs-normalize behavior. Everything is asserted through the
public grade (strings, booleans, scalars); nothing touches internals.
"""
from harneskills import slm


def test_exact_translation_scores_one():
    g = slm.grade("alice is a customer", gold="alice is a customer")
    assert g.parsed and g.exact
    assert g.missing == () and g.extra == ()
    assert slm.reward("alice is a customer", "alice is a customer") == 1.0


def test_confidently_wrong_translation_is_caught():
    # valid CNL, parses cleanly, but MEANS something else -> frame-graph match rejects it where a
    # parse-success or string-similarity check would wave it through. This is the whole reason the
    # grader compares frames, not surface.
    g = slm.grade("alice is a person", gold="alice is a customer")
    assert g.parsed                                   # it DID parse (the trap)...
    assert not g.exact                                # ...but the frame is wrong
    assert g.missing == ("alice is_a customer",)
    assert g.extra == ("alice is_a person",)
    assert 0.0 <= slm.reward("alice is a person", "alice is a customer") < 1.0


def test_unparseable_candidate_scores_zero_and_is_distinguished():
    g = slm.grade("blah blah blah", gold="alice is a customer")
    assert not g.parsed and not g.exact               # distinct from parsed-but-wrong
    assert slm.reward("blah blah blah", "alice is a customer") == 0.0


def test_copy_through_unknown_token_vs_normalizing_it():
    # The SLM's specific job on an out-of-vocabulary term: copy it VERBATIM into the slot, never
    # normalize it to something familiar. The grader distinguishes the two.
    gold = "the widget is a gadget"
    assert slm.grade("the widget is a gadget", gold).exact          # copied through -> correct
    normalized = slm.grade("the item is a gadget", gold)            # normalized widget->item -> wrong
    assert not normalized.exact
    assert normalized.missing == ("widget is_a gadget",)
    assert normalized.extra == ("item is_a gadget",)


def test_frame_graph_is_order_and_surface_independent():
    # gold facts in a different LINE ORDER still match (the frame graph is a SET, not a sequence),
    # and a different surface that denotes the same frame matches (definite `the` drops).
    a = "alice is a customer\nbob is a customer"
    b = "bob is a customer\nalice is a customer"
    assert slm.grade(a, gold=b).exact
    assert slm.grade("the eagle is a bird", gold="eagle is a bird").exact


def test_partial_translation_gets_partial_credit_for_triage():
    # got one of two facts right -> not exact, but a soft overlap for ranking near-misses (and a
    # `missing` list that says exactly what to generate more training data for).
    g = slm.grade("alice is a customer", gold="alice is a customer\nbob is a customer")
    assert not g.exact
    assert g.missing == ("bob is_a customer",) and g.extra == ()
    assert 0.0 < g.overlap < 1.0
