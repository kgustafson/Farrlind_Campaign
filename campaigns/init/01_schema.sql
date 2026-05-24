-- =============================================================================
-- CAMPAIGN DATABASE UNIVERSAL SCHEMA
-- Full 3NF PostgreSQL Schema shared by every named campaign.
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

CREATE TABLE combat_outcome (
    id              SERIAL PRIMARY KEY,
    outcome_code    VARCHAR(80) NOT NULL UNIQUE,
    description     TEXT
);

CREATE TABLE workflow_status_state (
    id              SERIAL PRIMARY KEY,
    status_code     VARCHAR(80) NOT NULL UNIQUE,
    description     TEXT
);

CREATE TABLE artifact_flag (
    id              SERIAL PRIMARY KEY,
    flag_code       VARCHAR(80) NOT NULL UNIQUE,
    description     TEXT
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
    parent_location_id INT REFERENCES location(id),   -- region hierarchy
    description     TEXT,
    is_underwater   BOOLEAN DEFAULT FALSE,
    is_feywild      BOOLEAN DEFAULT FALSE,
    first_visited_session INT,                         -- FK added after session table created
    notes           TEXT,
    metadata        JSONB                              -- flex for DM-side details
);

CREATE TABLE well (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL UNIQUE,
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
    alias           VARCHAR(150),                      -- nicknames, titles, or spelling variants
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
    start_location_id INT REFERENCES location(id),      -- where the party begins the session
    end_location_id   INT REFERENCES location(id),      -- where the party ends the session
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
    quantity_killed SMALLINT,
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
    song_number     SMALLINT UNIQUE,
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
    in_world_context TEXT,                             -- in-world reason the song was written
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

-- Session diary entries
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
    name            VARCHAR(200) NOT NULL,
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
-- OPEN THREADS  (unresolved campaign mysteries, promises, hooks, and ambiguities)
-- =============================================================================

CREATE TABLE open_thread (
    id                  SERIAL PRIMARY KEY,
    title               TEXT NOT NULL UNIQUE,
    thread_type         VARCHAR(80) NOT NULL DEFAULT 'lore_mystery',
    status              VARCHAR(30) NOT NULL DEFAULT 'open'
                            CHECK (status IN ('open', 'resolved', 'superseded', 'unknown')),
    first_session_id    INT REFERENCES session(id),
    last_session_id     INT REFERENCES session(id),
    related_location_id INT REFERENCES location(id),
    description         TEXT,
    resolution          TEXT,
    notes               TEXT
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
-- WORKFLOW STATE  (per-session operational progress)
-- =============================================================================

CREATE TABLE workflow_run (
    id                  SERIAL PRIMARY KEY,
    session_id          INT NOT NULL REFERENCES session(id),
    workflow_id         VARCHAR(120) NOT NULL,
    workflow_version    INT NOT NULL,
    workflow_name       TEXT,
    status              VARCHAR(30) NOT NULL DEFAULT 'initialized',
    initiated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    summary_comment     TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(session_id, workflow_id, workflow_version)
);

CREATE TABLE workflow_step_state (
    id                  SERIAL PRIMARY KEY,
    workflow_run_id     INT NOT NULL REFERENCES workflow_run(id) ON DELETE CASCADE,
    step_id             VARCHAR(120) NOT NULL,
    step_order          INT NOT NULL,
    display_name        TEXT NOT NULL,
    lane                VARCHAR(80),
    status              VARCHAR(30) NOT NULL DEFAULT 'pending',
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    summary_comment     TEXT,
    inputs              JSONB NOT NULL DEFAULT '[]'::jsonb,
    outputs             JSONB NOT NULL DEFAULT '[]'::jsonb,
    dependencies        JSONB NOT NULL DEFAULT '[]'::jsonb,
    gate                VARCHAR(80),
    rerun_policy        VARCHAR(80),
    canon_impact        VARCHAR(80),
    command             TEXT,
    status_rules        JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(workflow_run_id, step_id)
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

-- workflow state
CREATE INDEX idx_workflow_run_session     ON workflow_run(session_id);
CREATE INDEX idx_workflow_run_identity    ON workflow_run(workflow_id, workflow_version);
CREATE INDEX idx_workflow_run_status      ON workflow_run(status);
CREATE INDEX idx_workflow_step_run_order  ON workflow_step_state(workflow_run_id, step_order);
CREATE INDEX idx_workflow_step_status     ON workflow_step_state(status);

-- knowledge visibility
CREATE INDEX idx_entity_knowledge_entity  ON entity_knowledge(entity_type, entity_id);
CREATE INDEX idx_entity_knowledge_subject ON entity_knowledge(subject_type, subject_character_id, subject_npc_id, subject_faction_id);

-- JSONB indexes for metadata columns (GIN for containment queries)
CREATE INDEX idx_npc_metadata             ON npc USING GIN (metadata);
CREATE INDEX idx_artifact_metadata        ON artifact USING GIN (metadata);
CREATE INDEX idx_enemy_metadata           ON enemy USING GIN (metadata);
CREATE INDEX idx_location_metadata        ON location USING GIN (metadata);


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

-- Current artifact custody by character
CREATE VIEW v_character_inventory AS
    SELECT pc.name AS character_name, a.name, at2.type_name AS artifact_type,
           a.description, a.is_sentient, a.is_cursed, a.is_infernal,
           ac.notes AS acquisition_notes
    FROM artifact_custody ac
    JOIN artifact a ON ac.artifact_id = a.id
    JOIN artifact_type at2 ON a.artifact_type_id = at2.id
    JOIN player_character pc ON ac.character_id = pc.id
    ORDER BY pc.name, a.name;

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
