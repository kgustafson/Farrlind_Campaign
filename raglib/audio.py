from __future__ import annotations

from pathlib import Path

from raglib import campaign


AUDIO_EXTENSIONS = [".wav", ".mp3", ".m4a", ".flac", ".aac", ".ogg"]


def session_audio_candidates(session_name: str, campaign_name: str | None = None) -> list[Path]:
    return [campaign.audio_dir(campaign_name) / f"{session_name}{extension}" for extension in AUDIO_EXTENSIONS]


def resolve_session_audio_path(session_name: str, campaign_name: str | None = None) -> Path:
    candidates = session_audio_candidates(session_name, campaign_name)
    return next((path for path in candidates if path.exists()), candidates[0])


def audio_glob_pattern(session_name: str, campaign_name: str | None = None) -> Path:
    return campaign.audio_dir(campaign_name) / f"{session_name}.*"


def is_supported_audio_path(path: str | Path) -> bool:
    return Path(path).suffix.lower() in AUDIO_EXTENSIONS
