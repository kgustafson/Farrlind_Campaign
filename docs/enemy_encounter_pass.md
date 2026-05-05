# Enemy Encounter Pass

Generated from `knowledge/Faban/enemy_encounters.yaml` and loaded into `event_enemy`.

## Query Shape

Enemy encounters now track:

- enemy name/type
- session and linked reviewed event
- event location
- quantity encountered
- outcome
- confidence
- notes

This supports questions such as:

- How many goblins have we encountered?
- Which session had frog-like creatures?
- Where did the party fight cultists?
- Which enemies were defeated, fled, summoned, or unresolved?

## Seeded Encounter Counts

| Enemy | Type | Quantity | Sessions |
|---|---|---:|---|
| Ardema | warlock | 1 | 7 |
| Bellemaine construct | construct | 1 | 9 |
| Biha-Bibir | sea_entity | 1 | 14 |
| Cultist | cultist | unknown | 19 |
| Cultist controller | cultist | 1 | 9 |
| Dao | elemental | 1 | 10 |
| Dinosaur | beast | 1 | 6 |
| Druid Retreat archer | archer | 1 | 13 |
| Fey witch | fey_witch | 1 | 3 |
| Fish-thing | aquatic_creature | 3 | 16 |
| Frog-like creature | summoned_beast | 2 | 12 |
| Goblin | goblin | 2 | 3 |
| Hostile ranger | ranger | 5 | 12 |
| Iron Paw | warlock | 1 | 16 |
| Marl | elemental | 1 | 10 |
| Orsydon | dragon | 1 | 19 |
| Regenerating construct | construct | 1 | 0 |
| Sam | necrotic_agent | 1 | 12 |
| Wasterlich | undead | 1 | 16 |
| Water elemental | elemental | 1 | 14 |

## Lower-Confidence Items

These should be tightened later from diary/transcript/audio where possible:

| Enemy | Session | Current Quantity | Confidence | Note |
|---|---:|---:|---|---|
| Dinosaur | 6 | 1 | medium | The source says large lizard/dinosaur; exact taxonomy may need canon naming. |
| Cultist controller | 9 | 1 | medium | The controller is likely a cultist but the label is inferred. |
| Marl | 10 | 1 | medium | The creature name/spelling should be confirmed. |
| Druid Retreat archer | 13 | 1 | medium | This may be Jennifer or another retreat defender rather than an enemy. |
| Cultist | 19 | unknown | medium | Cultist count is not yet known from the reviewed final summary. |

## Implementation Notes

- `event_enemy` now has `quantity`, `confidence`, and `notes`.
- `scripts/load_summaries.py` loads curated rows from `knowledge/Faban/enemy_encounters.yaml`.
- Generic enemies are inserted into `enemy` if they do not already exist.
- Existing reviewed events remain the source of truth; enemy rows link back to final `session_event` rows by session and sequence.
