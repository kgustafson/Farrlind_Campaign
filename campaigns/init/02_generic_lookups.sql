-- =============================================================================
-- SEED DATA — Reference Tables
-- =============================================================================

INSERT INTO entity_status (status_code, description) VALUES
    ('alive',       'Confirmed living'),
    ('dead',        'Confirmed dead'),
    ('unknown',     'Status not confirmed'),
    ('missing',     'Last known location unknown'),
    ('imprisoned',  'Captured or confined'),
    ('fled',        'Escaped encounter');

INSERT INTO well_status (status_code, description) VALUES
    ('stable',      'Well is balanced and contained'),
    ('disturbed',   'Well has been interfered with'),
    ('active',      'Well is actively releasing energy'),
    ('depleted',    'Well energy has been drained'),
    ('with_party',  'Well is being carried by the party'),
    ('unknown',     'Status not yet determined');

INSERT INTO threat_level (level_code, sort_order) VALUES
    ('minor',       1),
    ('moderate',    2),
    ('major',       3),
    ('critical',    4),
    ('existential', 5);

INSERT INTO knowledge_state (state_code, description) VALUES
    ('unknown',   'Subject does not know this entity or fact'),
    ('rumored',   'Subject has heard an unverified or incomplete version'),
    ('suspected', 'Subject has reason to suspect this entity or fact'),
    ('known',     'Subject knows this entity or fact'),
    ('witnessed', 'Subject directly witnessed this entity or fact');

INSERT INTO visibility_level (level_code, description) VALUES
    ('dm_only',      'True in canon but hidden from players'),
    ('private_pc',   'Known privately by one player character'),
    ('shared_party', 'Known by the adventuring party'),
    ('public_world', 'Broadly known in-world'),
    ('rumor',        'Available as rumor, incomplete or unverified');

INSERT INTO event_type (type_name) VALUES
    ('combat'), ('travel'), ('discovery'), ('social'),
    ('ritual'), ('catastrophe'), ('rest'), ('acquisition');

INSERT INTO milestone_type (type_name) VALUES
    ('combat'), ('narrative'), ('personal'), ('discovery'),
    ('loss'), ('achievement'), ('gift_received'), ('song_written');

INSERT INTO element_type (element_name) VALUES
    ('lightning'), ('rage'), ('order'), ('chaos'),
    ('arcana'), ('fire'), ('water'), ('earth'), ('air');

INSERT INTO relationship_type (type_name) VALUES
    ('ally'), ('enemy'), ('neutral'), ('mentor'),
    ('rival'), ('romantic'), ('unknown'), ('feared_by'), ('worships');

INSERT INTO location_type (type_name) VALUES
    ('city'), ('dungeon'), ('feywild'), ('coastal'), ('underwater'),
    ('island'), ('monastery'), ('dwarven_hold'), ('wilderness'), ('inn'), ('temple');

INSERT INTO artifact_type (type_name) VALUES
    ('weapon'), ('armor'), ('orb'), ('grimoire'), ('wand'),
    ('staff'), ('shield'), ('cap'), ('axe'), ('bow');

INSERT INTO combat_outcome (outcome_code, description) VALUES
    ('defeated', 'Enemy or encounter was overcome.'),
    ('killed', 'Enemy was killed.'),
    ('captured', 'Enemy was captured.'),
    ('escaped', 'Enemy escaped the encounter.'),
    ('fled', 'Enemy fled the encounter.'),
    ('summoned', 'Enemy was summoned or appeared.'),
    ('unknown', 'Outcome has not been established.');

INSERT INTO workflow_status_state (status_code, description) VALUES
    ('initialized', 'Workflow has been created but not started.'),
    ('pending', 'Step is waiting to run.'),
    ('running', 'Step is currently running.'),
    ('completed', 'Step or workflow completed successfully.'),
    ('partially_completed', 'Workflow has completed some but not all steps.'),
    ('blocked', 'Step cannot proceed until a blocker is cleared.'),
    ('needs_attention', 'Human attention is required.'),
    ('failed', 'Step or workflow failed.'),
    ('skipped', 'Step was intentionally skipped.');

INSERT INTO artifact_flag (flag_code, description) VALUES
    ('sentient', 'Artifact has awareness or agency.'),
    ('cursed', 'Artifact carries a harmful curse.'),
    ('infernal', 'Artifact has infernal origin, influence, or binding.');

INSERT INTO song_style (style_name) VALUES
    ('tavern_song'), ('ballad'), ('sea_shanty'), ('war_chant'), ('jig'), ('lament')
ON CONFLICT DO NOTHING;

INSERT INTO song_category (category_name) VALUES
    ('humor'), ('political_satire'), ('heroic_saga'), ('lament'),
    ('fey_folklore'), ('lore'), ('fellowship'), ('personal')
ON CONFLICT DO NOTHING;

INSERT INTO character_class (class_name, hit_die) VALUES
    ('bard',      8),  ('wizard',   6),  ('ranger',   10),
    ('cleric',    8),  ('paladin',  10), ('fighter',  10),
    ('rogue',     8),  ('druid',    8),  ('warlock',  8);

INSERT INTO character_race (race_name) VALUES
    ('human'), ('elf'), ('dwarf'), ('halfling'), ('tiefling'),
    ('gnome'), ('half-orc'), ('warforged'), ('dragonborn');


