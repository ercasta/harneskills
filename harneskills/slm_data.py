"""
SLM NL->CNL training-data generator (docs/vision_agentic.md §9) — the in-env, testable half of the
fine-tuning pipeline. Produces (natural-language, gold-CNL) pairs to fine-tune a small model that
translates NL into CNL; the GPU training itself is `scripts/finetune_nl2cnl.py` (off-box).

Two design commitments from the discussion, both making the data cheap and the task narrow:

  - VOCABULARY IS STRIPPED FROM THE MODEL'S JOB. An unknown word is a KB failure, not a model
    failure, so the model only learns STRUCTURE (which surface span maps to which CNL slot) plus
    COPY-THROUGH (carry an unrecognized token verbatim into its slot). Therefore the fillers are
    NONSENSE tokens — the "colorless green ideas" separability of structural from lexical competence.
    Structure is what varies across examples; the specific nouns never matter.

  - COPY-THROUGH IS TESTED BY A DISJOINT EVAL VOCAB. `TRAIN_VOCAB` and `EVAL_VOCAB` share no tokens,
    so a correct eval prediction REQUIRES the model to copy a never-seen token into the right slot,
    not recall a memorized one. That is the specific behavior the vision says must be trained, and
    the held-out split is how we measure it.

Each example's gold CNL is VALIDATED here by parsing it through the real pipeline (`slm.frame_graph`):
a construct that did not parse to a non-empty frame would be an invalid training target, so the
generator refuses it. The frame is stored so the fine-tune eval can grade by FRAME-GRAPH match
(`slm.grade`), the exact reward — not brittle string equality.

Constructs are deliberately the ones that parse cleanly to a distinct frame today (typed fact,
attribute, multi-word definite decomposition, universal law). Negation and undeclared-relation
sentences currently yield an empty frame (no gold), so they are OUT until the NL-front-end gaps land
— extend `CONSTRUCTS` as the grammar grows.
"""
from __future__ import annotations

import json

from . import slm

# --- nonsense vocabulary: GENERATED, large, and train / eval DISJOINT ----------
#
# The first fine-tune (2026-07-04, 98%) failed only on `universal`, and BOTH misses were novel-token
# COPY-THROUGH failures: the model SUBSTITUTED a training token for an unseen one (`thorb`->`tronk`),
# and mangled a novel stem while depluralizing (`quanks`->`quen`). Root cause: only ~12 tokens per
# category, so the model over-anchored on them instead of learning "copy whatever is in the slot".
# The fix (the discussion's prescription) is a LARGE, varied nonsense vocabulary so copy-through
# becomes a learned rule, not memorization — generated deterministically (no randomness), with the
# eval slice disjoint from train so a correct eval prediction still proves verbatim copy of a
# never-seen token.
# CONSONANT-CLUSTER onsets only: no grammar-special word (is/a/an/the/every/all/any/each/not/and/
# does/did/was/has/…) begins with a cluster, so a generated token can never collide with one — no
# slow per-token parse-validation needed (each example's frame is still checked in `generate`).
_ONSET = ["br", "dr", "fl", "gl", "kr", "pl", "sn", "tr", "sk", "sw",
          "bl", "cl", "fr", "gr", "kl", "pr", "sl", "sp", "st", "tw"]
_NUC = ["a", "e", "i", "o", "u", "ar", "or", "en", "um", "ix"]
_CODA = ["", "b", "d", "g", "k", "l", "m", "n", "p", "t", "x", "sk", "nt", "rk", "mp"]


def _syllable(i: int) -> str:
    o = _ONSET[i % len(_ONSET)]
    n = _NUC[(i // len(_ONSET)) % len(_NUC)]
    c = _CODA[(i // (len(_ONSET) * len(_NUC))) % len(_CODA)]
    return o + n + c


def _pool(n_tokens: int = 780) -> list[str]:
    """A deterministic list of distinct cluster-onset nonsense tokens, DECORRELATED from structure.

    `_syllable` enumerates with the coda as the slowest index, so a contiguous slice would share a
    coda (the first fine-tune's 79% bug: every train noun ended `b`, every eval noun `g`, and the
    model learned the spurious regularity instead of copying). We therefore reorder by a multiplicative
    permutation (stride coprime to the pool size) so every train/eval slice draws the SAME mix of
    onsets/nuclei/codas — no learnable feature separates train from eval, so the only way to get an
    eval token right is to COPY it verbatim."""
    raw: list[str] = []
    s: set[str] = set()
    limit = len(_ONSET) * len(_NUC) * len(_CODA)
    for i in range(limit):
        t = _syllable(i)
        if len(t) >= 3 and t not in s:
            s.add(t)
            raw.append(t)
    n = len(raw)
    stride = 613                                     # prime, coprime to n -> a full permutation
    perm = [raw[(k * stride) % n] for k in range(n)]
    return perm[:n_tokens]


_POOL = _pool()
# disjoint slices -> disjoint category pools, and disjoint train / eval
TRAIN_VOCAB = {"entity": _POOL[0:200], "noun": _POOL[200:400], "adj": _POOL[400:600]}
EVAL_VOCAB = {"entity": _POOL[600:660], "noun": _POOL[660:720], "adj": _POOL[720:780]}

# slot letter -> vocabulary category
_SLOT_TYPE = {"e": "entity", "n": "noun", "m": "noun", "adj": "adj"}

# --- constructs: a CNL template + NL paraphrases that all map to its frame ------
# The NL side is the model INPUT (never parsed by us); the CNL side is the gold target (parsed to a
# frame for grading). NL variants are surface-different from the CNL so the model learns a real
# translation, not the identity.
CONSTRUCTS = [
    {
        "name": "typed_fact",
        "slots": ["e", "n"],
        "cnl": "{e} is a {n}",
        "nl": ["{e} is a {n}", "{e} is a kind of {n}", "{e}, a {n}",
               "you could call {e} a {n}", "{e} is basically a {n}",
               "{e} counts as a {n}"],
    },
    {
        "name": "attribute",
        "slots": ["e", "adj"],
        "cnl": "{e} is {adj}",
        "nl": ["{e} is {adj}", "{e} seems {adj}", "{e} appears {adj}",
               "{e} is definitely {adj}", "{e} looks {adj}"],
    },
    {
        "name": "multiword_def",
        "slots": ["adj", "e", "n"],
        "cnl": "the {adj} {e} is a {n}",
        "nl": ["the {adj} {e} is a {n}", "the {adj} {e} is a kind of {n}",
               "{e}, which is {adj}, is a {n}", "that {adj} {e} is a {n}"],
    },
    {
        "name": "universal",
        "slots": ["n", "m"],
        "cnl": "every {n} is a {m}",
        "nl": ["every {n} is a {m}", "all {n}s are {m}s", "each {n} is a {m}",
               "any {n} is a {m}", "{n}s are always {m}s"],
    },
]


def _fill(vocab: dict, slots: list[str], i: int) -> dict[str, str]:
    """Deterministic slot fills for example `i` (NO randomness — reproducible). Each slot draws from
    its category's pool offset by its position, so slots of the same category (e.g. universal's n/m)
    stay distinct."""
    out = {}
    for j, s in enumerate(slots):
        pool = vocab[_SLOT_TYPE[s]]
        out[s] = pool[(i + j) % len(pool)]
    return out


def generate(n_per_construct: int = 40, *, vocab: dict | None = None,
             constructs: list | None = None) -> list[dict]:
    """Generate validated (nl, cnl, frame, construct) examples. Every gold CNL is parsed through the
    real pipeline; a target that fails to yield a non-empty frame raises (an invalid construct, not a
    silent bad example)."""
    vocab = vocab or TRAIN_VOCAB
    constructs = constructs or CONSTRUCTS
    rows: list[dict] = []
    for c in constructs:
        for i in range(n_per_construct):
            fills = _fill(vocab, c["slots"], i)
            cnl = c["cnl"].format(**fills)
            nl = c["nl"][i % len(c["nl"])].format(**fills)
            frame = sorted(slm.frame_graph(cnl))
            if not frame:
                raise ValueError(f"construct {c['name']!r} produced no gold frame for {cnl!r}")
            rows.append({"construct": c["name"], "nl": nl, "cnl": cnl, "frame": frame})
    return rows


def write_jsonl(rows: list[dict], path: str) -> None:
    """Write examples as JSON-lines (the training input format)."""
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


if __name__ == "__main__":   # `python -m harneskills.slm_data <out_dir>` -> train.jsonl + eval.jsonl
    import sys

    out_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    train = generate(150, vocab=TRAIN_VOCAB)     # more examples -> more distinct tokens per slot seen
    ev = generate(20, vocab=EVAL_VOCAB)          # held-out NOVEL vocab -> copy-through generalization
    write_jsonl(train, f"{out_dir}/train.jsonl")
    write_jsonl(ev, f"{out_dir}/eval.jsonl")
    print(f"wrote {len(train)} train + {len(ev)} eval examples to {out_dir}/")
