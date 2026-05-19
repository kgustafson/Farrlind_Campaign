import argparse
import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_HEADINGS = [
    "# Session Summary",
    "## Key Events",
    "## Key Locations",
    "## Key NPCs / Entities",
    "## Important Lore",
    "## Inventory / Resource Notes",
    "## Artifacts / Magic Items",
    "## Open Threads Resolved",
    "## New Open Threads",
    "## Uncertainties",
]

GOLD_FACTS = [
    ("dragon fight and recovered well", ["dragon", "well"]),
    ("fiendish/celestial ancient items may persuade wells", ["fiendish", "celestial", "persuade"]),
    ("orb of control fragments", ["orb", "control", "fragment"]),
    ("outer islands under unnatural stress", ["outer islands", "stress"]),
    ("Cap of Water Breathing activated by Kokyu", ["cap of water breathing", "kokyu"]),
    ("Shortbow of Warning", ["shortbow of warning", "short bow of warning"]),
    ("Roon's +2 dwarven shield", ["roon", "shield"]),
    ("Gildas Staff of Defense", ["gildas", "staff of defense"]),
    ("Corvinus flame longsword works underwater", ["corvinus", "flame", "underwater"]),
    ("Faban Acheron Blade +1", ["faban", "acheron blade"]),
    ("28 mushrooms and 20 potions", ["28", "mushrooms", "20", "potions"]),
    ("Catur six miles offshore underwater", ["catur", "six miles", "underwater"]),
    ("giant fishermen warned about Catur", ["giant fishermen", "warn"]),
    ("Mikani emissary from Celestial Isles", ["mikani", "emissary", "celestial isles"]),
    ("Corvinus oath limits deception", ["corvinus", "oath", "deception"]),
    ("Rune handled the boat", ["rune", "boat"]),
    ("Celestial Isles dragonkin constitutional monarchy", ["celestial isles", "dragon", "constitutional monarchy"]),
    ("Mensen gold dragonborn high clan", ["mensen", "gold", "dragonborn"]),
    ("Catur cultivated coral/mushrooms/gardens", ["catur", "coral", "mushroom"]),
    ("Uthgar smith contact", ["uthgar", "smith"]),
    ("Queen of Catur allowed well access", ["queen", "catur", "well"]),
    ("Catur well chamber/pool of magic", ["well chamber", "pool of magic"]),
    ("known wells Korog Safi Ordor Gale Hanidal Catur", ["korog", "safi", "ordor"]),
    ("Wand of Wells stolen", ["wand of wells", "stolen"]),
    ("aboleth Niebain/Nebain telepathic warning", ["aboleth", "danger"]),
    ("water rushed in through crack cliffhanger", ["water", "rushing", "crack"]),
]

BAD_PATTERNS = [
    ("wrong Catur variant: Kator", r"\bKator\b"),
    ("wrong Catur variant: Couture", r"\bCouture\b"),
    ("wrong Catur variant: Peter", r"\bPeter\b"),
    ("wrong Gildas variant: Gildos", r"\bGildos\b"),
    ("wrong Uthgar variant: Utgar", r"\bUtgar\b"),
    ("generic transcript commentary", r"transcript|role-playing session|RPG session|players|GM|potential next steps|themes"),
    ("unsupported Cthulhu framing", r"\bCthulhu\b|Lovecraft"),
]


def normalize(text: str) -> str:
    text = text.lower()
    text = text.replace("short bow", "shortbow")
    return re.sub(r"\s+", " ", text)


def has_any(text: str, options: list[str]) -> bool:
    return any(option in text for option in options)


def fact_matched(text: str, terms: list[str]) -> bool:
    return all(has_any(text, [term.lower()]) for term in terms)


def score_output(output_text: str) -> dict[str, Any]:
    normalized = normalize(output_text)
    heading_hits = [heading for heading in REQUIRED_HEADINGS if heading in output_text]
    fact_hits = [name for name, terms in GOLD_FACTS if fact_matched(normalized, terms)]
    penalties = []
    penalty_points = 0
    for label, pattern in BAD_PATTERNS:
        matches = re.findall(pattern, output_text, flags=re.IGNORECASE)
        if matches:
            count = len(matches)
            penalties.append({"label": label, "count": count})
            penalty_points += min(8, count * 2)

    word_count = len(re.findall(r"\b\w+\b", output_text))
    if word_count < 500:
        penalties.append({"label": "too short", "count": 1})
        penalty_points += 20
    if word_count > 3500:
        penalties.append({"label": "too long", "count": 1})
        penalty_points += 5

    heading_score = len(heading_hits) * 3
    fact_score = len(fact_hits) * 4
    total = max(0, heading_score + fact_score - penalty_points)
    return {
        "score": total,
        "heading_score": heading_score,
        "fact_score": fact_score,
        "penalty_points": penalty_points,
        "word_count": word_count,
        "headings_present": heading_hits,
        "facts_matched": fact_hits,
        "penalties": penalties,
    }


def load_metadata(output_path: Path) -> dict[str, Any]:
    metadata_path = output_path.with_name(output_path.name.replace("_output.md", "_metadata.json"))
    if metadata_path.exists():
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    return {}


def score_prompt(prompt_version: str, session: str) -> dict[str, Any]:
    results = []
    for output_path in sorted((REPO_ROOT / "model_eval" / "runs").glob(f"*/{prompt_version}/{session}_output.md")):
        output_text = output_path.read_text(encoding="utf-8")
        metadata = load_metadata(output_path)
        scored = score_output(output_text)
        scored.update(
            {
                "model": metadata.get("model", output_path.parts[-3]),
                "duration_seconds": metadata.get("duration_seconds"),
                "output": str(output_path.relative_to(REPO_ROOT)),
                "prompt_version": prompt_version,
                "session": session,
            }
        )
        results.append(scored)
    results.sort(key=lambda row: (row["score"], -(row.get("duration_seconds") or 0)), reverse=True)
    return {"prompt_version": prompt_version, "session": session, "results": results}


def write_scorecard(scorecard: dict[str, Any]) -> None:
    out_dir = REPO_ROOT / "model_eval" / "scorecards"
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt_version = scorecard["prompt_version"]
    session = scorecard["session"]
    json_path = out_dir / f"{prompt_version}_{session}_scorecard.json"
    md_path = out_dir / f"{prompt_version}_{session}_scorecard.md"
    json_path.write_text(json.dumps(scorecard, indent=2), encoding="utf-8")

    lines = [f"# {prompt_version} {session} Scorecard", ""]
    lines.append("| Rank | Model | Score | Time | Words | Penalties | Output |")
    lines.append("|---:|---|---:|---:|---:|---|---|")
    for rank, row in enumerate(scorecard["results"], start=1):
        penalties = ", ".join(f"{p['label']} x{p['count']}" for p in row["penalties"]) or "none"
        duration = row["duration_seconds"]
        duration_text = f"{duration:.1f}s" if isinstance(duration, (int, float)) else "n/a"
        lines.append(
            f"| {rank} | `{row['model']}` | {row['score']} | {duration_text} | "
            f"{row['word_count']} | {penalties} | `{row['output']}` |"
        )
    lines.append("")
    lines.append("## Fact Coverage")
    for row in scorecard["results"]:
        lines.append("")
        lines.append(f"### {row['model']}")
        lines.append(f"- Facts matched: {len(row['facts_matched'])}/{len(GOLD_FACTS)}")
        lines.append(f"- Headings present: {len(row['headings_present'])}/{len(REQUIRED_HEADINGS)}")
        if row["facts_matched"]:
            lines.append("- Matched: " + "; ".join(row["facts_matched"]))
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(md_path.relative_to(REPO_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Score model eval outputs against deterministic Session 21 gold signals.")
    parser.add_argument("--prompt-version", required=True)
    parser.add_argument("--session", default="session21")
    args = parser.parse_args()
    write_scorecard(score_prompt(args.prompt_version, args.session))


if __name__ == "__main__":
    main()
