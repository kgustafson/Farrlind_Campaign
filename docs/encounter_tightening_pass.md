# Encounter Tightening Pass

Generated from `knowledge/Faban/encounters.yaml` and loaded into the `encounter` table.

## What Changed

The database now has a scene-level `encounter` table that links important encounter scenes back to reviewed `session_event` rows.

Each encounter tracks:

- session
- linked reviewed event
- encounter type
- subtype
- location
- title
- participants
- outcome
- confidence
- notes

Enemy quantities still live in `event_enemy` via `knowledge/Faban/enemy_encounters.yaml`.

## Current Encounter Counts

| Type | Count |
|---|---:|
| combat | 10 |
| hazard | 1 |
| social | 13 |

## Seeded Encounters

| Session | Type | Location | Encounter | Outcome | Confidence |
|---:|---|---|---|---|---|
| 00 | social | Alexander's Inn | Party forms at Alexander's Inn | party_forms | high |
| 00 | combat | Bentrios | Rock-being street attack | continues_into_session01 | high |
| 01 | social | Bentrios | Baron Wells and Salazar in Bentrios Tower | deadline_revealed | high |
| 02 | social | Bentrios | Father Joseph consultation | lore_gained | high |
| 02 | social | Fey Woods | Oak in the outer Fey Woods | guidance_gained | high |
| 02 | social | Fey Woods | Blue-skinned fey bargain refused | combat_triggered | high |
| 03 | combat | Fey Woods | Fey witch battle | enemies_defeated | high |
| 04 | social | Thataways | Arrival at Thataways | settlement_reached | high |
| 04 | social | Thataways | Partial sage council | quest_terms_discussed | high |
| 04 | social | Thataways | Full sage council grants Urgan's Axe | artifact_granted | high |
| 06 | combat | Thataways | Dinosaur at the Fey forest edge | enemy_defeated | medium |
| 07 | combat | Thataways | Defense of Thataways against Ardema | enemy_fled | high |
| 08 | hazard | Spore Sanctuary | Spore Sanctuary passage | party_exits_sanctuary | medium |
| 09 | combat | Bellemaine | Bellemaine construct attack | continues_into_session10 | high |
| 10 | combat | Bellemaine | Dao transformation battle | enemies_defeated | high |
| 11 | social | Road to Archaeological Dig Site | Faban questions Sam | warning_and_ring_revealed | high |
| 12 | combat | Road to Archaeological Dig Site | Sam caravan battle | enemies_defeated_or_fled | high |
| 13 | social | Mountain Road | Cole's magical deck | cards_drawn | high |
| 13 | social | Druid Retreat | Jennifer reveals herself | quest_contact_found | high |
| 14 | combat | Paramon | Biha-Bibir battle at Paramon | enemies_defeated | high |
| 16 | combat | Paramon | Iron Paw summons Wasterlich and fish-things | enemies_defeated | high |
| 17 | social | Crossroads | Crossroads Festival | festival_accepted | high |
| 19 | combat | Balrog | Orsydon summoned in Balrog | dragon_defeated | high |
| 20 | social | Coast near Catur | Negotiation for a vessel | boat_obtained | high |

## Lower-Confidence Encounter Scenes

| Session | Encounter | Why |
|---:|---|---|
| 06 | Dinosaur at the Fey forest edge | Creature is described as large lizard/dinosaur; exact canon taxonomy may need confirmation. |
| 08 | Spore Sanctuary passage | The route/encounter is clear, but the scene may deserve richer hazard detail later. |

## Next Tightening Ideas

1. Add event-to-NPC links for key social encounters.
2. Split complex combats into phases only where it helps answer real questions.
3. Add encounter roles for participants, such as negotiator, witness, enemy, guide, summoner, rescuer, or quest giver.
4. Add a query command in `dm_query.py` for `encounters`, `enemy-encounters`, and `npc-encounters`.
