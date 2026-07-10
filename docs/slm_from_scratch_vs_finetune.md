# Design discussion — training the NL→CNL model from scratch vs. fine-tuning

> Captured 2026-07-06. A reasoning record, not a spec. Companion to the SLM front-end:
> `docs/vision_agentic.md` §9, `harneskills/slm.py` (reward/grade), `harneskills/slm_data.py`
> (data generator), `scripts/finetune_nl2cnl.py` (off-box fine-tune), and the running surface
> ledger `docs/handoff_slm_surface_track.md`.

## The question

Given the SLM is used ONLY to translate natural language → CNL (the substrate does all reasoning),
two sub-questions:

1. Is training a language model **from scratch** for this task feasible, and how would we estimate
   the required model size?
2. Is from-scratch **worth the effort** versus fine-tuning a small pretrained model?

## Framing — what actually makes this task small

The current design already strips the hard part out of the model's job
(`slm_data.py:8-12`): **vocabulary is externalized to the KB.** An unknown word is a KB failure,
not a model failure, so the model learns only:

- **structure** — which surface span maps to which CNL slot, and
- **copy-through** — carry an unrecognized token VERBATIM into its slot
  (tested by a train/eval **disjoint** vocab so a correct eval prediction *requires* copying a
  never-seen token, `slm_data.py:14-17`, `TRAIN_VOCAB`/`EVAL_VOCAB`).

That reframes the task away from "language modeling" (needs pretraining for world/lexical priors)
toward **structured transduction over a controlled target language** — the semantic-parsing family
(SCAN, COGS, controlled-language MT), where small models trained from scratch reach ceiling.

Two additional properties push it toward feasible:

- We own the parser, so we have a **free, exact, automatic grader** (`slm.grade`, frame-graph
  match) and an **infinite, perfectly-labeled generator** (`slm_data.generate`). Pretraining exists
  mostly to compensate for data scarcity + missing priors — we have neither problem on the *output*
  side.
- Copy-through is a cheap pointer/attention primitive; a byte/char-level tokenizer makes it native
  (no OOV, no relearning subwords for nonsense fillers).

Corroboration from our own runs: the first *fine-tune* hit ~98%, failing only on `universal`, and
both misses were copy-through (substituted a training token for an unseen one), fixed by enlarging
the nonsense vocab. The task is already nearly solved by a small model.

## Sizing — the axis that actually binds

The **output** (CNL) side does not drive size: it is a small formal language (currently 4
constructs). The binding axis is **input-side natural-language variety** — how messy the human
phrasings we intend to *accept* are. So the size question is really "how much surface variation must
the encoder absorb?"

### How to estimate size (empirically — we own the grader)

1. **Capacity floor (MDL sanity check).** The transduction is ~a finite-state/CFG transducer; its
   description length ≈ (productions × constructs × slot-routing decisions) × bits. It is tiny —
   confirms the output side is not the constraint.
2. **Scaling sweep (the real answer).** Train encoder-decoder from scratch at {1M, 3M, 10M, 30M}
   params on generated data; plot held-out frame-graph exact-match. The knee where accuracy
   saturates *is* the required size. A few GPU-hours.
3. **Ablate the two axes separately.** (a) fix paraphrases, grow constructs → output-structure
   capacity (expected cheap/flat); (b) fix constructs, grow paraphrase diversity → input-encoding
   capacity (expected to dominate).

**Prior on the outcome:** for the current grammar, ~1–10M params (char/byte-level + explicit
pointer/copy) likely hits ceiling; at full grammar maturity with wide NL tolerance, low tens of
millions. Both are single-GPU, hours-not-days.

## Recursion changes the *character* of the estimate (subordinate / coordinate clauses)

As the grammar grows to coordination and subordination, the task leaves the finite-template regime
and becomes **recursive / compositional**. This is a qualitative shift, not just "more constructs."

- **Coordination** (`X is a foo and Y is a bar`) mostly decomposes into *independent* frames →
  segmentation + per-segment transduction. Cheap; length-generalizes reasonably. Small added
  capacity.
- **Subordination / embedding** (`the foo that is bar is a baz`; complement clauses `I know that X
  is Y`; relatives that rebind the matrix subject) is **genuine recursion** — unbounded nesting, and
  the inner clause can change the outer denotation. This is the axis that breaks small transducers.

Key correction: **recursion does not blow up parameter count** (a recursion/stack routine is a
compact program). It **moves the binding constraint off size and onto compositional
generalization** — the documented failure mode of from-scratch transformers (SCAN, COGS, CFQ:
ceiling in-distribution, collapse on longer/deeper/novel-combination inputs). Critically, **bigger
does not reliably fix it**; it correlates with data distribution + architectural inductive bias, not
raw size.

### New eval axes required (the current disjoint-vocab split does NOT probe these)

The `TRAIN_VOCAB`/`EVAL_VOCAB` split tests a *lexical* axis (copy-through). Recursion needs
*structural* held-outs:

1. **Depth extrapolation** — train ≤2 nesting levels, eval 3–4.
2. **Coordination-arity extrapolation** — train ≤3 conjuncts, eval 5–6.
3. **Novel combination** (COGS-style) — constructs seen separately, first combined at eval.

Our frame-graph grader gives **exact structural credit on novel compositions**, so these are
directly measurable. The honest deliverable becomes a **two-dimensional frontier** (model size ×
max-train-depth, measuring *extrapolation*), not a single-length point estimate.

### Highest-leverage move: exploit that we own the grammar

Because the CNL target is a formal language with a parser we control, we can bias the whole thing so
a *small* model handles recursion reliably:

- **Grammar-constrained / structured decoding** against the CNL grammar (choose only among valid
  continuations) — offloads recursive structure onto the decoder constraint. Highest single lever
  for "small AND compositional."
- **Decode to the frame/tree, not the surface string** — target the structured denotation directly;
  surface CNL is a deterministic render.
- **Depth curriculum** — the generator can synthesize controlled-depth data.

## Verdict — is from-scratch worth it?

**Not as the primary path (yet). Fine-tune a small pretrained model as production; treat
from-scratch as a cheap experiment that must earn its way in.**

Reasoning:

- The cost of from-scratch is **not compute** (hours) — it is **owning the compositional
  generalization problem in perpetuity.** Every grammar expansion forces regenerate-data +
  re-sweep + re-establish extrapolation from the synthetic corpus alone. The generalization ceiling
  *is* the paraphrase generator's coverage.
- Pretraining is a **bought solution** to exactly that problem, strongest where the roadmap heads
  (NL-input variety + recursion). And the fine-tune is already validated (~98%).
- The deciding variable is **how much unseen NL-input variety must be accepted**:
  - constrained/regular dictation → from-scratch's ownership + tiny footprint become worth it;
  - messy arbitrary phrasing → priors are the whole game, from-scratch is fighting the long tail.

Recommended sequencing: (1) ship fine-tuned-pretrained now; (2) run the size × depth from-scratch
sweep as a one-time experiment against `slm.grade`; (3) adopt from-scratch only if the gap is small
AND input phrasing is constrained. Otherwise a few GPU-hours *proves* it is not worth it — a good
outcome.

## Caveat that survived challenge — catastrophic forgetting taxes BOTH paths

Correction to an over-strong earlier claim ("pretraining makes variety free"): fine-tuning hard on a
narrow synthetic distribution (few constructs, nonsense fillers) can **catastrophically forget** the
input-side priors we are paying for. So **both paths need a diverse corpus.** The asymmetry is in
*kind*, not just degree:

- **From-scratch** needs **coverage-scale** variety — its input robustness *is* the corpus, tail
  included.
- **Fine-tuned** needs **preservation-scale** variety — enough to teach the mapping and regularize
  against drift; the frozen priors cover the tail we do not generate. (Preserving competence takes
  less data than manufacturing it — but not zero.)

The lever from-scratch structurally lacks:

- **PEFT (LoRA/adapters)** — freeze the base, train a small delta; you cannot forget what you do not
  update. No from-scratch analog.
- **Freeze the encoder, tune decoder/cross-attention** — preserve exactly the phrase-understanding
  we want to keep while the decoder specializes to CNL.
- **Rehearsal** — mix a thin slice of general text into the fine-tune.

And forgetting the *irrelevant* is fine (we only need NL→CNL). The risk collapses to "did we
preserve phrase-understanding," which freezing/LoRA directly tunes.

**Actionable that falls out of this:** an in-distribution eval **cannot detect forgetting.** Budget
for an **OOD diverse-phrasing probe** (real-ish human phrasings outside the template generator) as a
*forgetting monitor*, distinct from the "did we learn the task" probe. It also measures how much
preservation-scale variety is *enough*, and it sets the freeze/LoRA knob (freeze too much → underfit
task; tune too much → forget). This cost is **common to both paths** — not unique to from-scratch.

## Concrete next step (if pursued)

Extend `slm_data.CONSTRUCTS` with a coordination construct + one embedding construct, add the three
compositional eval splits (depth / arity / novel-combination) to `slm_data.py`, and run the
size × max-train-depth sweep against `slm.grade`. Building the **compositional eval splits first** is
what makes every later size/worth-it claim empirical rather than argued.
