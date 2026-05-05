# Whole-Campaign Travel Log Check

Generated from the reviewed session database after session00-session20 canon review and the first travel-log cleanup pass.

## Current Structured Route

| Session | From | To | Method | Days | Confidence | Basis |
|---:|---|---|---|---:|---|---|
| 02 | Bentrios | Fey Woods | foot | 1 | high | Diary dates span Apollal 12 to Apollal 13; inferred as 1 elapsed calendar day. |
| 04 | Fey Woods | Thataways | foot | 0 | high | Session04 begins on Apollal 13, the same in-game date as the fey witch battle; the centaur leads the party from the Fey Woods to Thataways before Apollal 14 events. |
| 05 | Thataways | Bentrios | foot | 1 | high | Diary dates span Apollal 14 to Apollal 15; inferred as 1 elapsed calendar day, though the travel covers parts of both dated days. |
| 06 | Bentrios | Thataways | foot | 1 | high | Diary dates span Apollal 16 to Apollal 17; inferred as 1 elapsed calendar day. |
| 08 | Thataways | Spore Sanctuary | foot | 0 | medium | Diary date remains Apollal 18; this appears to be same-day or partial-day travel. |
| 08 | Spore Sanctuary | Bellemaine | foot | 0 | medium | Diary date remains Apollal 18; travel appears same-day or partial-day after leaving the spore sanctuary. |
| 10 | Bellemaine | Road to Archaeological Dig Site | wagon | 0 | high | Session10 begins the caravan journey on Apollal 22; the party meets Richard and the caravan at the northern gate and receives a carriage. |
| 12 | Road to Archaeological Dig Site | Archaeological Dig Site | wagon | 12 | medium | The caravan journey begins on Apollal 22 and reaches the archaeological dig site on Namal 6, a 12-day elapsed span across sessions10-12. |
| 13 | Archaeological Dig Site | Mountain Road | foot | 0 | medium | Session13 begins at the archaeological dig site on Namal 6; the party sets out northward into the mountains and takes shelter in a shallow cave. |
| 13 | Mountain Road | Druid Retreat | foot | 4 | high | Diary dates span Namal 6 to Namal 10; inferred as 4 elapsed calendar days. |
| 14 | Druid Retreat | Paramon | portal | 0 | high | Diary date remains Namal 11 and travel is by portal; inferred as same-day travel. |
| 17 | Paramon | Crossroads | foot | 2 | high | Reviewed session17 dates show Paramon on Namal 13-14 and the Crossroads Festival around Namal 15-17. |
| 17 | Crossroads | Balrog | foot | 3 | high | Reviewed session17 dates place the Crossroads Festival around Namal 15-17 and arrival in Balrog on Namal 18; the combined Paramon-to-Balrog route remains 5 elapsed days. |
| 20 | Balrog | Coast near Catur | foot | 4 | high | Reviewed date span runs Namal 20 to Namal 24; inferred as 4 elapsed calendar days. |

Total currently tracked travel duration: 28 days.

## Session Location Timeline

| Session | In-Game Date | Primary Location | Event Locations |
|---:|---|---|---|
| 00 | 1832 AS Apollal 10 | Bentrios | Alexander's Inn; Bentrios |
| 01 | 1832 AS Apollal 10 | Bentrios | Bentrios |
| 02 | 1832 AS Apollal 11, 1832 AS Apollal 12, 1832 AS Apollal 13 | Fey Woods | Bentrios; Fey Woods; Road to Fey Woods |
| 03 | 1832 AS Apollal 13 | Fey Woods | Fey Woods |
| 04 | 1832 AS Apollal 13, 1832 AS Apollal 14 | Thataways | Thataways |
| 05 | 1832 AS Apollal 14, 1832 AS Apollal 15 | Bentrios | Bentrios; Road to Bentrios; Thataways |
| 06 | 1832 AS Apollal 16, 1832 AS Apollal 17 | Thataways | Thataways |
| 07 | 1832 AS Apollal 17 | Thataways | Thataways |
| 08 | 1832 AS Apollal 18 | Thataways | Bellemaine; Spore Sanctuary; Thataways |
| 09 | 1832 AS Apollal 19, 1832 AS Apollal 20, 1832 AS Apollal 21 | Bellemaine | Bellemaine |
| 10 | 1832 AS Apollal 21, 1832 AS Apollal 22 | Bellemaine | Bellemaine; Road to Archaeological Dig Site |
| 11 | 1832 AS Apollal 21, 1832 AS Namal 1, 1832 AS Namal 4, 1832 AS Namal 6 | Road to Archaeological Dig Site | Road to Archaeological Dig Site |
| 12 | 1832 AS Namal 6 | Road to Archaeological Dig Site | Archaeological Dig Site; Road to Archaeological Dig Site |
| 13 | 1832 AS Namal 6, 1832 AS Namal 7, 1832 AS Namal 8, 1832 AS Namal 9, 1832 AS Namal 10 | Druid Retreat | Archaeological Dig Site; Druid Retreat; Mountain Road |
| 14 | 1832 AS Namal 11 | Druid Retreat | Druid Retreat; Paramon |
| 15 | 1832 AS Namal 11 | Paramon | Paramon |
| 16 | 1832 AS Namal 12, 1832 AS Namal 13 | Paramon | Paramon |
| 17 | 1832 AS Namal 13, 1832 AS Namal 14, 1832 AS Namal 15-17, 1832 AS Namal 18 | Paramon | Balrog; Crossroads; Paramon |
| 18 | 1832 AS Namal 18 (continued) | Balrog | Balrog |
| 19 | 1832 AS Namal 19 (continued) | Balrog | Balrog |
| 20 | 1832 AS Namal 20, 1832 AS Namal 24 | Coast near Catur | Balrog; Catur; Coast near Catur |

## Completed Fixes

1. Session 03 was corrected from Thataways to Fey Woods.
   The fey witch battle now belongs to the Fey Woods, matching the fact that Thataways is first reached in session04.

2. Session 04 now has an explicit Fey Woods -> Thataways arrival leg.
   The centaur-led transition into Thataways is represented as a same-day travel row.

3. Session 08 now splits the Spore Sanctuary waypoint.
   The route is represented as Thataways -> Spore Sanctuary -> Bellemaine.

4. The ambiguous Camp Site route has been removed.
   The caravan arc now starts as Bellemaine -> Road to Archaeological Dig Site in session10 and reaches Archaeological Dig Site in session12.

5. Session 13 now starts from Archaeological Dig Site.
   The route is represented as Archaeological Dig Site -> Mountain Road -> Druid Retreat.

6. Session 17 now includes the Crossroads waypoint.
   Paramon -> Balrog is represented as Paramon -> Crossroads -> Balrog, while preserving the same 5-day total.

7. Session 20 remains correct.
   The route ends at Coast near Catur, not Catur itself.

## Remaining Notes

1. Some zero-day legs are intentional.
   These represent same-day waypoint transitions or departures where the elapsed calendar travel is already counted in a later arrival row.

2. The 12-day caravan duration is assigned to the arrival leg in session12.
   This keeps the full Bellemaine-to-dig-site elapsed span without pretending the party reached the dig site in session10.

3. Session20 event locations still include Catur.
   This appears to be destination/warning context rather than actual arrival. The travel row correctly ends at Coast near Catur.
