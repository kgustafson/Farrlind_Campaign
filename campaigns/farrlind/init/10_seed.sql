-- =============================================================================
-- SEED DATA — Known Campaign Entities (from documents)
-- =============================================================================

-- Locations
INSERT INTO location (name, location_type_id, description) VALUES
    ('Bentrios',          (SELECT id FROM location_type WHERE type_name='city'),         'Starting city; reverted to earlier age after Salazar fulfilled contract'),
    ('Thataways',         (SELECT id FROM location_type WHERE type_name='feywild'),      'Fey village; location of Khorag Well and the World Tree'),
    ('Paramon',           (SELECT id FROM location_type WHERE type_name='coastal'),      'Coastal city; Ordor Well disturbed here by Salazar'),
    ('Balrog',            (SELECT id FROM location_type WHERE type_name='dwarven_hold'), 'Dwarven hold; location of Saiffi Well; site of black dragon attack'),
    ('Catur',             (SELECT id FROM location_type WHERE type_name='underwater'),   'Sunken city beneath the coast; location of Catur Well'),
    ('Coast near Catur',  (SELECT id FROM location_type WHERE type_name='coastal'),      'Coast roughly 6 miles from Catur; party staging point before entering the sunken city'),
    ('Gale Monastery',    (SELECT id FROM location_type WHERE type_name='monastery'),    'Monastery of Open Hand; location of Open Hand Well'),
    ('Hanedal Island',    (SELECT id FROM location_type WHERE type_name='island'),       'Tiefling island; location of Hanedal Well'),
    ('Druid Retreat',     (SELECT id FROM location_type WHERE type_name='wilderness'),   'Jennifer Wilbreta''s coven and druid retreat in the mountains'),
    ('Mountain Road',      (SELECT id FROM location_type WHERE type_name='wilderness'),   'Mountain road toward Jennifer''s Druid Retreat'),
    ('Archaeological Dig Site', (SELECT id FROM location_type WHERE type_name='wilderness'), 'Ancient dig site tied to the transition from the Era of Dragons to the Era of Gods'),
    ('Alexander''s Inn',  (SELECT id FROM location_type WHERE type_name='inn'),          'Starting point; where the party formed in Bentrios');

-- fix Catur underwater flag
UPDATE location SET is_underwater = TRUE WHERE name = 'Catur';

-- Wells
INSERT INTO well (name, location_id, element_type_id, well_status_id, notes) VALUES
    ('Khorag',     (SELECT id FROM location WHERE name='Thataways'),       NULL,                                                          (SELECT id FROM well_status WHERE status_code='stable'),     'Revealed as World Tree; confirmed 6 wells exist; cataclysm has happened before'),
    ('Ordor',      (SELECT id FROM location WHERE name='Paramon'),         (SELECT id FROM element_type WHERE element_name='lightning'),  (SELECT id FROM well_status WHERE status_code='disturbed'),  'Used by Salazar'),
    ('Saiffi',     (SELECT id FROM location WHERE name='Balrog'),          NULL,                                                          (SELECT id FROM well_status WHERE status_code='with_party'), 'Currently carried by party in a waterskin'),
    ('Open Hand',  (SELECT id FROM location WHERE name='Gale Monastery'),  NULL,                                                          (SELECT id FROM well_status WHERE status_code='unknown'),    NULL),
    ('Catur',      (SELECT id FROM location WHERE name='Catur'),           NULL,                                                          (SELECT id FROM well_status WHERE status_code='unknown'),    'In sunken underwater city'),
    ('Hanedal',    (SELECT id FROM location WHERE name='Hanedal Island'),  NULL,                                                          (SELECT id FROM well_status WHERE status_code='unknown'),    NULL);

-- Factions
INSERT INTO faction (name, faction_type, alignment, description) VALUES
    ('Demon Lords',         'demon',    'evil',    'Demonic forces actively interfering with the wells'),
    ('Elemental Cults',     'cult',     'chaotic', 'Cults aligned with elemental/chaos forces'),
    ('Dwarves of Balrog',   'dwarven',  'neutral', 'Dwarven hold; allies of the party'),
    ('Fey of Thataways',    'fey',      'neutral', 'Fey community around the World Tree'),
    ('Abyssal Agents',      'demon',    'evil',    'Agents of the Abyss working against wells');

-- Enemies
INSERT INTO enemy (name, enemy_type, faction_id, element_type_id, threat_level_id, entity_status_id, description) VALUES
    ('Salazar',   'demon_lord', (SELECT id FROM faction WHERE name='Demon Lords'),   (SELECT id FROM element_type WHERE element_name='lightning'), (SELECT id FROM threat_level WHERE level_code='existential'), (SELECT id FROM entity_status WHERE status_code='alive'), 'Demon Lord of Lightning; fulfilled Baron Wells contract; reverted Bentrios'),
    ('Orsydon',   'dragon',     NULL,                                                NULL,                                                          (SELECT id FROM threat_level WHERE level_code='critical'),    (SELECT id FROM entity_status WHERE status_code='alive'), 'Black dragon summoned by cultists in Balrog'),
    ('Ardema',    'warlock',    (SELECT id FROM faction WHERE name='Elemental Cults'),NULL,                                                         (SELECT id FROM threat_level WHERE level_code='major'),       (SELECT id FROM entity_status WHERE status_code='alive'), 'Warlock who attacked Thataways; escaped'),
    ('Iron Paw',  'warlock',    (SELECT id FROM faction WHERE name='Elemental Cults'),NULL,                                                         (SELECT id FROM threat_level WHERE level_code='moderate'),    (SELECT id FROM entity_status WHERE status_code='dead'),  'Warlock; killed at corrupted Temple of Namaloa');

-- NPCs
INSERT INTO npc (name, entity_status_id, description) VALUES
    ('Baron Wells',  (SELECT id FROM entity_status WHERE status_code='unknown'), 'Mayor of Bentrios; made infernal deal with Salazar'),
    ('Jennifer',     (SELECT id FROM entity_status WHERE status_code='alive'),   'Ancient druid; confirmed wells and missing wand; last holder of Wand of Wells'),
    ('Sam',          (SELECT id FROM entity_status WHERE status_code='unknown'), 'Necrotic agent who infiltrated the caravan');

-- Party Characters
INSERT INTO player_character (name, player_name, background) VALUES
    ('Faban Colon', 'Player',  'Bard of the Open Road; keeper of the Grimoire; songwriter and chronicler of the party'),
    ('Gildas',      NULL,      'Arcane caster; received enhanced staff from Balrog'),
    ('Mikani',      NULL,      'Received breathing cap from Balrog for underwater travel'),
    ('Brigit',      NULL,      'Ranger/archer; received upgraded bow from Balrog'),
    ('Corvinas',    NULL,      'Paladin or cleric; received flame-wreathed blade from Balrog; judgment-focused'),
    ('Roon',        NULL,      'Tank/frontline; received shield from Balrog; notable ongoing relationship with mortality');

INSERT INTO character_class_level (character_id, character_class_id, level) VALUES
    ((SELECT id FROM player_character WHERE name='Faban Colon'), (SELECT id FROM character_class WHERE class_name='bard'), 7);

-- Artifacts
INSERT INTO artifact (name, artifact_type_id, description, lore_significance, is_sentient, is_cursed, is_infernal) VALUES
    ('The Black Blade',         (SELECT id FROM artifact_type WHERE type_name='weapon'),  'Matte black blade; refuses light; unnervingly perfect edge; given to Faban by Balrog dwarves', 'Feels like a decision already made; fits Faban''s hand too well', FALSE, FALSE, FALSE),
    ('Grimoire Mutandi',        (SELECT id FROM artifact_type WHERE type_name='grimoire'), 'Leather satchel covered in runes of hiding and protection; imbued with Siath, Goddess of Knowledge', 'People in Celestial Heights have been searching for this lost book of spells', TRUE, FALSE, FALSE),
    ('Urgan''s Axe',            (SELECT id FROM artifact_type WHERE type_name='axe'),     'Buried beneath the World Tree in Thataways', 'Legendary dwarven/orc artifact', FALSE, FALSE, FALSE),
    ('Infernal Orb of Rage',    (SELECT id FROM artifact_type WHERE type_name='orb'),     'Infernal orb discovered in Bentrios construct', 'Tied to Demon Lord of Rage', FALSE, FALSE, TRUE),
    ('Wand of Wells',           (SELECT id FROM artifact_type WHERE type_name='wand'),    'Only known method to control the Wells of Magic', 'Critical — stolen; last held by Jennifer', FALSE, FALSE, FALSE),
    ('Gildas'' Enhanced Staff', (SELECT id FROM artifact_type WHERE type_name='staff'),   'Given by Balrog dwarves; subtle weave of power within', 'Capable but not aggressive', FALSE, FALSE, FALSE),
    ('Mikani''s Breathing Cap', (SELECT id FROM artifact_type WHERE type_name='cap'),     'Simple appearance; grants underwater breathing; given by Balrog dwarves', 'Intentional gift — dwarves know the party is going to Catur', FALSE, FALSE, FALSE),
    ('Brigit''s Upgraded Bow',  (SELECT id FROM artifact_type WHERE type_name='bow'),     'Replacement/upgrade bow; string sings clean and eager; given by Balrog dwarves', NULL, FALSE, FALSE, FALSE),
    ('Corvinas'' Flame Blade',  (SELECT id FROM artifact_type WHERE type_name='weapon'),  'Blade wreathed in real fire; given by Balrog dwarves', 'Suits Corvinas; line between judgment and destruction negotiable', FALSE, FALSE, FALSE),
    ('Roon''s Shield',          (SELECT id FROM artifact_type WHERE type_name='shield'),  'Given by Balrog dwarves; weight and balance of a refusal; an anchor', 'Not merely defensive — a statement of continued existence', FALSE, FALSE, FALSE);

-- Sessions (known so far)
INSERT INTO session (session_number, session_date, in_game_date, title, party_level, location_id) VALUES
    (20, '2026-04-27', '1832 AS — Namal 20', 'Salt, Steel, and the Distance Between Legends', 7, (SELECT id FROM location WHERE name='Balrog'));

-- Artifact Custody — current holders
INSERT INTO artifact_custody (artifact_id, character_id, session_id, notes) VALUES
    ((SELECT id FROM artifact WHERE name='The Black Blade'),         (SELECT id FROM player_character WHERE name='Faban Colon'), (SELECT id FROM session WHERE session_number=20), 'Given by Balrog dwarves, Session 20'),
    ((SELECT id FROM artifact WHERE name='Grimoire Mutandi'),        (SELECT id FROM player_character WHERE name='Faban Colon'), (SELECT id FROM session WHERE session_number=20), 'Faban''s burden throughout the campaign'),
    ((SELECT id FROM artifact WHERE name='Gildas'' Enhanced Staff'), (SELECT id FROM player_character WHERE name='Gildas'),      (SELECT id FROM session WHERE session_number=20), 'Given by Balrog dwarves, Session 20'),
    ((SELECT id FROM artifact WHERE name='Mikani''s Breathing Cap'), (SELECT id FROM player_character WHERE name='Mikani'),      (SELECT id FROM session WHERE session_number=20), 'Given by Balrog dwarves, Session 20'),
    ((SELECT id FROM artifact WHERE name='Brigit''s Upgraded Bow'),  (SELECT id FROM player_character WHERE name='Brigit'),      (SELECT id FROM session WHERE session_number=20), 'Given by Balrog dwarves, Session 20'),
    ((SELECT id FROM artifact WHERE name='Corvinas'' Flame Blade'),  (SELECT id FROM player_character WHERE name='Corvinas'),    (SELECT id FROM session WHERE session_number=20), 'Given by Balrog dwarves, Session 20'),
    ((SELECT id FROM artifact WHERE name='Roon''s Shield'),          (SELECT id FROM player_character WHERE name='Roon'),        (SELECT id FROM session WHERE session_number=20), 'Given by Balrog dwarves, Session 20');

-- Knowledge visibility
INSERT INTO entity_knowledge (
    entity_type,
    entity_id,
    subject_type,
    subject_character_id,
    knowledge_state_id,
    visibility_level_id,
    first_known_session,
    is_revealed_to_party,
    notes
) VALUES (
    'artifact',
    (SELECT id FROM artifact WHERE name='Grimoire Mutandi'),
    'pc',
    (SELECT id FROM player_character WHERE name='Faban Colon'),
    (SELECT id FROM knowledge_state WHERE state_code='known'),
    (SELECT id FROM visibility_level WHERE level_code='private_pc'),
    NULL,
    FALSE,
    'Faban knows the Grimoire Mutandi well; it remains secret from the rest of the party.'
);

-- Songbook
INSERT INTO song (song_number, title, style_id, category_id, summary, lyrics_url, mp3_url) VALUES
    (1,  'The Off-Key Dragon',                    (SELECT id FROM song_style WHERE style_name='tavern_song'),   (SELECT id FROM song_category WHERE category_name='humor'),            'A dragon whose singing terrorizes more than its fire',                                         'https://docs.google.com/document/d/1Y83xhQ50SaQv5hEHZt0JdULeJhs3ahICJUF98EPfRjQ', 'https://drive.google.com/open?id=1oeGNsnuFI6m6jzCtNWOAtDfSZsZ35UZB'),
    (2,  'Sally and the Good Day',                (SELECT id FROM song_style WHERE style_name='tavern_song'),   (SELECT id FROM song_category WHERE category_name='humor'),            'Sally''s cheerful spirit turns every misfortune into celebration',                             'https://docs.google.com/document/d/1atKsg8jKG5jhWkJwLsMKYgbXRyshhGJA5hzgi4x3vik', 'https://drive.google.com/open?id=1_TSHLk07MyAy2PZNgZ98lzte1rN-sSMd'),
    (3,  'Roll the Barrel',                       (SELECT id FROM song_style WHERE style_name='sea_shanty'),    (SELECT id FROM song_category WHERE category_name='humor'),            'Rollicking drinking song celebrating reckless sailors',                                        'https://docs.google.com/document/d/1eVW7GzGgJ5OEzthTtyrRn4xQPZPW8khFvypDf-1xG9A', 'https://drive.google.com/open?id=1O4cTS-3zZglDgcaH47GeizEgJQMo-fbk'),
    (4,  'The One-Legged Lass',                   (SELECT id FROM song_style WHERE style_name='tavern_song'),   (SELECT id FROM song_category WHERE category_name='humor'),            'A legendary tavern woman who outdrinks and outwits every challenger',                          'https://docs.google.com/document/d/14UsBqJjeHysxyptIdjWxpmA3TcT70bnVMoCEJ-Itb6s', 'https://drive.google.com/open?id=1d21nG_9qmsX4I6b69wbEmp9R1H43S3Ud'),
    (5,  'The Contract of Baron Wells',           (SELECT id FROM song_style WHERE style_name='ballad'),        (SELECT id FROM song_category WHERE category_name='political_satire'), 'Warning tale: noble''s pact unleashes forces beyond control',                                  'https://docs.google.com/document/d/1KTaKIQIha1q9gtHuwRePZV-lhUgmgHYH7fIpAZCRo2g', 'https://drive.google.com/open?id=1PNGSD4ulixKd_BWT2nhtej_SNbpJzUe6'),
    (6,  'The Braggart Baron Who Bought His Battles', (SELECT id FROM song_style WHERE style_name='ballad'),   (SELECT id FROM song_category WHERE category_name='political_satire'), 'Mocking tale of a noble who claims heroes'' victories as his own',                             'https://docs.google.com/document/d/19Y4dXB_1VaDuffPNqI4mhIZJNpdD4ha84AxJKH7rNMc', 'https://drive.google.com/open?id=1IjYCn_nJk62EHT3mStLvnu30Yq0xLwQK'),
    (7,  'The Fool Who Outsang the Devil',        (SELECT id FROM song_style WHERE style_name='tavern_song'),   (SELECT id FROM song_category WHERE category_name='humor'),            'Bard wins singing contest against a disguised devil using love and human joy',                 'https://docs.google.com/document/d/1RYYbUjm6-5Pfm4IKFsHH1DxVXGZomHQOiV1sx2W1O68', 'https://drive.google.com/open?id=1vW7RwhXRrZNvpJeZS9MjxRDO5Ncfk71D'),
    (8,  'Flight of the Fairies',                 (SELECT id FROM song_style WHERE style_name='ballad'),        (SELECT id FROM song_category WHERE category_name='fey_folklore'),    'Celebration of mysterious fair folk in moonlit glades',                                        'https://docs.google.com/document/d/1Skwh7hO1yXnPMZVDJu9H7VXGy7YX4tI113fw8eECrFE', 'https://drive.google.com/open?id=15bRsU8-NjRAwwDr3AwkDaVg2r98JI8QK'),
    (9,  'Don''t Step in the Fairy Ring',         (SELECT id FROM song_style WHERE style_name='ballad'),        (SELECT id FROM song_category WHERE category_name='fey_folklore'),    'Warning that fairy rings may carry travelers to lands from which they may never return',       'https://docs.google.com/document/d/1GIdk9tqU9-1oMCxR5QvhYTS1VxpVCeefBThULBd1q30', 'https://drive.google.com/open?id=1ge6wUOTL15nsZ1GLHzX52E9Gc8UGmrPt'),
    (10, 'The Stars and the Centaurs',            (SELECT id FROM song_style WHERE style_name='ballad'),        (SELECT id FROM song_category WHERE category_name='lore'),             'Mythic tale of how stars and wild plains gave birth to the centaur race',                      'https://docs.google.com/document/d/1gWb4GDqdmS-w-mih3VLbC8UMcCS00-HqJmup3YVBA5k', 'https://drive.google.com/open?id=19-y_H0JQ9o537r-uOO50op9Eih_7ZRw-'),
    (11, 'Urgan Wyrmbane',                        (SELECT id FROM song_style WHERE style_name='war_chant'),     (SELECT id FROM song_category WHERE category_name='heroic_saga'),     'Battle anthem of the fearless warrior Urgan',                                                  'https://docs.google.com/document/d/1i5mEzVHczKq2myLJKDAZZOkbD0ECMfvbZhJaZMUNWfM/edit?usp=drivesdk', 'https://drive.google.com/open?id=1zkpsIShGZWJbNZga9M9vvcDres-fgYVL'),
    (12, 'The Day We Called It Victory',          (SELECT id FROM song_style WHERE style_name='ballad'),        (SELECT id FROM song_category WHERE category_name='lament'),           'Somber reflection on the illusion of victory and the forgotten valor of the enemy',            'https://docs.google.com/document/d/1yu8oXILnBE96bWirVny1N3gR8MxXUaXlN4_E2aZaV1U', 'https://drive.google.com/open?id=13aeVQ6BtsyG4Ah7UOm-Rx'),
    (13, 'The Defense of the Watery Dunes',       (SELECT id FROM song_style WHERE style_name='ballad'),        (SELECT id FROM song_category WHERE category_name='heroic_saga'),     'Paramon defenders stood firm against a corrupted sea guardian',                                'https://docs.google.com/document/d/1tb3wCD85AEB80rGA0n8CLefbeD9KW7EN0Ticl7k5zes', 'https://drive.google.com/open?id=1gHTpG6_kbSIaGiAqfPhlBb4iz-Sx'),
    (14, 'The Fallen Few at Devilspawn Valley',   (SELECT id FROM song_style WHERE style_name='ballad'),        (SELECT id FROM song_category WHERE category_name='heroic_saga'),     'Small band held a mountain pass against overwhelming evil',                                    'https://docs.google.com/document/d/1zU5qss81ouJvBIXUbcrOwSsQ-z62O4jpbUYGSdE2cyw', 'https://drive.google.com/open?id=1-3vEBd0SzEAo_Our4ehuO1hQfhz3VjQB'),
    (15, 'The Lost Miners of Karadum',            (SELECT id FROM song_style WHERE style_name='ballad'),        (SELECT id FROM song_category WHERE category_name='lament'),           'Remembrance of miners who vanished beneath the mountain they loved',                           'https://docs.google.com/document/d/15URVU7HduuQrpR4jCp6IsTtEMNls5XmjE_e97KpLvOA', 'https://drive.google.com/open?id=1brS1r95Q51bCTafkOJXZAE4'),
    (16, 'The Battle of Flintrock',               (SELECT id FROM song_style WHERE style_name='ballad'),        (SELECT id FROM song_category WHERE category_name='lament'),           'Two armies from the same people slaughter one another for the pride of their kings',           'https://docs.google.com/document/d/12We74JidneZ6EMqtk3d-eP8KNgVKdGYUHphMaBdVUPE', 'https://drive.google.com/open?id=1IkiDgP6lJRtkz5uwRbv5nkAwXjeKReQ3'),
    (17, 'The Fate of the Emerald Eel',           (SELECT id FROM song_style WHERE style_name='sea_shanty'),    (SELECT id FROM song_category WHERE category_name='lore'),             'Doomed ship encounters cursed phantom vessel the Donny Bell',                                  'https://docs.google.com/document/d/153E_NNfZaRU9WfqnDae58AdLgnr_riTg0AjxNbTBGN8', 'https://drive.google.com/open?id=1hWOt0fcDParlZ4fwkfaCST1HTs7f6Yv5'),
    (18, 'Ranger Rick and his Mighty Stick',      (SELECT id FROM song_style WHERE style_name='tavern_song'),   (SELECT id FROM song_category WHERE category_name='humor'),            'Wildly exaggerated tavern tale of a legendary ranger',                                         'https://docs.google.com/document/d/1YNHoU8ECDqM3RZQZD_H3PPe46DpXbhKRKAyv0GPNiFc', 'https://drive.google.com/open?id=1sWTocCBdOQFP0KXEEbXKmdmRcH9SvRxW'),
    (19, 'Mihira''s Rise',                        (SELECT id FROM song_style WHERE style_name='ballad'),        (SELECT id FROM song_category WHERE category_name='lore'),             'Goddess Mihira''s blind justice changed when war and love forced her to see',                  'https://docs.google.com/document/d/1iHqrglmqDaARjjHD6bNcNfps8gDdm8C3FMftPYe8p_0', 'https://drive.google.com/open?id=1ZSKySWHQzDjTSOKpH2-NjSfSDqXsy_za'),
    (20, 'The Ballad of Mortalkind',              (SELECT id FROM song_style WHERE style_name='ballad'),        (SELECT id FROM song_category WHERE category_name='lore'),             'Sweeping history: fall of dragonkind, rise of mortal civilization',                           'https://docs.google.com/document/d/1u32xLKJRYoucM6VFaxBJ7af9npeFgXNYsDyncVjQrNc', 'https://drive.google.com/open?id=1U_UrI9-gL1f8ruqcQoH1KtUnC-5wVb6x'),
    (21, 'The Keeper of the Quiet Key',           (SELECT id FROM song_style WHERE style_name='ballad'),        (SELECT id FROM song_category WHERE category_name='lore'),             'Solemn meditation on guarding dangerous truths; burden of silence',                           'https://docs.google.com/document/d/1PmM3scvY2Yn0ZNm4rYck3tTbftPMNHYl216WeV9mobQ', 'https://drive.google.com/open?id=1-n9ZnohEMFRxOaOltwLDZr--vtG2LjZY'),
    (22, 'Silent Queen of Whisper Vale',          (SELECT id FROM song_style WHERE style_name='ballad'),        (SELECT id FROM song_category WHERE category_name='lament'),           'Queen Mary guides her kingdom after her beloved king is assassinated',                         'https://docs.google.com/document/d/1zlMvslJspjEaCezHPzqQgREc1qLdnl4KxkP4p_hu9I4', 'https://drive.google.com/open?id=1roZtQeE_wgcBmmdPn2E-yeqh-fD61vRb'),
    (23, 'The Hand That Did Not Open',            (SELECT id FROM song_style WHERE style_name='ballad'),        (SELECT id FROM song_category WHERE category_name='lament'),           'Personal lament: choosing not to wield hidden power and bearing the quiet cost alone',         'https://docs.google.com/document/d/1e-7fpx8NxugmXNMSukXI8mv5XeTqbyU6uWlysvzu2tE', 'https://drive.google.com/open?id=1vGx4nqwm3OkTHhhGgtPtNsCq7qMhsq8F'),
    (24, 'The Road We Walk Together',             (SELECT id FROM song_style WHERE style_name='tavern_song'),   (SELECT id FROM song_category WHERE category_name='fellowship'),       'Tribute to bonds of friendship between companions who face hardship together',                 'https://docs.google.com/document/d/1BLJfHTXok4ktyoKZB5MzXXIF4EYKNcnBYMzY93Q4dKQ', 'https://drive.google.com/open?id=1mOPNnuugEWf2KhwM3rtfHW'),
    (25, 'The Long Road Home',                    (SELECT id FROM song_style WHERE style_name='ballad'),        (SELECT id FROM song_category WHERE category_name='fellowship'),       'Comforting song reminding wanderers they carry companionship wherever they go',                'https://docs.google.com/document/d/1_3c26SDHz7Nz9E_0VAbHhhQUrWeYexbWj8ZQfrNSuVw', 'https://drive.google.com/open?id=1j6EPxRpflVmqaY1uWYCYDo85e0vopVIc'),
    (26, 'The Lantern in Your Window',            (SELECT id FROM song_style WHERE style_name='ballad'),        (SELECT id FROM song_category WHERE category_name='fellowship'),       'Beloved love song: love will always light the way home',                                       'https://docs.google.com/document/d/1s4csJXwiWNpeNf7GUZbF79tl0pA2HKaUYhr5QC9DKPc', 'https://drive.google.com/open?id=1VdestSb1WF9TOP39N4K4Li2_eemoYro7');

UPDATE song AS s
SET
    title = v.title,
    song_type = v.song_type,
    short_description = v.short_description,
    long_description = v.long_description,
    summary = v.long_description,
    lyrics_local_path = v.lyrics_local_path,
    mp3_local_path = v.mp3_local_path
FROM (VALUES
    (1,  'The Off-Key Dragon', 'Comic tavern song', 'Humor / Tavern Entertainment', 'A ridiculous tale of a dragon whose singing voice is so terrible that it terrifies villages more than its fire ever could.', 'knowledge/Faban/songbook/The_Off_Key_Dragon/lyrics.md', 'knowledge/Faban/songbook/The_Off_Key_Dragon/song.mp3'),
    (2,  'Sally and the Good Day', '3/4 tavern jig', 'Tavern morale song', 'The story of Sally, whose cheerful spirit and refusal to surrender to gloom turns every misfortune into a reason to celebrate life.', 'knowledge/Faban/songbook/Sally_and_the_Good_Day/lyrics.md', 'knowledge/Faban/songbook/Sally_and_the_Good_Day/song.mp3'),
    (3,  'Roll the Barrel', 'Traditional sea shanty', 'Sailor tavern song', 'A rollicking drinking song celebrating the reckless joy of sailors who find courage and camaraderie at the bottom of a rum barrel.', 'knowledge/Faban/songbook/Roll_the_Barrel/lyrics.md', 'knowledge/Faban/songbook/Roll_the_Barrel/song.mp3'),
    (4,  'The One-Legged Lass', 'Bawdy drinking song', 'Tavern comedy', 'A legendary tavern woman with a wooden leg who outdrinks, outdances, and outwits every challenger foolish enough to test her.', 'knowledge/Faban/songbook/The_One_Legged_Lass/lyrics.md', 'knowledge/Faban/songbook/The_One_Legged_Lass/song.mp3'),
    (5,  'The Contract of Baron Wells', 'Political cautionary ballad', 'Consequence / power', 'A warning tale about a noble whose pact and ambition unleashed forces beyond control.', 'knowledge/Faban/songbook/The_Contract_of_Baron_Wells/lyrics.md', 'knowledge/Faban/songbook/The_Contract_of_Baron_Wells/song.mp3'),
    (6,  'The Lord Who Bought His Battles', 'Satirical tavern folk song', 'Political satire', 'A mocking tale of a boastful noble who hires heroes to fight his monsters and then proudly claims their victories as his own.', 'knowledge/Faban/songbook/The_Lord_Who_Bought_His_Battles/lyrics.md', 'knowledge/Faban/songbook/The_Lord_Who_Bought_His_Battles/song.mp3'),
    (7,  'The Fool Who Outsang the Devil', 'Clever Tavern folk song', 'Trickster tale / wit defeating evil', 'A quick-thinking bard challenges a disguised devil to a singing contest and wins by singing of love, hope, and human joy - things the devil cannot match.', 'knowledge/Faban/songbook/The_Fool_Who_Outsang_the_Devil/lyrics.md', 'knowledge/Faban/songbook/The_Fool_Who_Outsang_the_Devil/song.mp3'),
    (8,  'Flight of the Fairies', 'Whimsical folk dance', 'Fey folklore', 'A lighthearted celebration of the mysterious fair folk, whose laughter and mischief fill moonlit glades and forest clearings.', 'knowledge/Faban/songbook/Flight_of_the_Fairies/lyrics.md', 'knowledge/Faban/songbook/Flight_of_the_Fairies/song.mp3'),
    (9,  'Don''t Step in the Fairy Ring', 'Folk warning song', 'Fey cautionary tale', 'A cheerful but cautionary tale warning travelers that stepping into a fairy ring may carry them to strange lands from which they may never return.', 'knowledge/Faban/songbook/Don_t_Step_in_the_Fairy_Ring/lyrics.md', 'knowledge/Faban/songbook/Don_t_Step_in_the_Fairy_Ring/song.mp3'),
    (10, 'The Stars and the Centaurs', 'Lively cosmic jig', 'Mythic lore', 'A mythic tale describing how the wisdom of the stars and the spirit of the wild plains gave birth to the centaur race.', 'knowledge/Faban/songbook/The_Stars_and_the_Centaurs/lyrics.md', 'knowledge/Faban/songbook/The_Stars_and_the_Centaurs/song.mp3'),
    (11, 'Urgan Wyrmbane', 'Orc war chant', 'Heroic saga / Orc legend', 'A battle anthem recounting the fearless deeds of the warrior Urgan, whose courage carried him through countless battles.', 'knowledge/Faban/songbook/Urgan_Wyrmbane/lyrics.md', 'knowledge/Faban/songbook/Urgan_Wyrmbane/song.mp3'),
    (12, 'The Day We Called It Victory', 'Quiet reflective bardic ballad', 'Moral lament / truth of war', 'A somber reflection on the illusion of victory, honoring the forgotten valor of the enemy and exposing the quiet sins of the victors that time chooses to forget.', 'knowledge/Faban/songbook/The_Day_We_Called_It_Victory/lyrics.md', 'knowledge/Faban/songbook/The_Day_We_Called_It_Victory/song.mp3'),
    (13, 'The Defense of the Watery Dunes', 'Shore ballad', 'Heroic chronicle', 'The story of Paramon''s defenders who stood firm against a corrupted sea guardian and the unnatural tide that threatened their home.', 'knowledge/Faban/songbook/The_Defense_of_the_Watery_Dunes/lyrics.md', 'knowledge/Faban/songbook/The_Defense_of_the_Watery_Dunes/song.mp3'),
    (14, 'The Fallen Few at Devilspawn Valley', 'Epic heroic ballad', 'Heroic sacrifice', 'The legendary stand of a small band of warriors who held a mountain pass against overwhelming evil so that the realm might survive.', 'knowledge/Faban/songbook/The_Fallen_Few/lyrics.md', 'knowledge/Faban/songbook/The_Fallen_Few/song.mp3'),
    (15, 'The Lost Miners of Karadum', 'Dwarven lament', 'Tragic ballad', 'A somber remembrance of the miners of Karadum who vanished beneath the mountain they loved and labored within.', 'knowledge/Faban/songbook/The_Lost_Miners_of_Karadum/lyrics.md', 'knowledge/Faban/songbook/The_Lost_Miners_of_Karadum/song.mp3'),
    (16, 'The Battle of Flintrock', 'Tragic historical ballad', 'War lament', 'A sorrowful tale of two armies from the same people who slaughtered one another at Flintrock for the pride of their kings.', 'knowledge/Faban/songbook/The_Battle_of_Flintrock/lyrics.md', 'knowledge/Faban/songbook/The_Battle_of_Flintrock/song.mp3'),
    (17, 'The Fate of the Emerald Eel', 'Dark sea shanty', 'Ghost legend', 'A haunting maritime tale of the ship Emerald Eel and her doomed encounter with the cursed phantom vessel known as the Donny Bell.', 'knowledge/Faban/songbook/The_Fate_of_the_Emerald_Eel/lyrics.md', 'knowledge/Faban/songbook/The_Fate_of_the_Emerald_Eel/song.mp3'),
    (18, 'Ranger Rick and his Mighty Stick', 'Rowdy tavern call-and-response', 'Bawdy Humor', 'A wildly exaggerated tavern tale about the legendary ranger and the remarkable effectiveness of his mighty stick.', 'knowledge/Faban/songbook/Ranger_Rick_and_his_Mighty_Stick/lyrics.md', 'knowledge/Faban/songbook/Ranger_Rick_and_his_Mighty_Stick/song.mp3'),
    (19, 'Mihira''s Rise (The Ballad of Justice Untamed)', 'Theological epic ballad', 'Divine legend', 'The tale of the goddess Mihira, whose blind justice was forever changed when war and love forced her to see the world she judged.', 'knowledge/Faban/songbook/Mihiras_Rise/lyrics.md', 'knowledge/Faban/songbook/Mihiras_Rise/song.mp3'),
    (20, 'The Ballad of Mortalkind', 'Epic chronicle', 'Cosmology / history', 'A sweeping history of the ages describing the fall of dragonkind and the rise of mortal civilization and its dangerous ambitions.', 'knowledge/Faban/songbook/The_Ballad_of_Mortalkind/lyrics.md', 'knowledge/Faban/songbook/The_Ballad_of_Mortalkind/song.mp3'),
    (21, 'The Keeper of the Quiet Key', 'Reflective philosophical ballad', 'Moral allegory', 'A solemn meditation on the burden of guarding dangerous truths and the lonely responsibility of those who choose silence for the sake of others.', 'knowledge/Faban/songbook/The_Keeper_of_the_Quiet_Key/lyrics.md', 'knowledge/Faban/songbook/The_Keeper_of_the_Quiet_Key/song.mp3'),
    (22, 'Silent Queen of Whisper Vale', 'Lament', 'Leadership / grief', 'The story of Queen Mary of Whisper Vale, whose quiet strength guides her kingdom after the assassination of her beloved king.', 'knowledge/Faban/songbook/Silent_Queen_of_Whisper_Vale/lyrics.md', 'knowledge/Faban/songbook/Silent_Queen_of_Whisper_Vale/song.mp3'),
    (23, 'The Hand That Did Not Open', 'Reflective bardic ballad', 'Personal Lament', 'A deeply personal song in which the bard recounts a moment of absolute choice, choosing not to wield a hidden power and bearing the quiet cost of that decision alone.', 'knowledge/Faban/songbook/The_Hand_That_Did_Not_Open/lyrics.md', 'knowledge/Faban/songbook/The_Hand_That_Did_Not_Open/song.mp3'),
    (24, 'The Road We Walk Together', 'Fellowship tavern ballad', 'Companionship song', 'A tribute to the bonds of friendship and loyalty between companions who face hardship and adventure together.', 'knowledge/Faban/songbook/The_Road_We_Walk_Together/lyrics.md', 'knowledge/Faban/songbook/The_Road_We_Walk_Together/song.mp3'),
    (25, 'The Long Road Home', 'Traveling ballad', 'Journey song', 'A comforting song reminding wanderers that no matter how far they travel, they carry the companionship of others with them.', 'knowledge/Faban/songbook/The_Long_Road_Home/lyrics.md', 'knowledge/Faban/songbook/The_Long_Road_Home/song.mp3'),
    (26, 'The Lantern in Your Window', 'Romantic wedding ballad', 'Ceremony / love song', 'A beloved love song promising that no matter how long the road or how dark the night, love will always light the way home.', 'knowledge/Faban/songbook/The_Lantern_in_Your_Window/lyrics.md', 'knowledge/Faban/songbook/The_Lantern_in_Your_Window/song.mp3')
) AS v(song_number, title, song_type, short_description, long_description, lyrics_local_path, mp3_local_path)
WHERE s.song_number = v.song_number;

INSERT INTO songbook_front_matter (title, foreword_path, notes) VALUES
    ('The Revealed Songbook of Faban Colon', 'knowledge/Faban/songbook/foreward.md', 'Foreword placeholder for generated songbook documents.');

-- Lore Items
INSERT INTO lore_item (title, category, description, is_confirmed) VALUES
    ('Six Wells Exist',             'well_knowledge', 'There are exactly 6 Wells of Magic in the world. Confirmed by Khorag.',                             TRUE),
    ('Wells Always Tell Truth',     'well_knowledge', 'The Wells of Magic never lie.',                                                                      TRUE),
    ('Wand of Wells Required',      'well_knowledge', 'The Wand of Wells is the only known method to close or control the Wells.',                          TRUE),
    ('Cataclysm Has Happened Before','cosmology',     'This is not the first Cataclysm. Confirmed by Khorag.',                                              TRUE),
    ('Cataclysm Cannot Be Stopped', 'well_knowledge', 'The Cataclysm can only be delayed, not stopped. Learned at Balrog/Saiffi.',                          TRUE),
    ('Wells Tied to Elements',      'well_knowledge', 'Wells are tied to Elemental and Primordial forces: Order, Chaos, Arcana.',                           TRUE),
    ('Wand of Wells Stolen',        'well_knowledge', 'The Wand of Wells is currently missing. Last holder: Jennifer, ancient druid.',                      TRUE),
    ('Siath and the Grimoire',      'divine',         'The Grimoire Mutandi is imbued with the presence of Siath, Goddess of Knowledge. Sought in Celestial Heights.', TRUE),
    ('Bentrios Reversion',          'history',        'Demon Lord Salazar fulfilled Baron Wells'' infernal contract; Bentrios was reverted to an earlier age. Warforged disappeared.', TRUE);

-- Grimoire entry
INSERT INTO grimoire_entry (artifact_id, entry_title, content, language, is_deciphered, related_deity) VALUES
    ((SELECT id FROM artifact WHERE name='Grimoire Mutandi'),
     'Title Page',
     'Grimoire Mutandi Uter Sciencia Et Memoria — changing both knowledge and memory. Leather satchel covered in runes of hiding and protection. Central rune with old common script. Sought by people of Celestial Heights.',
     'old_common',
     TRUE,
     'Siath');

-- Faban diary entry (Session 20)
INSERT INTO diary_entry (character_id, session_id, in_game_date, title, content, emotional_tone) VALUES
    ((SELECT id FROM player_character WHERE name='Faban Colon'),
     (SELECT id FROM session WHERE session_number=20),
     '1832 AS — Namal 20 / Namal 24',
     'Salt, Steel, and the Distance Between Legends',
     'Session 20 diary entry — departure from Balrog with dwarven gifts, four days travel to coast, arrival at Catur shoreline, encounter with fishermen, preparations to descend into the sunken city.',
     'reflective');

-- Campaign arc
INSERT INTO campaign_arc (name, is_complete, summary) VALUES
    ('Bentrios',                TRUE,  'Party forms at Alexander''s Inn; Warforged malfunction; Infernal Orb discovered; Baron Wells'' deal with Salazar; city reverted'),
    ('Feywild and First Well',  TRUE,  'Enter Fey Woods; reach Thataways; discover Urgan''s Axe; Khorag Well reveals 6 wells exist; Cataclysm confirmed'),
    ('Paramon',                 TRUE,  'Coastal arc; Ordor Well disturbed by Salazar; sea entity defeated'),
    ('Balrog',                  TRUE,  'Dwarven hold; Saiffi Well accessed; black dragon Orsydon attack; party now carries living Well'),
    ('Catur',                   FALSE, 'Underwater sunken city; party preparing to descend; Catur Well location unknown within city');

-- Active threats
INSERT INTO active_threat (enemy_id, threat_level_id, description, is_active) VALUES
    ((SELECT id FROM enemy WHERE name='Salazar'),  (SELECT id FROM threat_level WHERE level_code='existential'), 'Demon Lord of Lightning; contract fulfilled but still active threat',  TRUE),
    ((SELECT id FROM enemy WHERE name='Orsydon'),  (SELECT id FROM threat_level WHERE level_code='critical'),    'Black dragon summoned in Balrog; outcome of battle not yet recorded',  TRUE),
    ((SELECT id FROM enemy WHERE name='Ardema'),   (SELECT id FROM threat_level WHERE level_code='major'),       'Warlock who attacked Thataways; escaped; whereabouts unknown',         TRUE);

-- Open threads
INSERT INTO open_thread (
    title, thread_type, status, first_session_id, last_session_id,
    related_location_id, description, notes
) VALUES
    ('Where is the Wand of Wells now?', 'lore_mystery', 'open', (SELECT id FROM session WHERE session_number=6), (SELECT id FROM session WHERE session_number=19), (SELECT id FROM location WHERE name='Druid Retreat'), 'Khorag says the Wand closes Wells and names Jennifer as last known user; Jennifer later says it was stolen amid magical failures. The party continues planning around the Wand.', 'Loaded from approved open threads pass.'),
    ('What does it mean to carry Saiffi?', 'lore_mystery', 'open', (SELECT id FROM session WHERE session_number=18), (SELECT id FROM session WHERE session_number=20), (SELECT id FROM location WHERE name='Balrog'), 'Saiffi is a truth-bound Well and is currently with the party in a waterskin. The lore file explicitly marks the meaning of carrying Saiffi as unanswered.', 'Loaded from approved open threads pass.'),
    ('What will happen at the sunken city of Catur?', 'pending_quest', 'open', (SELECT id FROM session WHERE session_number=13), (SELECT id FROM session WHERE session_number=20), (SELECT id FROM location WHERE name='Catur'), 'Catur is one of the known Wells. The party has reached the coast, gained a boat, and is preparing to descend, while locals warn that Catur''s peoples distrust strangers.', 'Loaded from approved open threads pass.'),
    ('What is the large intelligence or force beneath the waters near Catur?', 'dm_foreshadowing', 'open', (SELECT id FROM session WHERE session_number=20), (SELECT id FROM session WHERE session_number=20), (SELECT id FROM location WHERE name='Coast near Catur'), 'The fishermen report missing boats, lights under the water, and something thought-large beneath. This appears to be immediate next-session foreshadowing.', 'Loaded from approved open threads pass.'),
    ('Can the Cataclysm be stopped, or only softened?', 'lore_mystery', 'open', (SELECT id FROM session WHERE session_number=5), (SELECT id FROM session WHERE session_number=19), NULL, 'Multiple sources say the Cataclysm may be underway, tied to Wells, primordial over-release, dragons, and possibly not fully preventable.', 'Loaded from approved open threads pass.'),
    ('What are the rules of disturbed, active, depleted, or portable Wells?', 'lore_mystery', 'open', (SELECT id FROM session WHERE session_number=14), (SELECT id FROM session WHERE session_number=18), (SELECT id FROM location WHERE name='Paramon'), 'Ordor is disturbed and later no longer sentient; Saiffi can be carried; the consolidated Wells lore lists the rules of Well states as an open question.', 'Loaded from approved open threads pass.'),
    ('What does each Well want, fear, or protect?', 'lore_mystery', 'open', (SELECT id FROM session WHERE session_number=6), (SELECT id FROM session WHERE session_number=18), NULL, 'Khorag, Ordor, and Saiffi behave differently. The lore file names this as an open question, and future Wells may distrust the party.', 'Loaded from approved open threads pass.'),
    ('Where is the Monastery of the Open Hand Well in the Gale?', 'pending_quest', 'open', (SELECT id FROM session WHERE session_number=6), (SELECT id FROM session WHERE session_number=14), (SELECT id FROM location WHERE name='Gale Monastery'), 'Khorag identifies a sibling in the heart of the Gale at a monastery of the Open Hand; Jennifer confirms it as a known Well. It has not been visited.', 'Loaded from approved open threads pass.'),
    ('How will the party reach Hanedal and its Well?', 'pending_quest', 'open', (SELECT id FROM session WHERE session_number=5), (SELECT id FROM session WHERE session_number=14), (SELECT id FROM location WHERE name='Hanedal Island'), 'Father Joseph says Hanedal Island has one of the Wells and no known maps; Jennifer identifies Henedal/Hanedal as birthplace of magic and a Well location across the sea.', 'Loaded from approved open threads pass.'),
    ('Who stole the Wand of Wells, and for what purpose?', 'active_threat', 'open', (SELECT id FROM session WHERE session_number=13), (SELECT id FROM session WHERE session_number=15), (SELECT id FROM location WHERE name='Druid Retreat'), 'Jennifer says the Wand was stolen; the tabaxi later says demons seek resurrection material and that the Cataclysm may be required. This may point to an organized actor.', 'Loaded from approved open threads pass.'),
    ('Are the cults trying to return Tiamat, Chaotix, or both?', 'active_threat', 'open', (SELECT id FROM session WHERE session_number=9), (SELECT id FROM session WHERE session_number=19), (SELECT id FROM location WHERE name='Balrog'), 'Library research names Chaotix and primordial chaos; the tabaxi says Tiamat and demons are preparing resurrection; Balrog cultists summon Orsydon while trying to awaken Tiamat.', 'Loaded from approved open threads pass.'),
    ('What is Corvinas'' connection to Rage, the Wells, and the Cataclysm?', 'character_hook', 'open', (SELECT id FROM session WHERE session_number=4), (SELECT id FROM session WHERE session_number=17), (SELECT id FROM location WHERE name='Paramon'), 'Corvinas bears an infernal mark tied to a demon of rage; the Paramon Well recognizes him as conflict; his village history and the Well backlash remain unresolved.', 'Loaded from approved open threads pass.'),
    ('Who is Cole, and what does The Rogue betrayal card mean?', 'character_hook', 'open', (SELECT id FROM session WHERE session_number=13), (SELECT id FROM session WHERE session_number=13), (SELECT id FROM location WHERE name='Mountain Road'), 'Cole reappears with a magical deck; Faban draws The Rogue, which Cole says harbingers betrayal. No later resolution appears in current canon.', 'Loaded from approved open threads pass.'),
    ('What remains of Ardema of the Seven Seals?', 'active_threat', 'open', (SELECT id FROM session WHERE session_number=6), (SELECT id FROM session WHERE session_number=7), (SELECT id FROM location WHERE name='Thataways'), 'Ardema appears during the attack on Thataways and plane-shifts away rather than dying. His identity, faction, and next move remain unresolved.', 'Loaded from approved open threads pass.'),
    ('What is the meaning of the sapphire-eyed stranger?', 'dm_foreshadowing', 'unknown', (SELECT id FROM session WHERE session_number=15), (SELECT id FROM session WHERE session_number=15), (SELECT id FROM location WHERE name='Paramon'), 'Gildas speaks with a sapphire-eyed stranger in a tavern and mentions it only once afterward. This has no current explanation.', 'Loaded from approved open threads pass.'),
    ('Who or what was riding the Paramon guardian?', 'active_threat', 'open', (SELECT id FROM session WHERE session_number=14), (SELECT id FROM session WHERE session_number=15), (SELECT id FROM location WHERE name='Paramon'), 'The water elemental appears to have been a place-bound guardian used or ridden by another force, suggesting an invader capable of repeating the act.', 'Loaded from approved open threads pass.'),
    ('What faith or faction was Iron Paw actually serving?', 'faction_tension', 'open', (SELECT id FROM session WHERE session_number=15), (SELECT id FROM session WHERE session_number=17), (SELECT id FROM location WHERE name='Paramon'), 'Iron Paw wears borrowed Namaloan colors, reacts strongly to the Celestial Isles, casts Silence readily, and reveals eldritch or hellish power before defeat. His larger allegiance remains unclear.', 'Loaded from approved open threads pass.'),
    ('Why does the eastern coast remember conquest around the Celestial Isles?', 'faction_tension', 'open', (SELECT id FROM session WHERE session_number=15), (SELECT id FROM session WHERE session_number=16), (SELECT id FROM location WHERE name='Paramon'), 'Paramon grows quiet around the Celestial Isles, and commoner testimony suggests the eastern coast remembers conquest while claiming forgetfulness.', 'Loaded from approved open threads pass.'),
    ('What ancient curses or protections remain at the archaeological dig site?', 'lore_mystery', 'open', (SELECT id FROM session WHERE session_number=11), (SELECT id FROM session WHERE session_number=13), (SELECT id FROM location WHERE name='Archaeological Dig Site'), 'Sam warns that removing the site''s protection may return the arcane, Wells, and ancient curses; later evidence includes Abyssal influence and a necrotic dagger.', 'Loaded from approved open threads pass.'),
    ('What is the role of the black/obsidian Abyssal dagger?', 'active_threat', 'open', (SELECT id FROM session WHERE session_number=12), (SELECT id FROM session WHERE session_number=13), (SELECT id FROM location WHERE name='Archaeological Dig Site'), 'Sam uses the black dagger in a failed blood ritual; Gildas identifies it as Abyssal/necrotic and stores it with other dangerous artifacts.', 'Loaded from approved open threads pass.');

