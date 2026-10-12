# QLoRA fine-tune (designed, not built)

This is the stretch goal from the plan. It was deliberately left until the core system was
finished and evaluated, and it has not been implemented. This note records the design so the
work can be picked up later.

## Why

PrismRAG's actual contribution is a fine-tuning recipe: train the generator on examples that
mix the gold passage with realistic distractors, with a reasoned answer as the target. This
project only borrows the prompt shape (plan, evidence check, answer). A fine-tune would teach a
small local model the same behaviour so it does not depend on a hosted LLM.

## Plan

1. **Data** (`make_dataset.py`): for each question, one gold chunk plus 2 to 3 distractor chunks
   taken from the near-miss document (2024 vs 2025 handbook, Orbit A1 vs B2). The target is the
   same JSON the API already expects. About a third of the samples are unanswerable and target
   `INSUFFICIENT_CONTEXT`.
2. **Model**: Qwen2.5-1.5B-Instruct or Llama-3.2-3B-Instruct.
3. **Training** (`train_qlora.ipynb`): `peft` + `bitsandbytes` 4-bit, LoRA r=16, 1 to 2 epochs on
   a free Colab T4.
4. **Integration**: a `FineTunedLLM` class implementing `app.generation.llm_base.LLM`, selected
   with `LLM_PROVIDER=finetuned`. Nothing else in the pipeline changes.
5. **Proof**: run `eval/run_eval.py` with the base model and the fine-tuned model and report both
   rows, including if the fine-tune is worse.

## Risk

The sample corpus is tiny, so a model trained on it would mostly memorise it. A fair test needs
training documents that are disjoint from the evaluation documents.
