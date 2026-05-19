# Farrlind Local Model Evaluation

This folder holds the prompt and manifest for comparing local Ollama models against Farrlind session transcripts.

The goal is to reduce human review work by testing whether local models can turn noisy transcripts into useful canon review packets.

## Models

The initial run-off uses:

- `gemma3:latest`
- `qwen3:8b`
- `qwen3:14b`
- `qwen2.5:14b`

## Prompt

The starting prompt is:

```text
model_eval/prompts/prompt_v01.md
```

It asks the model to produce a coherent session packet with summaries, locations, NPCs/entities, lore, resources, artifacts, open threads, and uncertainties.

## Run Commands

Smoke test one model with a short transcript slice:

```bash
./rag-env/bin/python scripts/model_eval_run.py --model gemma3:latest --session session21 --limit-chars 1000
```

Run all models against Session 21:

```bash
./rag-env/bin/python scripts/model_eval_run.py --session session21
```

Run every configured model against every configured session:

```bash
./rag-env/bin/python scripts/model_eval_run.py
```

Full runs may take a long time. Generated outputs are written under `model_eval/runs/` and are ignored by git.
