-- Generated from campaign lookup_overrides.yaml by web_review.services.canon.
-- Intended for fresh campaign database initialization after generic lookup seeds.

-- Artifact Types
DELETE FROM artifact_type WHERE type_name NOT IN ('armor', 'axe', 'bow', 'cap', 'container', 'feature', 'grimoire', 'magic item', 'orb', 'other', 'relic', 'shield', 'spell', 'staff', 'tool', 'treasure', 'trinket', 'wand', 'weapon');
INSERT INTO artifact_type (type_name) VALUES ('armor') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO artifact_type (type_name) VALUES ('axe') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO artifact_type (type_name) VALUES ('bow') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO artifact_type (type_name) VALUES ('cap') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO artifact_type (type_name) VALUES ('container') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO artifact_type (type_name) VALUES ('feature') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO artifact_type (type_name) VALUES ('grimoire') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO artifact_type (type_name) VALUES ('magic item') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO artifact_type (type_name) VALUES ('orb') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO artifact_type (type_name) VALUES ('other') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO artifact_type (type_name) VALUES ('relic') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO artifact_type (type_name) VALUES ('shield') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO artifact_type (type_name) VALUES ('spell') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO artifact_type (type_name) VALUES ('staff') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO artifact_type (type_name) VALUES ('tool') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO artifact_type (type_name) VALUES ('treasure') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO artifact_type (type_name) VALUES ('trinket') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO artifact_type (type_name) VALUES ('wand') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO artifact_type (type_name) VALUES ('weapon') ON CONFLICT (type_name) DO NOTHING;

-- Location Types
DELETE FROM location_type WHERE type_name NOT IN ('building', 'city', 'coastal', 'dungeon', 'dwarven_hold', 'feywild', 'inn', 'island', 'landmark', 'monastery', 'realm', 'road', 'settlement', 'tavern', 'temple', 'town', 'underwater', 'wilderness');
INSERT INTO location_type (type_name) VALUES ('building') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO location_type (type_name) VALUES ('city') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO location_type (type_name) VALUES ('coastal') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO location_type (type_name) VALUES ('dungeon') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO location_type (type_name) VALUES ('dwarven_hold') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO location_type (type_name) VALUES ('feywild') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO location_type (type_name) VALUES ('inn') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO location_type (type_name) VALUES ('island') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO location_type (type_name) VALUES ('landmark') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO location_type (type_name) VALUES ('monastery') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO location_type (type_name) VALUES ('realm') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO location_type (type_name) VALUES ('road') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO location_type (type_name) VALUES ('settlement') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO location_type (type_name) VALUES ('tavern') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO location_type (type_name) VALUES ('temple') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO location_type (type_name) VALUES ('town') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO location_type (type_name) VALUES ('underwater') ON CONFLICT (type_name) DO NOTHING;
INSERT INTO location_type (type_name) VALUES ('wilderness') ON CONFLICT (type_name) DO NOTHING;

-- Combat Outcomes
DELETE FROM combat_outcome WHERE outcome_code NOT IN ('captured', 'defeated', 'escaped', 'fled', 'killed', 'summoned', 'unknown');
INSERT INTO combat_outcome (outcome_code, description) VALUES ('captured', 'Enemy was captured.') ON CONFLICT (outcome_code) DO UPDATE SET description = EXCLUDED.description;
INSERT INTO combat_outcome (outcome_code, description) VALUES ('defeated', 'Enemy or encounter was overcome.') ON CONFLICT (outcome_code) DO UPDATE SET description = EXCLUDED.description;
INSERT INTO combat_outcome (outcome_code, description) VALUES ('escaped', 'Enemy escaped the encounter.') ON CONFLICT (outcome_code) DO UPDATE SET description = EXCLUDED.description;
INSERT INTO combat_outcome (outcome_code, description) VALUES ('fled', 'Enemy fled the encounter.') ON CONFLICT (outcome_code) DO UPDATE SET description = EXCLUDED.description;
INSERT INTO combat_outcome (outcome_code, description) VALUES ('killed', 'Enemy was killed.') ON CONFLICT (outcome_code) DO UPDATE SET description = EXCLUDED.description;
INSERT INTO combat_outcome (outcome_code, description) VALUES ('summoned', 'Enemy was summoned or appeared.') ON CONFLICT (outcome_code) DO UPDATE SET description = EXCLUDED.description;
INSERT INTO combat_outcome (outcome_code, description) VALUES ('unknown', 'Outcome has not been established.') ON CONFLICT (outcome_code) DO UPDATE SET description = EXCLUDED.description;

-- NPC Status
DELETE FROM entity_status WHERE status_code NOT IN ('alive', 'dead', 'fled', 'imprisoned', 'missing', 'unknown');
INSERT INTO entity_status (status_code, description) VALUES ('alive', 'Confirmed living') ON CONFLICT (status_code) DO UPDATE SET description = EXCLUDED.description;
INSERT INTO entity_status (status_code, description) VALUES ('dead', 'Confirmed dead') ON CONFLICT (status_code) DO UPDATE SET description = EXCLUDED.description;
INSERT INTO entity_status (status_code, description) VALUES ('fled', 'Escaped encounter') ON CONFLICT (status_code) DO UPDATE SET description = EXCLUDED.description;
INSERT INTO entity_status (status_code, description) VALUES ('imprisoned', 'Captured or confined') ON CONFLICT (status_code) DO UPDATE SET description = EXCLUDED.description;
INSERT INTO entity_status (status_code, description) VALUES ('missing', 'Last known location unknown') ON CONFLICT (status_code) DO UPDATE SET description = EXCLUDED.description;
INSERT INTO entity_status (status_code, description) VALUES ('unknown', 'Status not confirmed') ON CONFLICT (status_code) DO UPDATE SET description = EXCLUDED.description;

-- Workflow Status States
DELETE FROM workflow_status_state WHERE status_code NOT IN ('blocked', 'completed', 'failed', 'initialized', 'needs_attention', 'partially_completed', 'pending', 'running', 'skipped');
INSERT INTO workflow_status_state (status_code, description) VALUES ('blocked', 'Step cannot proceed until a blocker is cleared.') ON CONFLICT (status_code) DO UPDATE SET description = EXCLUDED.description;
INSERT INTO workflow_status_state (status_code, description) VALUES ('completed', 'Step or workflow completed successfully.') ON CONFLICT (status_code) DO UPDATE SET description = EXCLUDED.description;
INSERT INTO workflow_status_state (status_code, description) VALUES ('failed', 'Step or workflow failed.') ON CONFLICT (status_code) DO UPDATE SET description = EXCLUDED.description;
INSERT INTO workflow_status_state (status_code, description) VALUES ('initialized', 'Workflow has been created but not started.') ON CONFLICT (status_code) DO UPDATE SET description = EXCLUDED.description;
INSERT INTO workflow_status_state (status_code, description) VALUES ('needs_attention', 'Human attention is required.') ON CONFLICT (status_code) DO UPDATE SET description = EXCLUDED.description;
INSERT INTO workflow_status_state (status_code, description) VALUES ('partially_completed', 'Workflow has completed some but not all steps.') ON CONFLICT (status_code) DO UPDATE SET description = EXCLUDED.description;
INSERT INTO workflow_status_state (status_code, description) VALUES ('pending', 'Step is waiting to run.') ON CONFLICT (status_code) DO UPDATE SET description = EXCLUDED.description;
INSERT INTO workflow_status_state (status_code, description) VALUES ('running', 'Step is currently running.') ON CONFLICT (status_code) DO UPDATE SET description = EXCLUDED.description;
INSERT INTO workflow_status_state (status_code, description) VALUES ('skipped', 'Step was intentionally skipped.') ON CONFLICT (status_code) DO UPDATE SET description = EXCLUDED.description;

-- Artifact Flags
DELETE FROM artifact_flag WHERE flag_code NOT IN ('cursed', 'infernal', 'sentient');
INSERT INTO artifact_flag (flag_code, description) VALUES ('cursed', 'Artifact carries a harmful curse.') ON CONFLICT (flag_code) DO UPDATE SET description = EXCLUDED.description;
INSERT INTO artifact_flag (flag_code, description) VALUES ('infernal', 'Artifact has infernal origin, influence, or binding.') ON CONFLICT (flag_code) DO UPDATE SET description = EXCLUDED.description;
INSERT INTO artifact_flag (flag_code, description) VALUES ('sentient', 'Artifact has awareness or agency.') ON CONFLICT (flag_code) DO UPDATE SET description = EXCLUDED.description;
