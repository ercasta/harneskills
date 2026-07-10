"""
SLM training-data generator (harneskills/slm_data.py) — validates the in-env half of the fine-tuning
pipeline BEFORE any Colab time is spent, so a bad gold target or a broken copy-through split is caught
here, not after training. All checks go through the real parser (`slm`), so they assert the data is
actually learnable and gradable.
"""
from harneskills import slm, slm_data


def test_every_gold_cnl_parses_to_its_stored_frame():
    # the training TARGET must be valid CNL that denotes exactly the stored frame — else the model
    # would be trained toward, or graded against, garbage.
    for row in slm_data.generate(12):
        assert row["frame"], f"empty gold frame: {row}"
        assert sorted(slm.frame_graph(row["cnl"])) == row["frame"]


def test_nl_and_cnl_differ_so_it_is_a_real_translation():
    # at least most examples are genuine paraphrases (NL != CNL), i.e. the model learns a mapping,
    # not the identity. (A few identity variants are allowed and fine.)
    rows = slm_data.generate(12)
    paraphrases = [r for r in rows if r["nl"] != r["cnl"]]
    assert len(paraphrases) > len(rows) // 2


def test_all_constructs_are_covered():
    names = {r["construct"] for r in slm_data.generate(4)}
    assert names == {c["name"] for c in slm_data.CONSTRUCTS}


def test_multiword_construct_preserves_two_fact_structure():
    # the definite multi-word construct must decompose to attribute + type (the structure the model
    # has to reproduce), not collapse to one fact: `the {adj} {e} is a {n}` -> {`{e} is {adj}`,
    # `{e} is_a {n}`}.
    rows = [r for r in slm_data.generate(6) if r["construct"] == "multiword_def"]
    assert rows and all(len(r["frame"]) == 2 for r in rows)
    for r in rows:
        preds = {f.split()[1] for f in r["frame"]}     # the predicate of each of the two facts
        assert preds == {"is", "is_a"}                  # one attribute fact + one type fact


def test_eval_vocab_is_disjoint_from_train_vocab():
    # copy-through is only tested if the eval tokens were NEVER seen in training — otherwise a correct
    # prediction could be memorization, not verbatim copying of a novel token.
    for cat in ("entity", "noun", "adj"):
        assert not (set(slm_data.TRAIN_VOCAB[cat]) & set(slm_data.EVAL_VOCAB[cat]))


def test_eval_examples_use_only_novel_tokens():
    # every eval example's gold CNL is built from held-out vocab -> grading it exercises copy-through.
    train_tokens = {t for pool in slm_data.TRAIN_VOCAB.values() for t in pool}
    for row in slm_data.generate(8, vocab=slm_data.EVAL_VOCAB):
        cnl_tokens = set(row["cnl"].replace(" is a ", " ").replace(" is ", " ").split())
        # the content fillers in the eval CNL are novel (function words like 'the'/'every' aside)
        content = cnl_tokens - {"the", "every", "a", "is"}
        assert content and not (content & train_tokens)


def test_generation_is_deterministic():
    assert slm_data.generate(10) == slm_data.generate(10)   # reproducible corpus (no randomness)


def test_vocab_is_large_and_varied_for_copy_through():
    # the first fine-tune failed by SUBSTITUTING a training token for a novel one, because only ~12
    # tokens/category let the model memorize rather than learn "copy the slot". A large pool with many
    # distinct tokens exercised across the corpus is the fix — pin it so it can't silently shrink.
    assert all(len(slm_data.TRAIN_VOCAB[c]) >= 150 for c in ("entity", "noun", "adj"))
    distinct = set()
    for r in slm_data.generate(150):
        distinct |= {w for w in r["cnl"].split() if w not in {"the", "every", "a", "is"}}
    assert len(distinct) >= 300           # hundreds of distinct fillers, not a dozen memorizable ones


def test_train_and_eval_vocab_share_structure_no_spurious_regularity():
    # REGRESSION for the 79% fine-tune bug: a contiguous slice of the coda-sorted pool made EVERY
    # train noun end `b` and every eval noun end `g`, so the model learned "nouns end in b" and rewrote
    # eval tokens instead of copying. The bug was a MONOCULTURE — guard it: each train category must
    # have many distinct final characters AND no single ending may dominate. Then no "tokens end in X"
    # rule is learnable and the model must copy. (Eval having a couple endings train lacks is fine —
    # the model has no prior on those, so it still must copy them verbatim.)
    from collections import Counter
    for cat in ("entity", "noun", "adj"):
        endings = Counter(t[-1] for t in slm_data.TRAIN_VOCAB[cat])
        assert len(endings) >= 6, f"{cat}: too few distinct endings {dict(endings)}"
        top = max(endings.values()) / sum(endings.values())
        assert top < 0.4, f"{cat}: ending {endings.most_common(1)} dominates ({top:.0%}) — monoculture"
