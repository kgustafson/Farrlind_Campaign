# Session20 Transcription Benchmark

Benchmark date: 2026-05-10

Audio: `campaigns/{campaign}/audio/session20.wav`

Model: `large-v3`

Chunk size: `180` seconds

Audio duration: `6932.67s` (`01:55:32`)

## Results

| Architecture | Workers | Elapsed | Audio | Speed Factor | Output |
| --- | ---: | ---: | ---: | ---: | --- |
| existing_sequential | 1 | `4207.47s` (`70m 7s`) | `6932.67s` | `1.648x` | `benchmarks/transcription/session20/20260510-124624/existing/existing_transcript.txt` |
| parallel_workers | 2 | `2728.89s` (`45m 29s`) | `6932.67s` | `2.540x` | `benchmarks/transcription/session20/20260510-124624/parallel/parallel_transcript.txt` |
| parallel_workers | 3 | `2538.06s` (`42m 18s`) | `6932.67s` | `2.731x` | `benchmarks/transcription/session20/20260510-150026/parallel/parallel_transcript.txt` |

## Comparison

- Two-worker parallel was `1478.58s` faster than existing sequential, reducing wall-clock time by about `35.1%`.
- Three-worker parallel was `1669.41s` faster than existing sequential, reducing wall-clock time by about `39.7%`.
- Three-worker parallel was `190.83s` faster than two-worker parallel, reducing wall-clock time by about `7.0%`.
- Three workers won this benchmark, but the gain over two workers was modest and some individual chunks slowed down, suggesting the machine may be close to contention.
- Recommendation: use two workers as the default local transcription setting. Keep three workers for explicit comparison or time-sensitive runs only.

## Transcript Equivalence

All three transcript outputs are byte-for-byte identical.

| Pair | Result |
| --- | --- |
| existing sequential vs two-worker parallel | identical |
| existing sequential vs three-worker parallel | identical |
| two-worker parallel vs three-worker parallel | identical |

Shared transcript stats:

| Metric | Value |
| --- | ---: |
| Lines | `2579` |
| Words | `23107` |
| Bytes | `133473` |
| SHA-256 | `a48d0d9923bb85fe882a1726094f07f75bfd4b4f4ef1a916965a6a8d2f99eb24` |

## Notes

- Benchmark artifacts are intentionally ignored by Git under `benchmarks/`.
- This file preserves the summary metrics we want to keep from the ignored benchmark runs.
- The production `rag.py transcribe sessionXX` command now uses the two-worker parallel architecture by default.
- Existing sequential and two-worker parallel metrics came from `benchmarks/transcription/session20/20260510-124624/report.md`.
- Three-worker parallel metrics came from `benchmarks/transcription/session20/20260510-150026/report.md`.
- Transcript equivalence was checked with `wc`, `shasum -a 256`, and `cmp`.
