import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPT_DIR = REPO_ROOT / "model_eval" / "prompts"

MODELS = [
    "gemma3:latest",
    "gemma4:e2b",
    "gemma4:e4b",
]

VARIANTS = [
    {
        "version": "v04",
        "focus": "Use the canon glossary aggressively. Normalize obvious transcript spelling drift, especially Catur/Kator/Couture/Peter.",
        "rule": "When a transcript name resembles a known glossary term, use the glossary term and list the heard variant under uncertainties.",
    },
    {
        "version": "v05",
        "focus": "Prefer high-signal canon facts over long exhaustive lists. Separate facts from table chatter and speculation.",
        "rule": "Every bullet must describe an in-world fact, resource, location, NPC/entity, lore item, or unresolved thread.",
    },
    {
        "version": "v06",
        "focus": "Improve NPC/entity extraction and distinguish people, factions, monsters, gods, wells, and vague speakers.",
        "rule": "Do not add player names, table participants, or generic speakers unless they are also in-world characters or entities.",
    },
    {
        "version": "v07",
        "focus": "Improve chronology and travel continuity. Preserve where the party starts, travels, arrives, and ends.",
        "rule": "The summary and Key Events must be chronological and must not reorder late-session well events before travel/social events.",
    },
    {
        "version": "v08",
        "focus": "Improve inventory, artifacts, and exact numbers. Capture owners only when supported and avoid converting totals into fake charges.",
        "rule": "Do not treat consumable counts as item charges unless the transcript says charges.",
    },
    {
        "version": "v09",
        "focus": "Improve uncertainty handling and conflict resolution. Preserve ambiguity without allowing it to overwrite known canon terms.",
        "rule": "If a chunk says Kator/Couture/Peter but glossary says Catur, write Catur and add the heard variant to Uncertainties.",
    },
    {
        "version": "v10",
        "focus": "Best combined prompt: glossary normalization, chronology, NPC/entity extraction, resources, and concise final synthesis.",
        "rule": "Optimize for the lowest human cleanup burden: useful, specific, chronological, and conservative.",
    },
]

GLOSSARY = """## Session 21 Canon Glossary

Use these as preferred spellings when the transcript is close or ambiguous:

- Catur: the underwater city about six miles offshore. Prefer this over Kator, Couture, Peter, Cater, or similar transcript drift.
- Coast near Catur: the party's starting coastal location before taking the boat.
- Catur's Well Chamber: underwater cave/chamber containing the dormant magical well or pool.
- Faban, Mikani, Brigit, Roon, Gildas, Corvinus, Rune: party/member names.
- Namaloa: deity/belief referenced in the diplomatic ruse.
- Allister: merchant who warned that Catur is dangerous and hostile to outsiders.
- Uthgar: smith/smith contact in Catur. Prefer this over Utgar.
- Queen of Catur / Her Majesty of Catur: ruler who allowed access to the well.
- Niebain / Nebain: uncertain aboleth-like entity name. If the transcript suggests Nebane/Nebeth, preserve uncertainty but prefer Niebain/Nebain.
- Locathah: D&D fish race if fish people are mentioned generally.
- Celestial Isles: dragonkin society, constitutional monarchy.
- Mensen: gold dragonborn high clan ruling the Celestial Isles.
- Korog, Safi / Scythe, Ordor: known wells. Ordor was destroyed in Paramon.
- Wand of Wells: stolen artifact central to the threat.
- Acheron Blade: Faban's +1 weapon with Dark Blessing and Disheartening Strike properties.
- Cap of Water Breathing: activated with Kokyu.
"""


CHUNK_TEMPLATE = """# Farrlind Transcript Chunk Extraction Prompt {version}

You are the Farrlind campaign archivist reading one chunk from Session 21.

Your task is to mine this chunk for campaign canon facts that can later be merged into a final review packet.

{glossary}

## Variant Focus

{focus}

## Rules

- Use only facts supported by this chunk.
- {rule}
- Normalize obvious transcript spelling drift using the glossary, but list the heard variant under `## Uncertainties`.
- Do not critique the transcript.
- Do not discuss players, GM, performance, themes, or future plot advice.
- Ignore table chatter unless it affects in-world canon.
- Ignore repeated transcript noise unless it confirms an important fact.
- Capture exact numbers, resources, distances, durations, passwords, item properties, and names.
- Include NPCs/entities even if unnamed, hostile, monstrous, divine, telepathic, or titled.
- If a section has no supported facts, write `- None identified.`

## Required Output

Begin with `# Chunk Canon Extract`.

Use exactly these headings:

# Chunk Canon Extract

## Events

Chronological bullets for in-world actions, decisions, discoveries, encounters, travel, and cliffhanger developments.

## Locations

Bullets in this form:

- **Location Name** - What happened there or why it matters.

## NPCs / Entities

Bullets in this form:

- **Name or Description** - Role, action, relationship, or uncertainty.

## Lore

Bullets for worldbuilding, histories, factions, gods, city politics, races/species, wells, planes, and threats.

## Inventory / Resources

Bullets for counts, consumables, magic item properties, equipment, distances, durations, passphrases, charges, or other resources.

## Artifacts / Magic Items

Bullets in this form:

- **Item Name** - Owner if known; properties or significance.

## Open Threads / Threats

Bullets for unresolved mysteries, warnings, threats, promises, cliffhangers, or canon ambiguities.

## Uncertainties

Bullets for unclear spellings, names, counts, locations, transcription errors, or facts needing human review.

The transcript chunk begins after this line.
"""

SYNTHESIS_TEMPLATE = """# Farrlind Chunk Synthesis Prompt {version}

You are the Farrlind campaign archivist. You are receiving extracted canon notes from multiple transcript chunks for Session 21.

Your task is to merge the chunk extracts into one final canon review packet.

{glossary}

## Variant Focus

{focus}

## Merge Rules

- Use only facts present in the chunk extracts.
- {rule}
- Normalize obvious transcript spelling drift using the glossary, but list the heard variant under `## Uncertainties`.
- Consolidate duplicates.
- Preserve chronology.
- Prefer specific campaign facts over generic summaries.
- If chunks disagree, keep the more specific version and list the conflict under `## Uncertainties`.
- Do not invent missing names, counts, locations, motives, or outcomes.
- Do not write about players, GM, transcript quality, literary themes, or future story advice.
- Keep the output useful for human review and later database loading.

## Required Output

Your response must begin with `# Session Summary`.

Use exactly these headings, in this exact order:

# Session Summary

Write 6-12 concise paragraphs in chronological order. Cover the beginning situation, party decisions, travel, social encounters, discoveries, lore, resources, threats, and ending cliffhanger. Do not write diary prose.

## Key Events

Write 8-18 chronological bullets. Each bullet must be a complete campaign fact.

## Key Locations

Write bullets in this form:

- **Location Name** - Why it mattered in this session.

## Key NPCs / Entities

Write bullets in this form:

- **Name or Description** - Role in the session; first known detail; uncertainty if any.

## Important Lore

Write bullets for worldbuilding facts learned or reinforced.

## Inventory / Resource Notes

Write bullets for explicit resources, counts, consumables, magic items, equipment properties, passphrases, distances, durations, or limits.

## Artifacts / Magic Items

Write bullets in this form:

- **Item Name** - Owner if known; properties or significance.

## Open Threads Resolved

Write bullets for mysteries, promises, threats, or questions that appear resolved. If none are supported, write exactly:

- None identified.

## New Open Threads

Write bullets for newly introduced or continuing unresolved problems. Include cliffhangers and canon ambiguities. If none are supported, write exactly:

- None identified.

## Uncertainties

Write bullets for unclear names, spellings, counts, locations, conflicting extracts, or facts needing human review. If none are supported, write exactly:

- None identified.

The chunk extracts begin after this line. Synthesize only from these extracts.
"""


def write_prompts() -> list[dict[str, str]]:
    prompt_pairs = []
    for variant in VARIANTS:
        version = variant["version"]
        chunk_path = PROMPT_DIR / f"prompt_{version}_chunk.md"
        synthesis_path = PROMPT_DIR / f"prompt_{version}_synthesis.md"
        values = {
            "version": version,
            "focus": variant["focus"],
            "rule": variant["rule"],
            "glossary": GLOSSARY,
        }
        chunk_path.write_text(CHUNK_TEMPLATE.format(**values), encoding="utf-8")
        synthesis_path.write_text(SYNTHESIS_TEMPLATE.format(**values), encoding="utf-8")
        prompt_pairs.append(
            {
                "version": version,
                "chunk": str(chunk_path.relative_to(REPO_ROOT)),
                "synthesis": str(synthesis_path.relative_to(REPO_ROOT)),
            }
        )
    return prompt_pairs


def run_command(command: list[str], log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as log:
        log.write("\n$ " + " ".join(command) + "\n")
        log.flush()
        subprocess.run(command, cwd=REPO_ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)


def main() -> None:
    prompt_pairs = write_prompts()
    log_dir = REPO_ROOT / "logs" / "model_eval_overnight"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "prompt_pairs.json").write_text(__import__("json").dumps(prompt_pairs, indent=2), encoding="utf-8")
    for pair in prompt_pairs:
        version = pair["version"]
        run_command(
            [
                "./rag-env/bin/python",
                "scripts/model_eval_run.py",
                "--session",
                "session21",
                "--chunk-prompt",
                pair["chunk"],
                "--synthesis-prompt",
                pair["synthesis"],
            ],
            log_dir / f"{version}_run.log",
        )
        run_command(
            [
                "./rag-env/bin/python",
                "scripts/model_eval_score.py",
                "--prompt-version",
                f"prompt_{version}_synthesis",
                "--session",
                "session21",
            ],
            log_dir / f"{version}_score.log",
        )


if __name__ == "__main__":
    main()
