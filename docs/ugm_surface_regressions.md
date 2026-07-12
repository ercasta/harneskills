# UGM bug / feature requests — CNL surface regressions found during the harneskills carve-out

> **From:** harneskills (a UGM consumer). **Date:** 2026-07-12. **Against:** `ugm` @ `08cc3c8`
> ("updated demos"). **How found:** rebuilding the harness onto UGM's new Session layer
> (`ugm/intake.py`) after the repo split. Two CNL surfaces the harness (and its NL→CNL SLM) depend
> on no longer produce facts / no longer derive through the `ingest` / `load_corpus` path.
>
> Both repros are **UGM-only** (no harneskills import) — run them so `import ugm` resolves the
> installed package (e.g. from a neutral working directory, not with the cwd set *inside* the repo
> root, where a stale `__pycache__` shadowed `wire_same_as` in our runs — an env quirk, not the bug).
> Both were verified against the source at `C:\Users\ercas\creazioni\ugm\ugm`. Neither is
> a harness wiring issue: the harness was confirmed to pass the *same* utterances straight to the
> UGM entry points. These are reported as regressions because the SLM baseline already trains on
> both surfaces (`multiword_def`, `universal`); they are not new asks.

---

## Issue 1 — determiner / multiword-NP normalization is not on the intake path

**Severity:** high (blocks the `the <adj> <noun> is a <type>` surface entirely).

**Summary.** `ingest` / `load_facts` / `load_corpus` no longer strip a leading determiner or
decompose a multiword noun phrase, so a sentence with `the` (or `the bald eagle`) recognizes to raw
surface tokens and produces **no content fact**. `normalize_surface` still exists in
`ugm/cnl/forms.py` and is invoked elsewhere (`authoring.py` ~L915–924, in a different function), but
it is **not wired into `_recognize` / `load_facts`**, which is the path `ingest` and `load_corpus` use.

**Repro (ugm-only):**

```python
import ugm
kb, rules = ugm.load_corpus("the eagle is a bird")
# Expected: an `eagle is_a bird` fact (determiner stripped).
# Actual: no is_a relation; raw token chain `the -> next -> eagle -> next -> is -> ...`
for n in kb.nodes():
    for r, o in kb.relations_from(n):
        print(kb.name(n), kb.predicate(r), kb.name(o))
```

Actual output has **no `is_a`** edge from `eagle` to `bird`; the sentence also spuriously produces a
`<use>` loose annotation. `"the bald eagle is a bird"` (determiner + NP decomposition to
`eagle is_a bird` + `eagle is bald`) likewise yields nothing.

**Expected:** determiner stripping + NP decomposition on the intake path, i.e. `the eagle is a bird`
→ `{eagle is_a bird}` and `the bald eagle is a bird` → `{eagle is_a bird, eagle is bald}` — the
behaviour `load_corpus` had before the intake rework.

**Impact on the consumer.** Breaks the harness SLM's `multiword_def` construct
(`the {adj} {e} is a {n}`) and any human/NL input that uses articles — i.e. most natural phrasing.

**Suggested fix / pointer.** Re-wire `normalize_surface` (with `surface_forms(form_keywords(forms))`,
as at `authoring.py` ~L915–924) into `_recognize` / `load_facts` so the intake path normalizes surface
before content recognition, matching the standalone helper that still does it.

---

## Issue 2 — `every X is a Y` recognizes but no longer derives

**Severity:** medium (the universal-law surface parses but is inert).

**Summary.** `every person is a mortal` recognizes to a `person every_is_a mortal` fact, but asking a
consequence of the law returns **`no`**, not `yes` — nothing turns the `every_is_a` fact into a
derivation that `ask_goal` / `ingest` consult. (UGM's own demos use the `HEAD when` variable-rule form
instead, so this surface appears to have been left behind rather than deliberately removed.)

**Repro (ugm-only):**

```python
import ugm
kb, rules = ugm.load_corpus("paul is a person\nevery person is a mortal")
print(ugm.ingest(kb, rules, "is paul a mortal").answer)   # -> ['no']   (expected ['yes'])
print(ugm.ingest(kb, rules, "who is a mortal").answer)    # -> ['(no answer)']  (expected paul)
```

`load_corpus`'s returned `rules` bundle (`expand_rules + expand_loose_from_graph +
same_name_coref_rules + _coref_propagation`) does not include a universal-derivation rule for
`every_is_a`, and `ask_goal` finds none, so the closed-world default answers `no`.

**Expected:** the universal law derives: `is paul a mortal` → `yes`, `who is a mortal` → `paul`.

**Impact on the consumer.** Breaks the harness SLM's `universal` construct (`every {n} is a {m}`) as a
*reasoning* surface. (As a bare fact it still lands, so `frame_graph` sees `person every_is_a mortal`;
the failure is that no downstream reasoning uses it.)

**Suggested fix / options.**
- (a) Ship a small `UNIVERSAL_RULES`-style derivation (`?x is_a ?m` from `?x is_a ?n` +
  `?n every_is_a ?m`) that `load_corpus` includes in its returned `rules`, so `ask_goal` applies it; or
- (b) if `every X is a Y` is intentionally deprecated in favour of `HEAD when`, say so — the consumer
  will migrate the surface and its SLM constructs, and the recognizer should ideally stop minting a
  dead `every_is_a` fact (or document it as fact-only, non-deriving).

---

## Notes for triage

- Neither issue is a harneskills-side problem: both repros use only `ugm`. The harness `Session` now
  passes utterances straight to `ingest` with the `load_corpus`-style rule bundle.
- A third change (relation **name-demotion** — `graph.name(r)` is now `''`, predicate via
  `graph.predicate(r)`) was NOT a bug; the harness adapted its readers. Mentioned only so the two
  issues above aren't conflated with it.
- Consumer-side tracking: `docs/handoff_slm_surface_track.md` (⚠ REGRESSIONS table) and
  `docs/implementation_plan.md` (Layer-2 item 3).
