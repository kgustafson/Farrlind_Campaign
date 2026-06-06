from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from raglib.campaign import active_campaign_name, campaign_database_url, final_dir, out_dir
from web_review.services.canon import _safe_repo_path


DEFAULT_REPORT = "songbook_maintenance_report.md"
MAJOR_EVENT_TYPES = {"combat", "catastrophe", "ritual", "acquisition", "discovery"}
WRITTEN_SONG_PATTERN = re.compile(
    r"\b(?:wrote|composed|created|performed|sang|plays?|introduced)\b.{0,80}?"
    r"(?:song|ballad|chant|lament|anthem|jig|shanty)?\s*"
    r"(?P<quote>\"[^\"]+\"|[“][^”]+[”])",
    re.IGNORECASE | re.DOTALL,
)
SONG_OPPORTUNITY_WORDS = re.compile(
    r"\b(song|ballad|lament|anthem|tale|saga|victory|defeat|battle|saved|destroyed|"
    r"dragon|well|queen|cataclysm|sacrifice|hero|heroes|curse|oath)\b",
    re.IGNORECASE,
)
STOP_WORDS = {
    "a",
    "an",
    "and",
    "at",
    "for",
    "in",
    "of",
    "on",
    "the",
    "to",
    "we",
    "who",
    "with",
}


@dataclass(frozen=True)
class SongOpportunity:
    session_number: int
    session_title: str
    reason: str
    evidence: str
    score: int


@dataclass(frozen=True)
class MissingRepertoireMention:
    session_number: int
    session_title: str
    title: str
    source_path: Path
    evidence: str


def normalize_words(value: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[A-Za-z0-9']+", value.lower())
        if len(word) > 2 and word not in STOP_WORDS
    }


def title_similarity(left: str, right: str) -> float:
    left_words = normalize_words(left)
    right_words = normalize_words(right)
    if not left_words or not right_words:
        return 0.0
    return len(left_words & right_words) / len(left_words | right_words)


def classify_song_issue(song: dict[str, Any]) -> list[str]:
    issues = []
    if not (song.get("suno_prompt") or "").strip():
        issues.append("missing prompt")
    if not (song.get("lyrics_local_path") or "").strip():
        issues.append("missing lyrics path")
    elif not _safe_repo_path(song["lyrics_local_path"]).exists():
        issues.append("lyrics file missing")
    if not (song.get("mp3_local_path") or "").strip():
        issues.append("missing audio path")
    elif not _safe_repo_path(song["mp3_local_path"]).exists():
        issues.append("audio file missing")
    if not (song.get("style") or "").strip():
        issues.append("missing style")
    if not (song.get("category") or "").strip():
        issues.append("missing category")
    if not (song.get("short_description") or song.get("summary") or "").strip():
        issues.append("missing description")
    return issues


def connect_database():
    url = os.getenv("FARRLIND_DATABASE_URL") or campaign_database_url(active_campaign_name())
    return create_engine(url)


def fetch_all(engine, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    with engine.begin() as conn:
        return [dict(row._mapping) for row in conn.execute(text(sql), params or {})]


def load_song_rows(engine) -> list[dict[str, Any]]:
    return fetch_all(
        engine,
        """
        SELECT
            vs.song_number,
            vs.title,
            vs.style,
            vs.category,
            vs.song_type,
            vs.short_description,
            vs.summary,
            vs.suno_prompt,
            vs.musical_key,
            vs.meter,
            vs.tempo,
            vs.instrumentation,
            vs.lyrics_local_path,
            vs.mp3_local_path,
            vs.mp3_url,
            vs.lyrics_url,
            written_session
        FROM v_songbook vs
        LEFT JOIN song s ON s.song_number = vs.song_number
        ORDER BY song_number;
        """,
    )


def load_session_event_rows(engine) -> list[dict[str, Any]]:
    return fetch_all(
        engine,
        """
        SELECT
            s.session_number,
            COALESCE(s.title, '') AS session_title,
            et.type_name AS event_type,
            COALESCE(se.significance, 0) AS significance,
            se.description,
            COALESCE(se.notes, '') AS notes
        FROM session_event se
        JOIN session s ON s.id = se.session_id
        LEFT JOIN event_type et ON et.id = se.event_type_id
        WHERE COALESCE(se.significance, 0) >= 4
        ORDER BY s.session_number, se.sequence_order, se.id;
        """,
    )


def load_sessions(engine) -> list[dict[str, Any]]:
    return fetch_all(
        engine,
        """
        SELECT session_number, COALESCE(title, '') AS title, COALESCE(summary, '') AS summary
        FROM session
        ORDER BY session_number;
        """,
    )


def existing_song_session_numbers(songs: list[dict[str, Any]]) -> set[int]:
    values = set()
    for song in songs:
        number = song.get("written_session")
        if number is not None:
            values.add(int(number))
    return values


def clean_quoted_title(value: str) -> str:
    return value.strip().strip("\"'“”").strip()


def scan_missing_repertoire_mentions(songs: list[dict[str, Any]]) -> list[MissingRepertoireMention]:
    song_titles = {frozenset(normalize_words(song["title"])) for song in songs}
    mentions: list[MissingRepertoireMention] = []
    for path in sorted(final_dir().glob("session*_summary.md")):
        session_match = re.search(r"session(\d+)_summary\.md$", path.name)
        if not session_match:
            continue
        session_number = int(session_match.group(1))
        text_value = path.read_text(encoding="utf-8-sig")
        session_title = ""
        title_match = re.search(r"(?m)^#\s+Session\s+\d+\s*(?:[:\-—]\s*)?(.*)$", text_value)
        if title_match:
            session_title = title_match.group(1).strip()
        for match in WRITTEN_SONG_PATTERN.finditer(text_value):
            title = clean_quoted_title(match.group("quote"))
            if not title:
                continue
            title_words = frozenset(normalize_words(title))
            if not title_words or title_words in song_titles:
                continue
            line_start = text_value.rfind("\n", 0, match.start()) + 1
            line_end = text_value.find("\n", match.end())
            if line_end == -1:
                line_end = len(text_value)
            evidence = text_value[line_start:line_end].strip()
            mentions.append(
                MissingRepertoireMention(
                    session_number=session_number,
                    session_title=session_title,
                    title=title,
                    source_path=path,
                    evidence=evidence,
                )
            )
    deduped = {}
    for mention in mentions:
        key = (mention.session_number, frozenset(normalize_words(mention.title)))
        deduped[key] = mention
    return sorted(deduped.values(), key=lambda item: (item.session_number, item.title.lower()))


def song_title_mentions(sessions: list[dict[str, Any]], songs: list[dict[str, Any]]) -> dict[int, list[str]]:
    mentions: dict[int, list[str]] = defaultdict(list)
    titles = [(song["title"], normalize_words(song["title"])) for song in songs]
    for session in sessions:
        haystack = f"{session.get('title', '')} {session.get('summary', '')}"
        haystack_words = normalize_words(haystack)
        for title, title_words in titles:
            if title_words and title_words.issubset(haystack_words):
                mentions[int(session["session_number"])].append(title)
    return mentions


def build_song_opportunities(
    sessions: list[dict[str, Any]],
    events: list[dict[str, Any]],
    songs: list[dict[str, Any]],
    max_items: int,
    excluded_sessions: set[int] | None = None,
) -> list[SongOpportunity]:
    by_session: dict[int, dict[str, Any]] = {
        int(session["session_number"]): session for session in sessions
    }
    grouped_events: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        grouped_events[int(event["session_number"])].append(event)

    song_sessions = existing_song_session_numbers(songs)
    mentioned_titles = song_title_mentions(sessions, songs)
    excluded_sessions = excluded_sessions or set()
    opportunities: list[SongOpportunity] = []

    for session_number, session in by_session.items():
        session_events = grouped_events.get(session_number, [])
        if not session_events:
            continue

        if session_number in song_sessions or mentioned_titles.get(session_number) or session_number in excluded_sessions:
            continue

        top_event = max(session_events, key=lambda row: (row["significance"], row.get("event_type") in MAJOR_EVENT_TYPES))
        event_type = (top_event.get("event_type") or "").lower()
        text_blob = f"{session.get('title', '')} {session.get('summary', '')} {top_event.get('description', '')}"
        score = int(top_event["significance"])
        if event_type in MAJOR_EVENT_TYPES:
            score += 2
        if SONG_OPPORTUNITY_WORDS.search(text_blob):
            score += 2
        if event_type == "combat":
            score += 1

        if score < 7:
            continue

        reason = f"High-significance {event_type or 'event'} with no linked/written song."
        opportunities.append(
            SongOpportunity(
                session_number=session_number,
                session_title=session.get("title") or "",
                reason=reason,
                evidence=top_event.get("description") or "",
                score=score,
            )
        )

    return sorted(opportunities, key=lambda item: (-item.score, item.session_number))[:max_items]


def duplicate_theme_groups(songs: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for song in songs:
        category = (song.get("category") or "uncategorized").strip() or "uncategorized"
        by_category[category].append(song)
    return sorted(
        ((category, rows) for category, rows in by_category.items() if len(rows) > 2),
        key=lambda group: (-len(group[1]), group[0].lower()),
    )


def similar_title_pairs(songs: list[dict[str, Any]], threshold: float = 0.34) -> list[tuple[dict[str, Any], dict[str, Any], float]]:
    pairs = []
    for index, left in enumerate(songs):
        for right in songs[index + 1 :]:
            score = title_similarity(left["title"], right["title"])
            if score >= threshold:
                pairs.append((left, right, score))
    return sorted(pairs, key=lambda pair: (-pair[2], pair[0]["song_number"], pair[1]["song_number"]))


def render_report(
    songs: list[dict[str, Any]],
    events: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
    output_path: Path,
    max_opportunities: int,
) -> str:
    issues_by_song = [(song, classify_song_issue(song)) for song in songs]
    issue_rows = [(song, issues) for song, issues in issues_by_song if issues]
    prompt_missing = [song for song, issues in issues_by_song if "missing prompt" in issues]
    lyrics_missing = [song for song, issues in issues_by_song if any("lyrics" in issue for issue in issues)]
    audio_missing = [song for song, issues in issues_by_song if any("audio" in issue for issue in issues)]
    category_counts = Counter((song.get("category") or "uncategorized").strip() or "uncategorized" for song in songs)
    style_counts = Counter((song.get("style") or "uncategorized").strip() or "uncategorized" for song in songs)
    missing_mentions = scan_missing_repertoire_mentions(songs)
    opportunities = build_song_opportunities(
        sessions,
        events,
        songs,
        max_opportunities,
        excluded_sessions={mention.session_number for mention in missing_mentions},
    )
    theme_groups = duplicate_theme_groups(songs)
    title_pairs = similar_title_pairs(songs)

    lines = [
        "# Songbook Prompt/Repertoire Review",
        "",
        f"Campaign: `{active_campaign_name()}`",
        f"Output: `{output_path}`",
        "",
        "## Summary",
        "",
        f"- Songs in repertoire: {len(songs)}",
        f"- Songs missing prompts: {len(prompt_missing)}",
        f"- Songs missing local lyrics: {len(lyrics_missing)}",
        f"- Songs missing local audio: {len(audio_missing)}",
        f"- High-significance song opportunities: {len(opportunities)}",
        f"- Summary song mentions missing from repertoire: {len(missing_mentions)}",
        f"- Repertoire categories: {len(category_counts)}",
        f"- Repertoire styles: {len(style_counts)}",
        "",
        "## Prompt And Asset Attention",
        "",
    ]

    if not issue_rows:
        lines.append("- No prompt or asset issues found.")
    else:
        for song, issues in issue_rows:
            lines.append(f"- {song['song_number']:02d}. {song['title']}: {', '.join(issues)}")

    lines.extend(["", "## Missing Repertoire Entries Mentioned In Summaries", ""])
    if not missing_mentions:
        lines.append("- No written/performed song titles were found missing from the song table.")
    else:
        for mention in missing_mentions:
            lines.append(
                f"- Session {mention.session_number:02d}"
                f"{f' - {mention.session_title}' if mention.session_title else ''}: "
                f"`{mention.title}` is mentioned but is not in the song table."
            )
            lines.append(f"  Source: `{mention.source_path}`")
            lines.append(f"  Evidence: {mention.evidence}")

    lines.extend(["", "## Song Opportunities", ""])
    if not opportunities:
        lines.append("- No obvious high-significance song opportunities found.")
    else:
        for item in opportunities:
            lines.append(
                f"- Session {item.session_number:02d}"
                f"{f' - {item.session_title}' if item.session_title else ''}: "
                f"{item.reason} Score {item.score}."
            )
            lines.append(f"  Evidence: {item.evidence}")

    lines.extend(["", "## Repertoire Theme Clusters", ""])
    for category, rows in theme_groups:
        titles = ", ".join(f"{row['song_number']:02d}. {row['title']}" for row in rows)
        lines.append(f"- {category}: {len(rows)} songs ({titles})")
    if not theme_groups:
        lines.append("- No category contains more than two songs.")

    lines.extend(["", "## Similar Title Watchlist", ""])
    if not title_pairs:
        lines.append("- No similar title pairs found.")
    else:
        for left, right, score in title_pairs[:15]:
            lines.append(
                f"- {left['song_number']:02d}. {left['title']} / "
                f"{right['song_number']:02d}. {right['title']} ({score:.0%} token overlap)"
            )

    lines.extend(["", "## Category Counts", ""])
    for category, count in sorted(category_counts.items(), key=lambda item: (-item[1], item[0].lower())):
        lines.append(f"- {category}: {count}")

    lines.extend(["", "## Style Counts", ""])
    for style, count in sorted(style_counts.items(), key=lambda item: (-item[1], item[0].lower())):
        lines.append(f"- {style}: {count}")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This report is diagnostic only. It does not create songs, prompts, performances, or canon records.",
            "- Song opportunities are intentionally conservative and should be treated as suggestions for human review.",
            "- A future maintenance workflow can promote accepted opportunities into explicit song ideas or songbook tasks.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_songbook_maintenance_report(output: Path | None = None, max_opportunities: int = 12) -> Path:
    engine = connect_database()
    songs = load_song_rows(engine)
    events = load_session_event_rows(engine)
    sessions = load_sessions(engine)

    report_path = output or (out_dir() / DEFAULT_REPORT)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        render_report(songs, events, sessions, report_path, max_opportunities),
        encoding="utf-8",
    )
    print(f"Wrote {report_path}")
    return report_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review songbook prompt coverage and repertoire gaps.")
    parser.add_argument("--output", type=Path, default=None, help=f"Defaults to campaign out/{DEFAULT_REPORT}.")
    parser.add_argument("--max-opportunities", type=int, default=12)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    write_songbook_maintenance_report(args.output, args.max_opportunities)


if __name__ == "__main__":
    main()
