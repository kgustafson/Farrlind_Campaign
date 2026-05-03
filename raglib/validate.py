import re

from raglib.config import CLEAN
from raglib.io_utils import read_text, write_text


KNOWN_ENTITIES = {
    "Faban", "Gildas", "Mikani", "Brigit", "Corvinas", "Roon",
    "Lightdelver", "Orsydon",
    "Balrog", "Saiffi", "Wand of Wells", "Bag of Holding",
}

SUSPECT_TERMS = {
    "mouth-a-lug": "Likely Lightdelver based on Cloud of Daggers / concentration context.",
    "clap daggers": "Likely Cloud of Daggers.",
    "cloud dagger": "Likely Cloud of Daggers.",
    "bag of folding": "Likely Bag of Holding.",
    "faven": "Likely Faban.",
    "faben": "Likely Faban.",
    "rune": "Likely Roon.",
    "scythe": "Likely Saiffi.",
    "syfie": "Likely Saiffi.",
}

BAD_GENERIC_PHRASES = [
    "the guy in the back",
    "unknown",
    "not specified",
    "n/a",
    "none specified",
    "none mentioned",
]

REQUIRED_IF_PRESENT = [
    {
        "name": "Dragon combat",
        "triggers": ["dragon", "initiative"],
        "required": ["dragon", "combat"],
    },
    {
        "name": "Nightmare breath",
        "triggers": ["nightmare breath"],
        "required": ["psychic", "frightened"],
    },
    {
        "name": "Dragon defeat",
        "triggers": ["dragon", "defeated"],
        "required": ["dragon", "defeated"],
    },
    {
        "name": "Cloud of Daggers concentration",
        "triggers": ["cloud of daggers", "concentration"],
        "required": ["cloud of daggers", "concentration"],
    },
]


def find_suspect_terms(text: str):
    findings = []
    low = text.lower()

    for term, note in SUSPECT_TERMS.items():
        if term in low:
            findings.append(f"- Suspect term: `{term}` — {note}")

    return findings


def find_generic_placeholders(text: str):
    findings = []

    substantive_fields = {"summary", "actors", "targets", "outcome", "verify"}

    for block in extract_event_blocks(text):
        lines = block.splitlines()
        title = lines[0].strip() if lines else "Unknown event"

        for line in lines:
            match = re.match(r"\s*-\s*([a-z_]+):\s*(.*)", line, re.IGNORECASE)
            if not match:
                continue

            field = match.group(1).lower()
            value = match.group(2).strip()

            if field not in substantive_fields or not value:
                continue

            low = value.lower()
            for phrase in BAD_GENERIC_PHRASES:
                if phrase in low:
                    findings.append(
                        f"- Generic/uncertain phrase found in `{title}` {field}: `{phrase}`"
                    )

    return findings


def extract_event_blocks(text: str):
    return re.split(r"\n## Event \d+:", text)


def find_low_confidence_high_importance(text: str):
    findings = []

    for block in extract_event_blocks(text):
        low = block.lower()
        if "importance: high" in low and "confidence: low" in low:
            title = block.splitlines()[0].strip() if block.splitlines() else "Unknown event"
            findings.append(f"- High-importance event has low confidence: `{title}`")

    return findings


def find_malformed_fields(text: str):
    findings = []

    malformed_patterns = [
        r"actors:\s*targets:",
        r"targets:\s*location:",
        r"location:\s*mechanical_tags:",
        r"mechanical_tags:\s*story_tags:",
        r"story_tags:\s*outcome:",
    ]

    for pattern in malformed_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            findings.append(f"- Malformed field pattern detected: `{pattern}`")

    return findings


def validate_required_facts(source_text: str, summary_text: str = ""):
    findings = []
    summary_low = summary_text.lower()

    for block in extract_event_blocks(source_text):
        source_low = block.lower()

        for rule in REQUIRED_IF_PRESENT:
            if not all(trigger in source_low for trigger in rule["triggers"]):
                continue

            if summary_text:
                missing = [
                    required for required in rule["required"]
                    if required not in summary_low
                ]
                if missing:
                    findings.append(
                        f"- Summary may be missing `{rule['name']}` details: "
                        f"missing {', '.join(missing)}"
                    )
            else:
                findings.append(
                    f"- Required summary topic detected: `{rule['name']}`"
                )

    return list(dict.fromkeys(findings))


def validate_session(session_name: str):
    merged_path = CLEAN / f"{session_name}_merged.md"
    summary_path = CLEAN / f"{session_name}_summary.md"
    report_path = CLEAN / f"{session_name}_validation.md"

    merged = read_text(merged_path)
    summary = summary_path.read_text(encoding="utf-8") if summary_path.exists() else ""

    findings = []
    findings.append(f"# Validation Report: {session_name}")
    findings.append("")

    checks = []

    checks.extend(find_suspect_terms(merged))
    checks.extend(find_generic_placeholders(merged))
    checks.extend(find_low_confidence_high_importance(merged))
    checks.extend(find_malformed_fields(merged))
    checks.extend(validate_required_facts(merged, summary))

    if not checks:
        findings.append("No obvious validation issues found.")
    else:
        findings.append("## Issues Found")
        findings.append("")
        findings.extend(checks)

    findings.append("")
    findings.append("## Recommended Human Corrections")
    findings.append("")
    findings.append("- Add confirmed corrections to:")
    findings.append(f"  - `knowledge/Faban/notes/{session_name}_corrections.md`")
    findings.append("")
    findings.append("Example:")
    findings.append("")
    findings.append("```text")
    findings.append("Mouth-a-lug = Lightdelver")
    findings.append("Dragon = Orsydon")
    findings.append("Scythe/Syfie = Saiffi")
    findings.append("```")

    write_text(report_path, "\n".join(findings))

    print(f"Validation report written to: {report_path}")
