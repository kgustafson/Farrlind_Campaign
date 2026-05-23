# Farrlind Local Model Evaluation

This folder holds the prompt and manifest for comparing local Ollama models against Farrlind session transcripts.

The goal is to reduce human review work by testing whether local models can turn noisy transcripts into useful canon review packets.

## Models

The active run-off uses the Gemma models. Qwen models were dropped after early rounds showed much slower runtime without a quality win.

- `gemma3:latest`
- `gemma4:e2b`
- `gemma4:e4b`

Optional stretch candidate:

- `gemma4:26b`

## Prompt

The current starting prompt is:

```text
model_eval/prompts/prompt_v03_synthesis.md
```

The v3 workflow uses chunked extraction:

- `model_eval/prompts/prompt_v03_chunk.md` extracts canon facts from transcript chunks.
- `model_eval/prompts/prompt_v03_synthesis.md` merges chunk extracts into the final canon packet.

`prompt_v01.md` and `prompt_v02.md` are preserved for baseline comparison.

## Run Commands

Smoke test one model with a short transcript slice:

```bash
./rag-env/bin/python scripts/model_eval_run.py --model gemma4:e2b --session session21 --limit-chars 3000 --chunk-size 1200 --chunk-overlap 150
```

Run all models against Session 21 with the default chunked v3 workflow:

```bash
./rag-env/bin/python scripts/model_eval_run.py --session session21
```

Run every configured model against every configured session:

```bash
./rag-env/bin/python scripts/model_eval_run.py
```

Full runs may take a long time. Generated outputs are written under `model_eval/runs/` and are ignored by git.

Chunked runs write intermediate extracts under:

```text
model_eval/runs/<model>/<prompt>/session##_chunks/
```

Run an older single-pass prompt for comparison:

```bash
./rag-env/bin/python scripts/model_eval_run.py --strategy single --prompt model_eval/prompts/prompt_v02.md --session session21
```
