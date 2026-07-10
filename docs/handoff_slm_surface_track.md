# Handoff — SLM NL→CNL surface-coverage track (retrain ledger)

> A dedicated, LONG-LIVED coordination track for parallel work. Parent plan:
> `docs/implementation_plan.md`. Philosophy: `docs/vision.md` + `docs/vision_agentic.md` §9
> (the SLM front-end). Unlike the other handoffs, this file is a RUNNING LEDGER by design —
> its whole job is to accumulate, across parallel sessions, the CNL surface that the NL→CNL
> SLM front-end does not yet cover, so a single retrain session can sweep them all up.

## Why this track exists

The system's front door for humans is an SLM that translates natural language → CNL
(`vision_agentic.md` §9; harness `harneskills/slm.py` reward + `harneskills/slm_data.py`
generator; off-box QLoRA fine-tune `scripts/finetune_nl2cnl.py`; validated on Colab at
95–98% held-out frame-graph). The model only learns the CNL surfaces present in the training
generator's `CONSTRUCTS`. **Every time a session adds a NEW authored CNL surface** (a new form,
a new sentence shape, a new keyword), the SLM cannot yet emit it — the surface is reachable by a
human typing exact CNL, but not by the NL front-end. So new surface accrues a DEBT that a
retrain pays off.

Rather than retrain per-surface (expensive, and the fine-tune is off-box / user-run), we let
surface debt accumulate here and retrain in ONE batch when enough has landed. This lets parallel
sessions each add surface freely without blocking on the model — they just register the surface
below.

## Protocol (for every session that adds CNL surface)

When your session adds or changes an authored CNL surface (a new `*_FORMS` bank, a new sentence
shape, a new keyword/lexicon entry that a human would type), do THREE cheap things:

1. **Append a row** to the ledger below: date, the surface, an example `NL-ish → CNL → edge/frame`,
   the module/forms that implement it, and the SLM-coverage status (`NOT COVERED` unless you also
   added a `CONSTRUCTS` entry).
2. If the surface is fact-shaped (parses to a non-empty frame), it is a candidate for a
   `slm_data.CONSTRUCTS` entry — a CNL template + 4–6 NL paraphrases. Adding that entry is what a
   retrain will consume. You do NOT have to add it now (that is the retrain session's job), but note
   whether it is fact-shaped (SLM-trainable) or control/machinery (out of the front-end's scope).
3. Leave the retrain itself to a dedicated SLM session (it is GPU-gated / user-run on Colab).

A retrain session then: reads the `NOT COVERED` rows, writes a `CONSTRUCTS` entry per trainable
surface (with disjoint eval vocab so a correct eval prediction proves copy-through, per
`slm_data.py`), regenerates data, runs the fine-tune, reads the per-construct frame-match report,
and flips the rows to `COVERED (retrain <date>)`.

## Scope — what is SLM-trainable vs not

- **SLM-trainable = FACT-shaped surface**: a line a human asserts that parses to a non-empty frame
  (typed facts, attributes, universals, relations, and — new — planning operators/state/goal, which
  lower to plain relation edges). These want a `CONSTRUCTS` entry.
- **NOT front-end scope = CONTROL / MACHINERY surface**: machine-rule CNL (`corpus/planning.cnl`,
  walker/teardown banks), rule-authoring grammar itself. These are authored by the system/developer,
  not spoken in NL by an end user, so the SLM need not learn them. Register them here anyway (as
  `N/A — machinery`) so the picture is complete, but they do not gate a retrain.

## Currently COVERED by the SLM generator (baseline — `slm_data.CONSTRUCTS`, 4 constructs)

| Construct | Gold CNL template | Notes |
|---|---|---|
| `typed_fact` | `{e} is a {n}` | is_a facts |
| `attribute` | `{e} is {adj}` | gradable/attribute copula |
| `multiword_def` | `the {adj} {e} is a {n}` | determiner + NP decomposition |
| `universal` | `every {n} is a {m}` | universal law |

Residual known misses inside these are a synthetic artifact (nonsense-token depluralization), not
worth chasing — see `CHANGELOG` "SLM PILLAR DONE" (arc history in `attic/handoff_redesign.md`).

## Ledger — NEW surface awaiting front-end coverage

> Append newest-last. Status ∈ {`NOT COVERED`, `COVERED (retrain <date>)`, `N/A — machinery`}.

| Date | Surface | Example (NL-ish → CNL → edge/frame) | Implemented in | Status |
|---|---|---|---|---|
| 2026-07-06 | **Planning operator / state / goal** (fact-shaped) | "make_coffee needs water" → `make_coffee needs water` → `make_coffee --pre--> water`; "we want coffee" → `we want have_coffee` → `<goal> --want--> have_coffee`. Keywords: `needs`/`produces`/`removes`/`costs`/`is priced`/`we have`/`we want`. | `harneskills/planning_kb.py` (`PLANNING_KB_FORMS`, `load_planning_kb`); doc `docs/operator_goal_cnl.md`; corpus `corpus/coffee_kb.cnl` | NOT COVERED — trainable; 7 candidate CONSTRUCTS (one per keyword). Names are single-token identifiers (underscored), so NL paraphrases should keep the identifiers verbatim (copy-through) and vary only the verb/framing (e.g. "brewing needs water", "to get coffee you need water"). |
| 2026-07-06 | **Procedure declaration** (fact-shaped; PRE-EXISTING form `procedure.PROCEDURE_FORMS`, now exposed in the planning-KB CNL + TUI) | "to brew, get water then add beans then heat" → `to brew get_water then add_beans then heat` → `brew --is_a--> procedure` + a `before`-chain over the step nodes. Keyword: leading `to` + `then`-chain. | `harneskills/procedure.py` (`PROCEDURE_FORMS`, `parse_procedures`); folded into the mixed-KB loader `harneskills/planning_kb.py` (`load_planning_program`); corpus `corpus/barista_kb.cnl`; TUI `/do NAME` | NOT COVERED — trainable; 1 candidate CONSTRUCT. Variadic step list (2+ steps). Single-token underscored step/procedure names → copy identifiers verbatim; vary framing ("to make tea, boil water then steep"). Pairs naturally with the planning operator constructs above (same retrain batch). |

## When to trigger a retrain

Judgment call, not a hard threshold: retrain when the `NOT COVERED` rows represent surface a real
user would speak (e.g. once the planning surface is something the TUI exposes to NL input), or when
several trainable surfaces have accumulated and a single sweep is economical. The fine-tune is
cheap on a T4 (0.5–1B QLoRA); the cost is the human-in-the-loop Colab run, so batching wins.

## Pointers

- SLM harness + reward: `harneskills/slm.py`; data generator: `harneskills/slm_data.py`
  (`CONSTRUCTS`); off-box fine-tune: `scripts/finetune_nl2cnl.py`.
- Surface authoring conventions: `docs/kb_authoring_guide.md`, `docs/logic_fragment.md`
  (§Authoring — the fragment forms), `harneskills/authoring.py` (`FACT_FORMS`,
  `BODY_SPINE_FORMS`), `harneskills/forms.py`.
- Parent plan: `docs/implementation_plan.md`. History: `docs/CHANGELOG.md`.
