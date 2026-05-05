# Backlog

## Song Suggestions From Major Session Events

Status: idea

Add an optional command that suggests possible new Faban song topics from a session.

Candidate command:

```bash
./rag-env/bin/python scripts/dm_query.py song-suggestions session20
```

Intent:

- Suggest songs only for major events, revelations, victories, losses, or emotionally important turns.
- Avoid repeats of songs already in Faban's repertoire.
- Prefer one to five strong suggestions over a long list.
- Include the source session/event for each suggestion.
- Explain why each event is song-worthy.
- Mark uncertain suggestions as uncertain instead of overclaiming.

Possible inputs:

- `session.summary`
- `session_event.description`
- `session_event.significance`
- existing `song` / `v_songbook` titles and summaries

Possible output:

```text
Session 20 Song Suggestions

- The Lights Beneath Catur
  Source: Session 20, missing boats and underwater lights.
  Why: New arc hook, strong visual image, not already covered by the songbook.

- Salt, Steel, and the Distance Between Legends
  Source: Session 20, departure from Balrog with dwarven gifts.
  Why: Good transitional ballad if the Balrog arc needs closure.
```
