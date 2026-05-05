-- =============================================================================
-- FARRLIND CAMPAIGN DATABASE SCHEMA
-- Full 3NF PostgreSQL Schema
-- Character: Faban Colon | Campaign: Farrlind
-- =============================================================================

-- =============================================================================
-- LOOKUP / REFERENCE TABLES
-- =============================================================================

CREATE TABLE entity_status (
    id              SERIAL PRIMARY KEY,
    status_code     VARCHAR(30) NOT NULL UNIQUE,  -- 'alive','dead','unknown','missing','imprisoned','fled'
    description     TEXT
);

CREATE TABLE faction (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL UNIQUE,
    faction_type    VARCHAR(50),                  -- 'demon','cult','dwarven','fey','mortal','divine','elemental'
    alignment       VARCHAR(20),                  -- 'good','evil','neutral','chaotic','lawful'
    description     TEXT,
    is_active       BOOLEAN DEFAULT TRUE
);

CREATE TABLE location_type (
    id              SERIAL PRIMARY KEY,
    type_name       VARCHAR(50) NOT NULL UNIQUE   -- 'city','dungeon','feywild','coastal','underwater','island','monastery','dwarven_hold'
);

CREATE TABLE element_type (
    id              SERIAL PRIMARY KEY,
    element_name    VARCHAR(50) NOT NULL UNIQUE   -- 'lightning','rage','order','chaos','arcana','fire','water','earth','air'
);

CREATE TABLE song_category (
    id              SERIAL PRIMARY KEY,
    category_name   VARCHAR(80) NOT NULL UNIQUE   -- 'humor','political_satire','heroic_saga','lament','fey_folklore',...
);

CREATE TABLE song_style (
    id              SERIAL PRIMARY KEY,
    style_name      VARCHAR(80) NOT NULL UNIQUE   -- 'tavern_song','ballad','sea_shanty','war_chant','jig',...
);

CREATE TABLE artifact_type (
    id              SERIAL PRIMARY KEY,
    type_name       VARCHAR(50) NOT NULL UNIQUE   -- 'weapon','armor','orb','grimoire','wand','staff','shield','cap'
);

CREATE TABLE well_status (
    id              SERIAL PRIMARY KEY,
    status_code     VARCHAR(30) NOT NULL UNIQUE,  -- 'stable','disturbed','active','depleted','unknown','with_party'
    description     TEXT
);

CREATE TABLE character_class (
    id              SERIAL PRIMARY KEY,
    class_name      VARCHAR(50) NOT NULL UNIQUE,  -- 'bard','wizard','ranger','cleric','paladin','fighter','rogue'
    hit_die         SMALLINT
);

CREATE TABLE character_race (
    id              SERIAL PRIMARY KEY,
    race_name       VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE relationship_type (
    id              SERIAL PRIMARY KEY,
    type_name       VARCHAR(50) NOT NULL UNIQUE   -- 'ally','enemy','neutral','mentor','rival','romantic','unknown'
);

CREATE TABLE milestone_type (
    id              SERIAL PRIMARY KEY,
    type_name       VARCHAR(50) NOT NULL UNIQUE   -- 'combat','narrative','personal','discovery','loss','achievement'
);

CREATE TABLE event_type (
    id              SERIAL PRIMARY KEY,
    type_name       VARCHAR(50) NOT NULL UNIQUE   -- 'combat','travel','discovery','social','ritual','catastrophe'
);

CREATE TABLE threat_level (
    id              SERIAL PRIMARY KEY,
    level_code      VARCHAR(20) NOT NULL UNIQUE,  -- 'minor','moderate','major','critical','existential'
    sort_order      SMALLINT NOT NULL
);

CREATE TABLE knowledge_state (
    id              SERIAL PRIMARY KEY,
    state_code      VARCHAR(30) NOT NULL UNIQUE,  -- 'unknown','rumored','suspected','known','witnessed'
    description     TEXT
);

CREATE TABLE visibility_level (
    id              SERIAL PRIMARY KEY,
    level_code      VARCHAR(30) NOT NULL UNIQUE,  -- 'dm_only','private_pc','shared_party','public_world','rumor'
    description     TEXT
);


-- =============================================================================
-- CORE WORLD TABLES
-- =============================================================================

CREATE TABLE location (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(150) NOT NULL UNIQUE,
    location_type_id INT REFERENCES location_type(id),
    parent_location_id INT REFERENCES location(id),   -- region hierarchy (Catur is in coastal region, etc.)
    description     TEXT,
    is_underwater   BOOLEAN DEFAULT FALSE,
    is_feywild      BOOLEAN DEFAULT FALSE,
    first_visited_session INT,                         -- FK added after session table created
    notes           TEXT,
    metadata        JSONB                              -- flex for DM-side details
);

CREATE TABLE well (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL UNIQUE,      -- Khorag, Ordor, Saiffi, Open Hand, Catur, Hanedal
    location_id     INT REFERENCES location(id),
    element_type_id INT REFERENCES element_type(id),
    well_status_id  INT REFERENCES well_status(id),
    always_tells_truth BOOLEAN DEFAULT TRUE,
    notes           TEXT,
    metadata        JSONB
);

CREATE TABLE npc (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(150) NOT NULL,
    alias           VARCHAR(150),                      -- nicknames Faban uses
    faction_id      INT REFERENCES faction(id),
    entity_status_id INT REFERENCES entity_status(id),
    last_known_location_id INT REFERENCES location(id),
    first_seen_session INT,                            -- FK added after session table
    description     TEXT,
    is_named        BOOLEAN DEFAULT TRUE,              -- false for generic fishermen, guards, etc.
    notes           TEXT,
    metadata        JSONB
);

CREATE TABLE enemy (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(150) NOT NULL,
    enemy_type      VARCHAR(80),                       -- 'demon_lord','dragon','construct','hag','warlock','cultist'
    faction_id      INT REFERENCES faction(id),
    element_type_id INT REFERENCES element_type(id),
    threat_level_id INT REFERENCES threat_level(id),
    entity_status_id INT REFERENCES entity_status(id),
    first_encountered_session INT,                     -- FK added after session table
    description     TEXT,
    notes           TEXT,
    metadata        JSONB
);

CREATE TABLE artifact (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(150) NOT NULL,
    artifact_type_id INT REFERENCES artifact_type(id),
    description     TEXT,
    lore_significance TEXT,
    is_sentient     BOOLEAN DEFAULT FALSE,
    is_cursed       BOOLEAN DEFAULT FALSE,
    is_infernal     BOOLEAN DEFAULT FALSE,
    discovered_session INT,                            -- FK added after session table
    notes           TEXT,
    metadata        JSONB
);

CREATE TABLE lore_item (
    id              SERIAL PRIMARY KEY,
    title           VARCHAR(200) NOT NULL,
    category        VARCHAR(80),                       -- 'prophecy','history','divine','cosmology','faction_lore','well_knowledge'
    description     TEXT NOT NULL,
    source_npc_id   INT REFERENCES npc(id),            -- who revealed it (nullable = discovered via event)
    discovered_session INT,                            -- FK added after session table
    is_confirmed    BOOLEAN DEFAULT FALSE,
    notes           TEXT
);


-- =============================================================================
-- PARTY / CHARACTER TABLES
-- =============================================================================

CREATE TABLE player_character (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    player_name     VARCHAR(100),
    character_class_id INT REFERENCES character_class(id),
    character_race_id  INT REFERENCES character_race(id),
    is_active       BOOLEAN DEFAULT TRUE,
    background      TEXT,
    notes           TEXT
);

-- multiclass support
CREATE TABLE character_class_level (
    id              SERIAL PRIMARY KEY,
    character_id    INT NOT NULL REFERENCES player_character(id),
    character_class_id INT NOT NULL REFERENCES character_class(id),
    level           SMALLINT NOT NULL,
    UNIQUE (character_id, character_class_id)
);

CREATE TABLE character_attribute (
    id              SERIAL PRIMARY KEY,
    character_id    INT NOT NULL REFERENCES player_character(id),
    attribute_name  VARCHAR(50) NOT NULL,              -- 'STR','DEX','CON','INT','WIS','CHA'
    score           SMALLINT NOT NULL,
    UNIQUE (character_id, attribute_name)
);


-- =============================================================================
-- SESSION TABLES
-- =============================================================================

CREATE TABLE session (
    id              SERIAL PRIMARY KEY,
    session_number  SMALLINT NOT NULL UNIQUE,
    session_date    DATE,
    in_game_date    TEXT,                              -- flavor date/range, sometimes multiple in-world dates
    title           VARCHAR(200),
    summary         TEXT,
    party_level     SMALLINT,
    location_id     INT REFERENCES location(id),       -- primary location of session
    audio_file_path TEXT,                              -- path to wav
    transcript_path TEXT,                              -- path to whisper output
    notes           TEXT
);

-- now add forward-reference FKs deferred above
ALTER TABLE location       ADD CONSTRAINT fk_loc_first_session    FOREIGN KEY (first_visited_session)    REFERENCES session(id);
ALTER TABLE npc            ADD CONSTRAINT fk_npc_first_session     FOREIGN KEY (first_seen_session)       REFERENCES session(id);
ALTER TABLE enemy          ADD CONSTRAINT fk_enemy_first_session   FOREIGN KEY (first_encountered_session) REFERENCES session(id);
ALTER TABLE artifact       ADD CONSTRAINT fk_artifact_session      FOREIGN KEY (discovered_session)       REFERENCES session(id);
ALTER TABLE lore_item      ADD CONSTRAINT fk_lore_session          FOREIGN KEY (discovered_session)       REFERENCES session(id);


-- =============================================================================
-- ENTITY KNOWLEDGE / VISIBILITY
-- =============================================================================

CREATE TABLE entity_knowledge (
    id                  SERIAL PRIMARY KEY,
    entity_type         VARCHAR(50) NOT NULL CHECK (entity_type IN (
                            'artifact','npc','location','enemy','well','faction','lore_item','song'
                        )),
    entity_id           INT NOT NULL,                  -- polymorphic reference to the table named by entity_type
    subject_type        VARCHAR(50) NOT NULL CHECK (subject_type IN (
                            'dm','party','pc','npc','faction','public_world'
                        )),
    subject_character_id INT REFERENCES player_character(id),
    subject_npc_id      INT REFERENCES npc(id),
    subject_faction_id  INT REFERENCES faction(id),
    knowledge_state_id  INT NOT NULL REFERENCES knowledge_state(id),
    visibility_level_id INT NOT NULL REFERENCES visibility_level(id),
    first_known_session INT REFERENCES session(id),
    is_revealed_to_party BOOLEAN DEFAULT FALSE,
    notes               TEXT,
    metadata            JSONB,
    CONSTRAINT entity_knowledge_subject CHECK (
        (subject_type = 'pc' AND subject_character_id IS NOT NULL AND subject_npc_id IS NULL AND subject_faction_id IS NULL) OR
        (subject_type = 'npc' AND subject_character_id IS NULL AND subject_npc_id IS NOT NULL AND subject_faction_id IS NULL) OR
        (subject_type = 'faction' AND subject_character_id IS NULL AND subject_npc_id IS NULL AND subject_faction_id IS NOT NULL) OR
        (subject_type IN ('dm','party','public_world') AND subject_character_id IS NULL AND subject_npc_id IS NULL AND subject_faction_id IS NULL)
    )
);

CREATE UNIQUE INDEX unique_entity_knowledge_subject ON entity_knowledge (
    entity_type,
    entity_id,
    subject_type,
    COALESCE(subject_character_id, 0),
    COALESCE(subject_npc_id, 0),
    COALESCE(subject_faction_id, 0)
);


-- =============================================================================
-- SESSION EVENT TABLE  (the heart of the pipeline)
-- =============================================================================

CREATE TABLE session_event (
    id              SERIAL PRIMARY KEY,
    session_id      INT NOT NULL REFERENCES session(id),
    event_type_id   INT REFERENCES event_type(id),
    sequence_order  SMALLINT,                          -- order within session
    location_id     INT REFERENCES location(id),
    description     TEXT NOT NULL,
    significance    SMALLINT CHECK (significance BETWEEN 1 AND 5),  -- 1=minor, 5=critical
    notes           TEXT
);

-- M:M — events involve multiple characters
CREATE TABLE event_character (
    event_id        INT NOT NULL REFERENCES session_event(id),
    character_id    INT NOT NULL REFERENCES player_character(id),
    role            VARCHAR(80),                       -- 'primary','witness','affected','absent'
    PRIMARY KEY (event_id, character_id)
);

-- M:M — events involve multiple NPCs
CREATE TABLE event_npc (
    event_id        INT NOT NULL REFERENCES session_event(id),
    npc_id          INT NOT NULL REFERENCES npc(id),
    role            VARCHAR(80),                       -- 'encountered','helped','fled','revealed_info'
    PRIMARY KEY (event_id, npc_id)
);

-- M:M — events involve enemies
CREATE TABLE event_enemy (
    event_id        INT NOT NULL REFERENCES session_event(id),
    enemy_id        INT NOT NULL REFERENCES enemy(id),
    outcome         VARCHAR(50),                       -- 'defeated','fled','escaped','killed_party','summoned'
    quantity        SMALLINT,
    confidence      VARCHAR(30),
    notes           TEXT,
    PRIMARY KEY (event_id, enemy_id)
);

CREATE TABLE encounter (
    id              SERIAL PRIMARY KEY,
    session_id      INT NOT NULL REFERENCES session(id),
    event_id        INT REFERENCES session_event(id),
    encounter_type  VARCHAR(80) NOT NULL,              -- 'combat','social','hazard','travel','discovery'
    subtype         VARCHAR(100),
    location_id     INT REFERENCES location(id),
    title           VARCHAR(200) NOT NULL,
    participants    TEXT,
    outcome         VARCHAR(120),
    confidence      VARCHAR(30),
    notes           TEXT,
    UNIQUE (session_id, title)
);

-- M:M — events involve artifacts
CREATE TABLE event_artifact (
    event_id        INT NOT NULL REFERENCES session_event(id),
    artifact_id     INT NOT NULL REFERENCES artifact(id),
    interaction     VARCHAR(80),                       -- 'discovered','used','lost','given','received'
    PRIMARY KEY (event_id, artifact_id)
);

-- M:M — events involve wells
CREATE TABLE event_well (
    event_id        INT NOT NULL REFERENCES session_event(id),
    well_id         INT NOT NULL REFERENCES well(id),
    interaction     VARCHAR(80),                       -- 'discovered','stabilized','disturbed','spoken_to','carried'
    PRIMARY KEY (event_id, well_id)
);


-- =============================================================================
-- CHARACTER MILESTONE TABLE
-- =============================================================================

CREATE TABLE character_milestone (
    id              SERIAL PRIMARY KEY,
    character_id    INT NOT NULL REFERENCES player_character(id),
    session_id      INT NOT NULL REFERENCES session(id),
    milestone_type_id INT REFERENCES milestone_type(id),
    title           VARCHAR(200) NOT NULL,
    description     TEXT,
    significance    SMALLINT CHECK (significance BETWEEN 1 AND 5),
    related_event_id INT REFERENCES session_event(id)
);


-- =============================================================================
-- TRAVEL LOG
-- =============================================================================

CREATE TABLE travel_log (
    id                  SERIAL PRIMARY KEY,
    session_id          INT NOT NULL REFERENCES session(id),
    from_location_id    INT REFERENCES location(id),
    to_location_id      INT REFERENCES location(id),
    travel_method       VARCHAR(80),                   -- 'foot','horse','ship','portal','magical'
    duration_days       SMALLINT,
    duration_confidence VARCHAR(30),                    -- 'low','medium','high'
    duration_basis      TEXT,
    notes               TEXT
);


-- =============================================================================
-- ARTIFACT CUSTODY CHAIN  (who holds what, when)
-- =============================================================================

CREATE TABLE artifact_custody (
    id              SERIAL PRIMARY KEY,
    artifact_id     INT NOT NULL REFERENCES artifact(id),
    character_id    INT REFERENCES player_character(id),  -- null = NPC holds it
    npc_id          INT REFERENCES npc(id),               -- null = PC holds it
    session_id      INT NOT NULL REFERENCES session(id),
    acquired_event_id INT REFERENCES session_event(id),
    notes           TEXT,
    CONSTRAINT custody_holder CHECK (
        (character_id IS NOT NULL AND npc_id IS NULL) OR
        (character_id IS NULL AND npc_id IS NOT NULL) OR
        (character_id IS NULL AND npc_id IS NULL)      -- unknown/lost
    )
);


-- =============================================================================
-- NPC RELATIONSHIP TABLE
-- =============================================================================

CREATE TABLE npc_relationship (
    id                  SERIAL PRIMARY KEY,
    npc_id              INT NOT NULL REFERENCES npc(id),
    character_id        INT REFERENCES player_character(id),
    relationship_type_id INT REFERENCES relationship_type(id),
    established_session INT REFERENCES session(id),
    description         TEXT,
    UNIQUE (npc_id, character_id)
);

-- NPC to NPC relationships
CREATE TABLE npc_npc_relationship (
    id                  SERIAL PRIMARY KEY,
    npc_id_a            INT NOT NULL REFERENCES npc(id),
    npc_id_b            INT NOT NULL REFERENCES npc(id),
    relationship_type_id INT REFERENCES relationship_type(id),
    description         TEXT,
    CONSTRAINT no_self_relationship CHECK (npc_id_a <> npc_id_b)
);

CREATE UNIQUE INDEX unique_npc_pair ON npc_npc_relationship (
    LEAST(npc_id_a, npc_id_b),
    GREATEST(npc_id_a, npc_id_b)
);


-- =============================================================================
-- FABAN-SPECIFIC TABLES
-- =============================================================================

-- The Songbook
CREATE TABLE song (
    id              SERIAL PRIMARY KEY,
    song_number     SMALLINT UNIQUE,                   -- Faban's own numbering (1-26+)
    title           VARCHAR(200) NOT NULL,
    style_id        INT REFERENCES song_style(id),
    category_id     INT REFERENCES song_category(id),
    summary         TEXT,
    song_type       VARCHAR(120),                      -- exact editorial type/style from the revealed songbook
    short_description TEXT,                            -- compact editorial category/description
    long_description TEXT,                             -- songbook-facing description
    suno_prompt     TEXT,                              -- generation prompt used for Suno AI, if known
    musical_key     VARCHAR(120),                      -- e.g. 'D minor', 'G major'
    meter           VARCHAR(120),                      -- e.g. '4/4', '3/4', '6/8'
    tempo           VARCHAR(120),                      -- e.g. '90 BPM', '100-110 BPM'
    instrumentation TEXT,
    lyrics_local_path TEXT,                            -- local lyrics file if downloaded/curated
    lyrics_url      TEXT,                              -- Google Doc link
    mp3_url         TEXT,                              -- Google Drive link
    mp3_local_path  TEXT,                              -- local path if downloaded
    written_session INT REFERENCES session(id),        -- session it was composed (if known)
    in_world_context TEXT,                             -- why Faban wrote it
    is_performed    BOOLEAN DEFAULT TRUE               -- has an MP3 recording
);

-- Songs performed in-session
CREATE TABLE song_performance (
    id              SERIAL PRIMARY KEY,
    song_id         INT NOT NULL REFERENCES song(id),
    session_id      INT NOT NULL REFERENCES session(id),
    event_id        INT REFERENCES session_event(id),
    location_id     INT REFERENCES location(id),
    audience_notes  TEXT,                              -- who heard it, reaction
    effect          TEXT                               -- mechanical or narrative effect
);

CREATE TABLE songbook_front_matter (
    id              SERIAL PRIMARY KEY,
    title           VARCHAR(200) NOT NULL,
    foreword_path   TEXT,
    foreword_text   TEXT,
    notes           TEXT
);

-- Songs referencing campaign entities (lore connections)
CREATE TABLE song_entity_reference (
    id              SERIAL PRIMARY KEY,
    song_id         INT NOT NULL REFERENCES song(id),
    entity_type     VARCHAR(50) NOT NULL,              -- 'npc','enemy','location','artifact','well','faction','lore_item'
    entity_id       INT NOT NULL,                      -- polymorphic reference
    reference_notes TEXT
);

-- The Grimoire — tracked as artifact but with its own lore table
CREATE TABLE grimoire_entry (
    id              SERIAL PRIMARY KEY,
    artifact_id     INT NOT NULL REFERENCES artifact(id),  -- FK to the Grimoire artifact record
    entry_title     VARCHAR(200),
    content         TEXT,
    language        VARCHAR(50),                       -- 'old_common','celestial','arcane'
    is_deciphered   BOOLEAN DEFAULT FALSE,
    deciphered_session INT REFERENCES session(id),
    related_deity   VARCHAR(100),                      -- Siath, Goddess of Knowledge
    notes           TEXT
);

-- Faban's Diary entries
CREATE TABLE diary_entry (
    id              SERIAL PRIMARY KEY,
    character_id    INT NOT NULL REFERENCES player_character(id),
    session_id      INT REFERENCES session(id),
    in_game_date    TEXT,
    title           VARCHAR(200),
    content         TEXT NOT NULL,
    emotional_tone  VARCHAR(50),                       -- 'reflective','triumphant','uneasy','grieving','hopeful'
    word_count      INT,
    notes           TEXT
);

-- Diary entry entity mentions (extracted by pipeline)
CREATE TABLE diary_entity_mention (
    id              SERIAL PRIMARY KEY,
    diary_entry_id  INT NOT NULL REFERENCES diary_entry(id),
    entity_type     VARCHAR(50) NOT NULL,
    entity_id       INT NOT NULL,
    mention_context TEXT                               -- the sentence/phrase referencing the entity
);


-- =============================================================================
-- WELL STATUS HISTORY  (wells change state — track it)
-- =============================================================================

CREATE TABLE well_status_history (
    id              SERIAL PRIMARY KEY,
    well_id         INT NOT NULL REFERENCES well(id),
    session_id      INT NOT NULL REFERENCES session(id),
    well_status_id  INT NOT NULL REFERENCES well_status(id),
    changed_by      TEXT,                              -- who/what changed it
    notes           TEXT
);


-- =============================================================================
-- CAMPAIGN ARC TABLE
-- =============================================================================

CREATE TABLE campaign_arc (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(200) NOT NULL,             -- 'Bentrios','Feywild & First Well','Balrog','Catur'
    start_session   INT REFERENCES session(id),
    end_session     INT REFERENCES session(id),
    summary         TEXT,
    is_complete     BOOLEAN DEFAULT FALSE
);

CREATE TABLE arc_session (
    arc_id          INT NOT NULL REFERENCES campaign_arc(id),
    session_id      INT NOT NULL REFERENCES session(id),
    PRIMARY KEY (arc_id, session_id)
);


-- =============================================================================
-- THREAT TRACKER
-- =============================================================================

CREATE TABLE active_threat (
    id              SERIAL PRIMARY KEY,
    enemy_id        INT REFERENCES enemy(id),
    faction_id      INT REFERENCES faction(id),
    threat_level_id INT REFERENCES threat_level(id),
    description     TEXT,
    last_known_action TEXT,
    last_seen_session INT REFERENCES session(id),
    is_active       BOOLEAN DEFAULT TRUE
);


-- =============================================================================
-- PIPELINE METADATA  (track extraction runs — data scientist essential)
-- =============================================================================

CREATE TABLE pipeline_run (
    id              SERIAL PRIMARY KEY,
    run_timestamp   TIMESTAMPTZ DEFAULT NOW(),
    session_id      INT REFERENCES session(id),
    pipeline_stage  VARCHAR(80),                       -- 'transcription','extraction','normalization','tagging','summarization'
    model_used      VARCHAR(80),                       -- 'llama3.2','whisper-large-v3', etc.
    input_file      TEXT,
    output_file     TEXT,
    records_created INT,
    records_updated INT,
    success         BOOLEAN DEFAULT TRUE,
    error_message   TEXT,
    run_duration_ms INT
);

CREATE TABLE extraction_confidence (
    id              SERIAL PRIMARY KEY,
    pipeline_run_id INT NOT NULL REFERENCES pipeline_run(id),
    entity_type     VARCHAR(50) NOT NULL,
    entity_id       INT NOT NULL,
    confidence_score NUMERIC(4,3) CHECK (confidence_score BETWEEN 0 AND 1),
    needs_review    BOOLEAN DEFAULT FALSE,
    reviewed        BOOLEAN DEFAULT FALSE,
    reviewer_notes  TEXT
);


-- =============================================================================
-- INDEXES
-- =============================================================================

-- session lookups
CREATE INDEX idx_session_number           ON session(session_number);
CREATE INDEX idx_session_date             ON session(session_date);

-- entity status lookups (frequent filters)
CREATE INDEX idx_npc_status               ON npc(entity_status_id);
CREATE INDEX idx_npc_faction              ON npc(faction_id);
CREATE INDEX idx_enemy_status             ON enemy(entity_status_id);
CREATE INDEX idx_enemy_threat             ON enemy(threat_level_id);

-- event lookups
CREATE INDEX idx_event_session            ON session_event(session_id);
CREATE INDEX idx_event_type               ON session_event(event_type_id);
CREATE INDEX idx_event_location           ON session_event(location_id);

-- milestone lookups
CREATE INDEX idx_milestone_character      ON character_milestone(character_id);
CREATE INDEX idx_milestone_session        ON character_milestone(session_id);

-- artifact custody chain
CREATE INDEX idx_custody_artifact         ON artifact_custody(artifact_id);
CREATE INDEX idx_custody_character        ON artifact_custody(character_id);

-- song lookups
CREATE INDEX idx_song_number              ON song(song_number);
CREATE INDEX idx_song_performance_session ON song_performance(session_id);

-- diary lookups
CREATE INDEX idx_diary_session            ON diary_entry(session_id);
CREATE INDEX idx_diary_character          ON diary_entry(character_id);

-- pipeline metadata
CREATE INDEX idx_pipeline_session         ON pipeline_run(session_id);
CREATE INDEX idx_pipeline_stage           ON pipeline_run(pipeline_stage);
CREATE INDEX idx_extraction_needs_review  ON extraction_confidence(needs_review) WHERE needs_review = TRUE;

-- knowledge visibility
CREATE INDEX idx_entity_knowledge_entity  ON entity_knowledge(entity_type, entity_id);
CREATE INDEX idx_entity_knowledge_subject ON entity_knowledge(subject_type, subject_character_id, subject_npc_id, subject_faction_id);

-- JSONB indexes for metadata columns (GIN for containment queries)
CREATE INDEX idx_npc_metadata             ON npc USING GIN (metadata);
CREATE INDEX idx_artifact_metadata        ON artifact USING GIN (metadata);
CREATE INDEX idx_enemy_metadata           ON enemy USING GIN (metadata);
CREATE INDEX idx_location_metadata        ON location USING GIN (metadata);


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
    (5,  'Ranger Rick and his Mighty Stick',      (SELECT id FROM song_style WHERE style_name='tavern_song'),   (SELECT id FROM song_category WHERE category_name='humor'),            'Wildly exaggerated tavern tale of a legendary ranger',                                         'https://docs.google.com/document/d/1YNHoU8ECDqM3RZQZD_H3PPe46DpXbhKRKAyv0GPNiFc', 'https://drive.google.com/open?id=1sWTocCBdOQFP0KXEEbXKmdmRcH9SvRxW'),
    (6,  'The Braggart Baron Who Bought His Battles', (SELECT id FROM song_style WHERE style_name='ballad'),   (SELECT id FROM song_category WHERE category_name='political_satire'), 'Mocking tale of a noble who claims heroes'' victories as his own',                             'https://docs.google.com/document/d/19Y4dXB_1VaDuffPNqI4mhIZJNpdD4ha84AxJKH7rNMc', 'https://drive.google.com/open?id=1IjYCn_nJk62EHT3mStLvnu30Yq0xLwQK'),
    (7,  'The Fool Who Outsang the Devil',        (SELECT id FROM song_style WHERE style_name='tavern_song'),   (SELECT id FROM song_category WHERE category_name='humor'),            'Bard wins singing contest against a disguised devil using love and human joy',                 'https://docs.google.com/document/d/1RYYbUjm6-5Pfm4IKFsHH1DxVXGZomHQOiV1sx2W1O68', 'https://drive.google.com/open?id=1vW7RwhXRrZNvpJeZS9MjxRDO5Ncfk71D'),
    (8,  'Flight of the Fairies',                 (SELECT id FROM song_style WHERE style_name='ballad'),        (SELECT id FROM song_category WHERE category_name='fey_folklore'),    'Celebration of mysterious fair folk in moonlit glades',                                        'https://docs.google.com/document/d/1Skwh7hO1yXnPMZVDJu9H7VXGy7YX4tI113fw8eECrFE', 'https://drive.google.com/open?id=15bRsU8-NjRAwwDr3AwkDaVg2r98JI8QK'),
    (9,  'Don''t Step in the Fairy Ring',         (SELECT id FROM song_style WHERE style_name='ballad'),        (SELECT id FROM song_category WHERE category_name='fey_folklore'),    'Warning that fairy rings may carry travelers to lands from which they may never return',       'https://docs.google.com/document/d/1GIdk9tqU9-1oMCxR5QvhYTS1VxpVCeefBThULBd1q30', 'https://drive.google.com/open?id=1ge6wUOTL15nsZ1GLHzX52E9Gc8UGmrPt'),
    (10, 'The Stars and the Centaurs',            (SELECT id FROM song_style WHERE style_name='ballad'),        (SELECT id FROM song_category WHERE category_name='lore'),             'Mythic tale of how stars and wild plains gave birth to the centaur race',                      'https://docs.google.com/document/d/1gWb4GDqdmS-w-mih3VLbC8UMcCS00-HqJmup3YVBA5k', 'https://drive.google.com/open?id=19-y_H0JQ9o537r-uOO50op9Eih_7ZRw-'),
    (11, 'Urgan Wyrmbane',                        (SELECT id FROM song_style WHERE style_name='war_chant'),     (SELECT id FROM song_category WHERE category_name='heroic_saga'),     'Battle anthem of the fearless warrior Urgan',                                                  'https://docs.google.com/document/d/1Msz3r053Hnf0VSyXiH_I3-eL-QqZH1tte-lCevwDltk', 'https://drive.google.com/open?id=1zkpsIShGZWJbNZga9M9vvcDre'),
    (12, 'The Day We Called It Victory',          (SELECT id FROM song_style WHERE style_name='ballad'),        (SELECT id FROM song_category WHERE category_name='lament'),           'Somber reflection on the illusion of victory and the forgotten valor of the enemy',            'https://docs.google.com/document/d/1yu8oXILnBE96bWirVny1N3gR8MxXUaXlN4_E2aZaV1U', 'https://drive.google.com/open?id=13aeVQ6BtsyG4Ah7UOm-Rx'),
    (13, 'The Defense of the Watery Dunes',       (SELECT id FROM song_style WHERE style_name='ballad'),        (SELECT id FROM song_category WHERE category_name='heroic_saga'),     'Paramon defenders stood firm against a corrupted sea guardian',                                'https://docs.google.com/document/d/1tb3wCD85AEB80rGA0n8CLefbeD9KW7EN0Ticl7k5zes', 'https://drive.google.com/open?id=1gHTpG6_kbSIaGiAqfPhlBb4iz-Sx'),
    (14, 'The Fallen Few at Devilspawn Valley',   (SELECT id FROM song_style WHERE style_name='ballad'),        (SELECT id FROM song_category WHERE category_name='heroic_saga'),     'Small band held a mountain pass against overwhelming evil',                                    'https://docs.google.com/document/d/1zU5qss81ouJvBIXUbcrOwSsQ-z62O4jpbUYGSdE2cyw', 'https://drive.google.com/open?id=1-3vEBd0SzEAo_Our4ehuO1hQfhz3VjQB'),
    (15, 'The Lost Miners of Karadum',            (SELECT id FROM song_style WHERE style_name='ballad'),        (SELECT id FROM song_category WHERE category_name='lament'),           'Remembrance of miners who vanished beneath the mountain they loved',                           'https://docs.google.com/document/d/15URVU7HduuQrpR4jCp6IsTtEMNls5XmjE_e97KpLvOA', 'https://drive.google.com/open?id=1brS1r95Q51bCTafkOJXZAE4'),
    (16, 'The Battle of Flintrock',               (SELECT id FROM song_style WHERE style_name='ballad'),        (SELECT id FROM song_category WHERE category_name='lament'),           'Two armies from the same people slaughter one another for the pride of their kings',           'https://docs.google.com/document/d/12We74JidneZ6EMqtk3d-eP8KNgVKdGYUHphMaBdVUPE', 'https://drive.google.com/open?id=1IkiDgP6lJRtkz5uwRbv5nkAwXjeKReQ3'),
    (17, 'The Fate of the Emerald Eel',           (SELECT id FROM song_style WHERE style_name='sea_shanty'),    (SELECT id FROM song_category WHERE category_name='lore'),             'Doomed ship encounters cursed phantom vessel the Donny Bell',                                  'https://docs.google.com/document/d/153E_NNfZaRU9WfqnDae58AdLgnr_riTg0AjxNbTBGN8', 'https://drive.google.com/open?id=1hWOt0fcDParlZ4fwkfaCST1HTs7f6Yv5'),
    (18, 'The Contract of Baron Welles',          (SELECT id FROM song_style WHERE style_name='ballad'),        (SELECT id FROM song_category WHERE category_name='political_satire'), 'Warning tale: noble''s pact unleashes forces beyond control',                                  'https://docs.google.com/document/d/1KTaKIQIha1q9gtHuwRePZV-lhUgmgHYH7fIpAZCRo2g', 'https://drive.google.com/open?id=1PNGSD4ulixKd_BWT2nhtej_SNbpJzUe6'),
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

-- =============================================================================
-- USEFUL VIEWS
-- =============================================================================

-- Current well status overview
CREATE VIEW v_well_status AS
    SELECT w.name, l.name AS location, ws.status_code AS status,
           et.element_name AS element, w.notes
    FROM well w
    LEFT JOIN location l ON w.location_id = l.id
    LEFT JOIN well_status ws ON w.well_status_id = ws.id
    LEFT JOIN element_type et ON w.element_type_id = et.id
    ORDER BY w.id;

-- All active threats with detail
CREATE VIEW v_active_threats AS
    SELECT e.name, e.enemy_type, f.name AS faction,
           tl.level_code AS threat_level, at.description,
           at.last_known_action
    FROM active_threat at
    JOIN enemy e ON at.enemy_id = e.id
    LEFT JOIN faction f ON e.faction_id = f.id
    LEFT JOIN threat_level tl ON at.threat_level_id = tl.id
    WHERE at.is_active = TRUE
    ORDER BY tl.sort_order DESC;

-- Faban's current inventory
CREATE VIEW v_faban_inventory AS
    SELECT a.name, at2.type_name AS artifact_type,
           a.description, a.is_sentient, a.is_cursed, a.is_infernal,
           ac.notes AS acquisition_notes
    FROM artifact_custody ac
    JOIN artifact a ON ac.artifact_id = a.id
    JOIN artifact_type at2 ON a.artifact_type_id = at2.id
    JOIN player_character pc ON ac.character_id = pc.id
    WHERE pc.name = 'Faban Colon'
    ORDER BY a.name;

-- Songbook with performance tracking
CREATE VIEW v_songbook AS
    SELECT s.song_number, s.title, ss.style_name AS style,
           sc.category_name AS category, s.song_type, s.short_description,
           s.long_description, s.summary, s.suno_prompt, s.musical_key,
           s.meter, s.tempo, s.instrumentation,
           COUNT(sp.id) AS times_performed,
           s.lyrics_local_path, s.mp3_local_path, s.mp3_url, s.lyrics_url
    FROM song s
    LEFT JOIN song_style ss ON s.style_id = ss.id
    LEFT JOIN song_category sc ON s.category_id = sc.id
    LEFT JOIN song_performance sp ON s.id = sp.song_id
    GROUP BY s.id, s.song_number, s.title, ss.style_name, sc.category_name, s.song_type,
             s.short_description, s.long_description, s.summary, s.suno_prompt, s.musical_key,
             s.meter, s.tempo, s.instrumentation, s.lyrics_local_path, s.mp3_local_path, s.mp3_url, s.lyrics_url
    ORDER BY s.song_number;

-- Party milestone timeline
CREATE VIEW v_milestone_timeline AS
    SELECT pc.name AS character, s.session_number, s.in_game_date,
           mt.type_name AS milestone_type, cm.title, cm.description, cm.significance
    FROM character_milestone cm
    JOIN player_character pc ON cm.character_id = pc.id
    JOIN session s ON cm.session_id = s.id
    LEFT JOIN milestone_type mt ON cm.milestone_type_id = mt.id
    ORDER BY s.session_number, cm.significance DESC;

-- Pipeline health check
CREATE VIEW v_pipeline_health AS
    SELECT pr.pipeline_stage, COUNT(*) AS total_runs,
           SUM(CASE WHEN pr.success THEN 1 ELSE 0 END) AS successful,
           SUM(CASE WHEN NOT pr.success THEN 1 ELSE 0 END) AS failed,
           AVG(pr.run_duration_ms) AS avg_duration_ms,
           COUNT(ec.id) AS extractions_needing_review
    FROM pipeline_run pr
    LEFT JOIN extraction_confidence ec ON pr.id = ec.pipeline_run_id AND ec.needs_review = TRUE
    GROUP BY pr.pipeline_stage
    ORDER BY pr.pipeline_stage;
