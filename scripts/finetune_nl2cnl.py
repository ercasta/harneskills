r"""
Fine-tune a small model for NL -> CNL translation (docs/vision_agentic.md §9). OFF-BOX: run this on a
GPU (a free Colab / Kaggle T4 is plenty for a 0.5-1B model with QLoRA — the discussion's sizing). It
is NOT run by the test suite; the IN-ENV, tested half is `harneskills/slm_data.py` (the data) and
`harneskills/slm.py` (the exact frame-graph reward this script grades with).

WHY THIS IS THE TRACTABLE PIECE: NL -> CNL is closed-target translation, not open generation. With
vocabulary stripped from the model's job (an unknown word is a KB failure — `slm_data` fills with
nonsense tokens and holds out a DISJOINT eval vocab), the model only has to learn STRUCTURE + verbatim
COPY-THROUGH of novel tokens. That is a narrow task small models do well after fine-tuning.

WHAT SUCCESS LOOKS LIKE, AND WHY THE METRIC IS HONEST: we grade with `slm.grade` — parse the model's
CNL and compare its FRAME GRAPH to gold. This catches the confidently-wrong translation (valid CNL,
different meaning) that string-match or a loss curve would miss, and the held-out eval vocab makes a
correct answer PROVE copy-through, not memorization. Report exact-frame-match overall and per
construct; the interesting number is the eval (novel-vocab) rate vs. the train-vocab rate.

------------------------------------------------------------------------------------------------------
COLAB SETUP (paste into a cell, GPU runtime):
    !pip install -q unsloth trl peft bitsandbytes accelerate datasets
    !git clone <this repo> && pip install -q -e ./harneskills        # so `import harneskills` works
    !python -m harneskills.slm_data /content                          # writes train.jsonl + eval.jsonl
    !python harneskills/scripts/finetune_nl2cnl.py --data-dir /content --model unsloth/Qwen2.5-0.5B
Then read the per-construct frame-match report it prints.

Optional (removes a whole error class): GRAMMAR-CONSTRAINED DECODING so invalid CNL is unreachable at
generation time — build a GBNF/outlines grammar for the CNL construct set and decode under it. Not
wired here to keep the script dependency-light; the frame-graph metric already rejects invalid output.
------------------------------------------------------------------------------------------------------
"""
from __future__ import annotations

import argparse
import json

PROMPT = "Translate the sentence into CNL.\n\nSentence: {nl}\nCNL:"


def _format(row: dict, eos: str) -> str:
    """One SFT training string: the prompt followed by the gold CNL completion and EOS."""
    return PROMPT.format(nl=row["nl"]) + " " + row["cnl"] + eos


def _read_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _extract_cnl(generated: str) -> str:
    """Pull the CNL the model emitted after the final `CNL:` marker, first line only."""
    tail = generated.rsplit("CNL:", 1)[-1]
    return tail.strip().splitlines()[0].strip() if tail.strip() else ""


def train(args) -> None:
    from unsloth import FastLanguageModel      # imported here so the module loads without a GPU stack
    from trl import SFTConfig, SFTTrainer
    from datasets import Dataset

    model, tok = FastLanguageModel.from_pretrained(
        model_name=args.model, max_seq_length=256, load_in_4bit=True, dtype=None)
    model = FastLanguageModel.get_peft_model(
        model, r=16, lora_alpha=16, lora_dropout=0.0, bias="none",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        use_gradient_checkpointing="unsloth", random_state=0)

    eos = tok.eos_token or "</s>"
    train_rows = _read_jsonl(f"{args.data_dir}/train.jsonl")
    ds = Dataset.from_dict({"text": [_format(r, eos) for r in train_rows]})

    trainer = SFTTrainer(
        model=model, tokenizer=tok, train_dataset=ds,
        args=SFTConfig(
            dataset_text_field="text", max_seq_length=256,
            per_device_train_batch_size=8, gradient_accumulation_steps=2,
            warmup_steps=5, num_train_epochs=args.epochs, learning_rate=2e-4,
            logging_steps=10, optim="adamw_8bit", seed=0, output_dir=args.out,
            report_to="none"))
    trainer.train()

    FastLanguageModel.for_inference(model)
    _evaluate(model, tok, args)
    model.save_pretrained(args.out)
    tok.save_pretrained(args.out)
    print(f"\nsaved LoRA adapter to {args.out}")


def _evaluate(model, tok, args) -> None:
    """Generate on the held-out (novel-vocab) eval set and grade by FRAME-GRAPH match — the exact
    reward. Falls back to string equality if harneskills is not importable (but install it: the whole
    point is the frame-graph signal)."""
    try:
        from harneskills import slm
        grade = lambda pred, gold: slm.grade(pred, gold).exact
        metric = "frame-graph match"
    except Exception:
        grade = lambda pred, gold: pred.strip() == gold.strip()
        metric = "string match (INSTALL harneskills for the real frame-graph metric)"

    rows = _read_jsonl(f"{args.data_dir}/eval.jsonl")
    by_construct: dict[str, list[bool]] = {}
    for r in rows:
        prompt = PROMPT.format(nl=r["nl"])
        ids = tok(prompt, return_tensors="pt").to(model.device)
        out = tok.decode(model.generate(**ids, max_new_tokens=32, do_sample=False)[0],
                         skip_special_tokens=True)
        ok = grade(_extract_cnl(out), r["cnl"])
        by_construct.setdefault(r["construct"], []).append(ok)

    print(f"\n=== eval on held-out NOVEL vocab (copy-through), metric = {metric} ===")
    allv = [v for vs in by_construct.values() for v in vs]
    for name, vs in sorted(by_construct.items()):
        print(f"  {name:16s} {sum(vs)}/{len(vs)}  ({sum(vs) / len(vs):.0%})")
    print(f"  {'OVERALL':16s} {sum(allv)}/{len(allv)}  ({sum(allv) / len(allv):.0%})")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Fine-tune a small model for NL->CNL (QLoRA).")
    p.add_argument("--data-dir", default=".", help="dir with train.jsonl / eval.jsonl (from `python -m harneskills.slm_data`)")
    p.add_argument("--model", default="unsloth/Qwen2.5-0.5B", help="base model (0.5-1B fits a T4)")
    p.add_argument("--epochs", type=float, default=3.0)
    p.add_argument("--out", default="nl2cnl-lora")
    train(p.parse_args())
