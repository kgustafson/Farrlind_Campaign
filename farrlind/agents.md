# AGENTS.md — Farrlind Transcription Pipeline

## Core Architecture

This project is a deterministic worker pipeline, not a chat-agent system.

Use the term **worker** for focused processing units. Do not design autonomous “bots” unless explicitly requested.

The pipeline shape is:

audio file
→ split into overlapping chunks
→ transcribe chunks in parallel
→ stitch/reduce transcripts
→ validate transcript quality
→ normalize names/terms
→ classify segments
→ extract entities/events/rewards/travel/combat
→ generate summaries, Faban diary drafts, and Farrlind canon updates

## Design Rules

1. Prefer small, testable Python modules.
2. Each worker should take explicit inputs and produce explicit outputs.
3. Workers should be deterministic where possible.
4. Intermediate outputs should be saved to disk as JSON or Markdown.
5. Failed chunks should be retryable without rerunning the whole pipeline.
6. Do not hide state inside prompts.
7. Do not mix transcription, validation, classification, and writing in one function.
8. Use structured data between stages.

## Worker Definitions

### Split Worker
Input:
- source audio file

Output:
- chunk audio files
- chunk manifest JSON with start/end timestamps

### Transcription Worker
Input:
- one audio chunk
- chunk metadata

Output:
- transcript JSON containing:
  - chunk id
  - start timestamp
  - end timestamp
  - text
  - segment timestamps if available
  - model name
  - confidence/quality metadata if available

This worker may run in parallel using a worker pool.

### Stitch/Reduce Worker
Input:
- ordered transcript chunk JSON files

Output:
- stitched transcript Markdown
- stitched transcript JSON
- warnings for gaps, overlaps, duplicate lines, or missing chunks

Responsibilities:
- sort chunks by start time
- remove overlap duplication
- preserve timestamps
- detect missing or failed chunks

### Validation Worker
Input:
- stitched transcript

Output:
- validation report JSON/Markdown

Detect:
- likely Whisper hallucinations
- repeated loops
- empty or near-empty chunks
- abrupt topic discontinuities
- suspicious repeated phrases
- missing timestamp ranges

### Normalize Worker
Input:
- transcript
- project glossary/canon terms

Output:
- normalized transcript
- replacement report

Examples:
- Roon, not Rune
- Lightdelver, not Light Delver if canon says so
- Orsydon, not misheard variants

### Classification Worker
Input:
- normalized transcript

Output:
- classified segments JSON

Segment types:
- story
- combat
- travel
- NPC interaction
- location/lore
- reward/loot
- downtime
- planning
- unclear

### Extraction Workers

Separate workers should extract:

- key NPCs
- key places
- enemies
- rewards/items
- travel
- combat events
- lore/canon facts
- unresolved questions
- player character moments

Each extractor writes structured JSON.

### Summary Worker
Input:
- classified segments
- extraction outputs

Output:
- session summary Markdown
- structured session summary JSON

The summary must capture story, not just combat.

### Diary Worker
Input:
- session summary
- normalized transcript
- Faban style guidance

Output:
- Faban diary draft Markdown

This should be prose, not raw summary.

### Canon Worker
Input:
- extraction outputs
- current Farrlind canon files

Output:
- proposed canon updates only

Do not overwrite canon automatically unless explicitly asked.

## Parallelism Model

Use parallel workers for expensive independent tasks.

Good parallel targets:
- audio chunk transcription
- entity extraction by category
- segment classification by chunk
- validation checks

Do not parallelize steps that require ordered global context unless using a reduce step afterward.

Preferred model:

map:
- process chunks independently

reduce:
- stitch, merge, deduplicate, validate

## Directory Suggestions

```text
src/
  farrlind_pipeline/
    audio/
      split.py
      manifest.py
    transcription/
      transcribe_worker.py
      transcribe_parallel.py
      stitch.py
    validation/
      validate.py
    normalization/
      normalize.py
      glossary.py
    classification/
      classify.py
    extraction/
      npcs.py
      places.py
      rewards.py
      combat.py
      travel.py
      lore.py
    generation/
      summary.py
      diary.py
      canon.py
    pipeline/
      simple_runner.py
      graph_runner.py
    models/
      schemas.py

data/
  sessions/
  glossary/
  canon/
  outputs/