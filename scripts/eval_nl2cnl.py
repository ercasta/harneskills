r"""
Evaluate a saved NL->CNL LoRA adapter with the REAL frame-graph reward, and DUMP every failure — no
retraining (loads the adapter from `scripts/finetune_nl2cnl.py`). Run on the GPU box (Colab) AFTER
installing harneskills so the frame-graph metric is available:

    !pip install -q -e ./harneskills            # so `import harneskills` works -> frame-graph grade
    !python harneskills/scripts/eval_nl2cnl.py --data-dir /content --adapter nl2cnl-lora

Frame-graph match (parse(pred) == parse(gold)) is the honest metric: it CREDITS a semantically-correct
prediction whose surface differs from gold (which plain string-match wrongly counts as a miss), and it
REJECTS a confidently-wrong one that parses to a different frame. The failure dump shows exactly which
frame facts are missing/extra, so a real error is distinguishable from a mere surface variant.
"""
from __future__ import annotations

import argparse
import json

PROMPT = "Translate the sentence into CNL.\n\nSentence: {nl}\nCNL:"


def _read_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _extract_cnl(generated: str) -> str:
    tail = generated.rsplit("CNL:", 1)[-1]
    return tail.strip().splitlines()[0].strip() if tail.strip() else ""


def main(args) -> None:
    from unsloth import FastLanguageModel
    from harneskills import slm

    model, tok = FastLanguageModel.from_pretrained(
        model_name=args.adapter, max_seq_length=256, load_in_4bit=True, dtype=None)
    FastLanguageModel.for_inference(model)

    rows = _read_jsonl(f"{args.data_dir}/eval.jsonl")
    by_construct: dict[str, list[bool]] = {}
    failures: list[dict] = []
    for r in rows:
        ids = tok(PROMPT.format(nl=r["nl"]), return_tensors="pt").to(model.device)
        out = tok.decode(model.generate(**ids, max_new_tokens=32, do_sample=False)[0],
                         skip_special_tokens=True)
        pred = _extract_cnl(out)
        g = slm.grade(pred, r["cnl"])                 # FRAME-GRAPH match, the real reward
        by_construct.setdefault(r["construct"], []).append(g.exact)
        if not g.exact:
            failures.append({"construct": r["construct"], "nl": r["nl"], "pred": pred,
                             "gold": r["cnl"], "missing": g.missing, "extra": g.extra,
                             "parsed": g.parsed})

    print("\n=== FRAME-GRAPH match on held-out NOVEL vocab (copy-through) ===")
    allv = [v for vs in by_construct.values() for v in vs]
    for name, vs in sorted(by_construct.items()):
        print(f"  {name:16s} {sum(vs)}/{len(vs)}  ({sum(vs) / len(vs):.0%})")
    print(f"  {'OVERALL':16s} {sum(allv)}/{len(allv)}  ({sum(allv) / len(allv):.0%})")

    if failures:
        print(f"\n=== {len(failures)} FAILURE(S) — is it a real error or a surface variant? ===")
        for f in failures:
            tag = "UNPARSEABLE" if not f["parsed"] else "wrong-frame"
            print(f"\n[{f['construct']}] ({tag})")
            print(f"  NL   : {f['nl']!r}")
            print(f"  pred : {f['pred']!r}")
            print(f"  gold : {f['gold']!r}")
            print(f"  missing={list(f['missing'])}  extra={list(f['extra'])}")
    else:
        print("\nno failures — 100% frame-graph match.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Eval a saved NL->CNL LoRA with the frame-graph reward.")
    p.add_argument("--data-dir", default=".")
    p.add_argument("--adapter", default="nl2cnl-lora")
    main(p.parse_args())
