-- Generated from campaign.yaml by raglib.campaign_metadata_seed.
-- Seeds campaign-specific player characters and known NPC glossary entries.

INSERT INTO character_class (class_name)
SELECT 'bard'
WHERE 'bard' <> ''
  AND NOT EXISTS (SELECT 1 FROM character_class WHERE lower(class_name) = lower('bard'));

INSERT INTO character_race (race_name)
SELECT 'elf'
WHERE 'elf' <> ''
  AND NOT EXISTS (SELECT 1 FROM character_race WHERE lower(race_name) = lower('elf'));

UPDATE player_character
SET
    player_name = COALESCE(NULLIF('Brian Murphy', ''), player_name),
    character_class_id = COALESCE((SELECT id FROM character_class WHERE lower(class_name) = lower('bard') LIMIT 1), character_class_id),
    character_race_id = COALESCE((SELECT id FROM character_race WHERE lower(race_name) = lower('elf') LIMIT 1), character_race_id),
    notes = COALESCE(NULLIF('One of the Trinyvale Triplets; introduced in the transcript as an elven bard. Aliases: Jens Lindell, Jins, Murph.', ''), notes)
WHERE lower(name) = lower('Jens Lyndelle');

INSERT INTO player_character (
    name, player_name, character_class_id, character_race_id, is_active, notes
)
SELECT
    'Jens Lyndelle',
    'Brian Murphy',
    (SELECT id FROM character_class WHERE lower(class_name) = lower('bard') LIMIT 1),
    (SELECT id FROM character_race WHERE lower(race_name) = lower('elf') LIMIT 1),
    TRUE,
    'One of the Trinyvale Triplets; introduced in the transcript as an elven bard. Aliases: Jens Lindell, Jins, Murph.'
WHERE NOT EXISTS (SELECT 1 FROM player_character WHERE lower(name) = lower('Jens Lyndelle'));

INSERT INTO character_class (class_name)
SELECT 'warlock'
WHERE 'warlock' <> ''
  AND NOT EXISTS (SELECT 1 FROM character_class WHERE lower(class_name) = lower('warlock'));

INSERT INTO character_race (race_name)
SELECT ''
WHERE '' <> ''
  AND NOT EXISTS (SELECT 1 FROM character_race WHERE lower(race_name) = lower(''));

UPDATE player_character
SET
    player_name = COALESCE(NULLIF('Emily Axford', ''), player_name),
    character_class_id = COALESCE((SELECT id FROM character_class WHERE lower(class_name) = lower('warlock') LIMIT 1), character_class_id),
    character_race_id = COALESCE((SELECT id FROM character_race WHERE lower(race_name) = lower('') LIMIT 1), character_race_id),
    notes = COALESCE(NULLIF('One of the Trinyvale Triplets; introduced as a social media warlock from the moon. Aliases: Onyx back.', ''), notes)
WHERE lower(name) = lower('Onyx Lumiere');

INSERT INTO player_character (
    name, player_name, character_class_id, character_race_id, is_active, notes
)
SELECT
    'Onyx Lumiere',
    'Emily Axford',
    (SELECT id FROM character_class WHERE lower(class_name) = lower('warlock') LIMIT 1),
    (SELECT id FROM character_race WHERE lower(race_name) = lower('') LIMIT 1),
    TRUE,
    'One of the Trinyvale Triplets; introduced as a social media warlock from the moon. Aliases: Onyx back.'
WHERE NOT EXISTS (SELECT 1 FROM player_character WHERE lower(name) = lower('Onyx Lumiere'));

INSERT INTO character_class (class_name)
SELECT 'ranger'
WHERE 'ranger' <> ''
  AND NOT EXISTS (SELECT 1 FROM character_class WHERE lower(class_name) = lower('ranger'));

INSERT INTO character_race (race_name)
SELECT 'half-elf'
WHERE 'half-elf' <> ''
  AND NOT EXISTS (SELECT 1 FROM character_race WHERE lower(race_name) = lower('half-elf'));

UPDATE player_character
SET
    player_name = COALESCE(NULLIF('Jake Hurwitz', ''), player_name),
    character_class_id = COALESCE((SELECT id FROM character_class WHERE lower(class_name) = lower('ranger') LIMIT 1), character_class_id),
    character_race_id = COALESCE((SELECT id FROM character_race WHERE lower(race_name) = lower('half-elf') LIMIT 1), character_race_id),
    notes = COALESCE(NULLIF('One of the Trinyvale Triplets; introduced in the transcript as Jens''s shirtless half-elf half brother. Aliases: Nyac, Niac, Nayak, Jake.', ''), notes)
WHERE lower(name) = lower('Nyack of the Ran''afor');

INSERT INTO player_character (
    name, player_name, character_class_id, character_race_id, is_active, notes
)
SELECT
    'Nyack of the Ran''afor',
    'Jake Hurwitz',
    (SELECT id FROM character_class WHERE lower(class_name) = lower('ranger') LIMIT 1),
    (SELECT id FROM character_race WHERE lower(race_name) = lower('half-elf') LIMIT 1),
    TRUE,
    'One of the Trinyvale Triplets; introduced in the transcript as Jens''s shirtless half-elf half brother. Aliases: Nyac, Niac, Nayak, Jake.'
WHERE NOT EXISTS (SELECT 1 FROM player_character WHERE lower(name) = lower('Nyack of the Ran''afor'));

WITH incoming AS (
    SELECT
        'Strahd von Zarovich'::text AS name,
        'Strahd, Strahd Von Zorovich, Strahd von Zorovich'::text AS alias,
        'Vampire lord of Barovia; the Triplets keep interpreting him as the resort manager.'::text AS description,
        ARRAY['Strahd', 'Strahd Von Zorovich', 'Strahd von Zorovich'] AS aliases
),
matched AS (
    SELECT n.id
    FROM npc n, incoming i
    WHERE lower(n.name) = lower(i.name)
       OR lower(n.name) = ANY(SELECT lower(unnest(i.aliases)))
       OR lower(i.name) = ANY(SELECT lower(unnest(string_to_array(COALESCE(n.alias, ''), ', '))))
    ORDER BY n.id
    LIMIT 1
),
updated AS (
    UPDATE npc n
    SET
        alias = COALESCE(NULLIF(n.alias, ''), i.alias),
        description = COALESCE(NULLIF(n.description, ''), i.description),
        entity_status_id = COALESCE(n.entity_status_id, (SELECT id FROM entity_status WHERE status_code = 'unknown' LIMIT 1)),
        notes = CASE
            WHEN n.notes IS NULL OR n.notes = '' THEN 'Seeded from campaign.yaml.'
            WHEN n.notes NOT LIKE '%Seeded from campaign.yaml.%' THEN n.notes || E'\nSeeded from campaign.yaml.'
            ELSE n.notes
        END
    FROM incoming i, matched m
    WHERE n.id = m.id
    RETURNING n.id
)
INSERT INTO npc (
    name, alias, entity_status_id, description, is_named, notes
)
SELECT
    i.name,
    i.alias,
    (SELECT id FROM entity_status WHERE status_code = 'unknown' LIMIT 1),
    i.description,
    TRUE,
    'Seeded from campaign.yaml.'
FROM incoming i
WHERE NOT EXISTS (SELECT 1 FROM matched);

WITH incoming AS (
    SELECT
        'Kolyan Indirovich'::text AS name,
        'Kolyan, Burgomaster Kolyan'::text AS alias,
        'Burgomaster of Barovia; father of Ismark and adoptive father of Marina Kulyana.'::text AS description,
        ARRAY['Kolyan', 'Burgomaster Kolyan'] AS aliases
),
matched AS (
    SELECT n.id
    FROM npc n, incoming i
    WHERE lower(n.name) = lower(i.name)
       OR lower(n.name) = ANY(SELECT lower(unnest(i.aliases)))
       OR lower(i.name) = ANY(SELECT lower(unnest(string_to_array(COALESCE(n.alias, ''), ', '))))
    ORDER BY n.id
    LIMIT 1
),
updated AS (
    UPDATE npc n
    SET
        alias = COALESCE(NULLIF(n.alias, ''), i.alias),
        description = COALESCE(NULLIF(n.description, ''), i.description),
        entity_status_id = COALESCE(n.entity_status_id, (SELECT id FROM entity_status WHERE status_code = 'unknown' LIMIT 1)),
        notes = CASE
            WHEN n.notes IS NULL OR n.notes = '' THEN 'Seeded from campaign.yaml.'
            WHEN n.notes NOT LIKE '%Seeded from campaign.yaml.%' THEN n.notes || E'\nSeeded from campaign.yaml.'
            ELSE n.notes
        END
    FROM incoming i, matched m
    WHERE n.id = m.id
    RETURNING n.id
)
INSERT INTO npc (
    name, alias, entity_status_id, description, is_named, notes
)
SELECT
    i.name,
    i.alias,
    (SELECT id FROM entity_status WHERE status_code = 'unknown' LIMIT 1),
    i.description,
    TRUE,
    'Seeded from campaign.yaml.'
FROM incoming i
WHERE NOT EXISTS (SELECT 1 FROM matched);

WITH incoming AS (
    SELECT
        'Marina Kulyana'::text AS name,
        'Marina, Marina Kuljana, Marina Kolyana'::text AS alias,
        'Kolyan''s adopted daughter, bitten by a vampire.'::text AS description,
        ARRAY['Marina', 'Marina Kuljana', 'Marina Kolyana'] AS aliases
),
matched AS (
    SELECT n.id
    FROM npc n, incoming i
    WHERE lower(n.name) = lower(i.name)
       OR lower(n.name) = ANY(SELECT lower(unnest(i.aliases)))
       OR lower(i.name) = ANY(SELECT lower(unnest(string_to_array(COALESCE(n.alias, ''), ', '))))
    ORDER BY n.id
    LIMIT 1
),
updated AS (
    UPDATE npc n
    SET
        alias = COALESCE(NULLIF(n.alias, ''), i.alias),
        description = COALESCE(NULLIF(n.description, ''), i.description),
        entity_status_id = COALESCE(n.entity_status_id, (SELECT id FROM entity_status WHERE status_code = 'unknown' LIMIT 1)),
        notes = CASE
            WHEN n.notes IS NULL OR n.notes = '' THEN 'Seeded from campaign.yaml.'
            WHEN n.notes NOT LIKE '%Seeded from campaign.yaml.%' THEN n.notes || E'\nSeeded from campaign.yaml.'
            ELSE n.notes
        END
    FROM incoming i, matched m
    WHERE n.id = m.id
    RETURNING n.id
)
INSERT INTO npc (
    name, alias, entity_status_id, description, is_named, notes
)
SELECT
    i.name,
    i.alias,
    (SELECT id FROM entity_status WHERE status_code = 'unknown' LIMIT 1),
    i.description,
    TRUE,
    'Seeded from campaign.yaml.'
FROM incoming i
WHERE NOT EXISTS (SELECT 1 FROM matched);

WITH incoming AS (
    SELECT
        'Ismark'::text AS name,
        'Ismark the Lesser'::text AS alias,
        'Kolyan''s son; meets the party at Blood on the Vine and becomes suspicious of their disguises.'::text AS description,
        ARRAY['Ismark the Lesser'] AS aliases
),
matched AS (
    SELECT n.id
    FROM npc n, incoming i
    WHERE lower(n.name) = lower(i.name)
       OR lower(n.name) = ANY(SELECT lower(unnest(i.aliases)))
       OR lower(i.name) = ANY(SELECT lower(unnest(string_to_array(COALESCE(n.alias, ''), ', '))))
    ORDER BY n.id
    LIMIT 1
),
updated AS (
    UPDATE npc n
    SET
        alias = COALESCE(NULLIF(n.alias, ''), i.alias),
        description = COALESCE(NULLIF(n.description, ''), i.description),
        entity_status_id = COALESCE(n.entity_status_id, (SELECT id FROM entity_status WHERE status_code = 'unknown' LIMIT 1)),
        notes = CASE
            WHEN n.notes IS NULL OR n.notes = '' THEN 'Seeded from campaign.yaml.'
            WHEN n.notes NOT LIKE '%Seeded from campaign.yaml.%' THEN n.notes || E'\nSeeded from campaign.yaml.'
            ELSE n.notes
        END
    FROM incoming i, matched m
    WHERE n.id = m.id
    RETURNING n.id
)
INSERT INTO npc (
    name, alias, entity_status_id, description, is_named, notes
)
SELECT
    i.name,
    i.alias,
    (SELECT id FROM entity_status WHERE status_code = 'unknown' LIMIT 1),
    i.description,
    TRUE,
    'Seeded from campaign.yaml.'
FROM incoming i
WHERE NOT EXISTS (SELECT 1 FROM matched);

WITH incoming AS (
    SELECT
        'Bluetooth'::text AS name,
        'Jens Z, Jens Z. Bluetooth'::text AS alias,
        'Onyx''s imp familiar, also nicknamed Jens Z.'::text AS description,
        ARRAY['Jens Z', 'Jens Z. Bluetooth'] AS aliases
),
matched AS (
    SELECT n.id
    FROM npc n, incoming i
    WHERE lower(n.name) = lower(i.name)
       OR lower(n.name) = ANY(SELECT lower(unnest(i.aliases)))
       OR lower(i.name) = ANY(SELECT lower(unnest(string_to_array(COALESCE(n.alias, ''), ', '))))
    ORDER BY n.id
    LIMIT 1
),
updated AS (
    UPDATE npc n
    SET
        alias = COALESCE(NULLIF(n.alias, ''), i.alias),
        description = COALESCE(NULLIF(n.description, ''), i.description),
        entity_status_id = COALESCE(n.entity_status_id, (SELECT id FROM entity_status WHERE status_code = 'unknown' LIMIT 1)),
        notes = CASE
            WHEN n.notes IS NULL OR n.notes = '' THEN 'Seeded from campaign.yaml.'
            WHEN n.notes NOT LIKE '%Seeded from campaign.yaml.%' THEN n.notes || E'\nSeeded from campaign.yaml.'
            ELSE n.notes
        END
    FROM incoming i, matched m
    WHERE n.id = m.id
    RETURNING n.id
)
INSERT INTO npc (
    name, alias, entity_status_id, description, is_named, notes
)
SELECT
    i.name,
    i.alias,
    (SELECT id FROM entity_status WHERE status_code = 'unknown' LIMIT 1),
    i.description,
    TRUE,
    'Seeded from campaign.yaml.'
FROM incoming i
WHERE NOT EXISTS (SELECT 1 FROM matched);
