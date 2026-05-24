from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CAMPAIGN = "farrlind"


def active_campaign_name() -> str:
    value = os.getenv("FARRLIND_CAMPAIGN") or os.getenv("CAMPAIGN_NAME") or DEFAULT_CAMPAIGN
    normalized = value.strip().lower().replace(" ", "_")
    if not normalized:
        return DEFAULT_CAMPAIGN
    if any(part in normalized for part in ["/", "\\", ".."]):
        raise ValueError(f"Invalid campaign name: {value!r}")
    return normalized


def campaigns_root() -> Path:
    configured = os.getenv("FARRLIND_CAMPAIGNS_ROOT")
    return Path(configured).expanduser().resolve() if configured else REPO_ROOT / "campaigns"


def campaign_root(campaign_name: str | None = None) -> Path:
    return campaigns_root() / (campaign_name or active_campaign_name())


def campaign_path(*parts: str, campaign_name: str | None = None) -> Path:
    return campaign_root(campaign_name).joinpath(*parts)


def audio_dir(campaign_name: str | None = None) -> Path:
    return campaign_path("audio", campaign_name=campaign_name)


def raw_dir(campaign_name: str | None = None) -> Path:
    return campaign_path("raw", campaign_name=campaign_name)


def clean_dir(campaign_name: str | None = None) -> Path:
    return campaign_path("clean", campaign_name=campaign_name)


def final_dir(campaign_name: str | None = None) -> Path:
    return campaign_path("final", campaign_name=campaign_name)


def reviews_dir(campaign_name: str | None = None) -> Path:
    return campaign_path("reviews", campaign_name=campaign_name)


def extracted_dir(campaign_name: str | None = None) -> Path:
    return campaign_path("extracted", campaign_name=campaign_name)


def lore_dir(campaign_name: str | None = None) -> Path:
    return campaign_path("lore", campaign_name=campaign_name)


def sessions_dir(campaign_name: str | None = None) -> Path:
    return campaign_path("sessions", campaign_name=campaign_name)


def notes_dir(campaign_name: str | None = None) -> Path:
    return campaign_path("notes", campaign_name=campaign_name)


def songbook_dir(campaign_name: str | None = None) -> Path:
    return campaign_path("songbook", campaign_name=campaign_name)


def assets_dir(campaign_name: str | None = None) -> Path:
    return campaign_path("assets", campaign_name=campaign_name)


def out_dir(campaign_name: str | None = None) -> Path:
    return campaign_path("out", campaign_name=campaign_name)


def campaign_metadata_path(campaign_name: str | None = None) -> Path:
    return campaign_path("campaign.yaml", campaign_name=campaign_name)


def ensure_campaign_dirs(campaign_name: str | None = None) -> None:
    for path in [
        audio_dir(campaign_name),
        raw_dir(campaign_name),
        clean_dir(campaign_name),
        final_dir(campaign_name),
        reviews_dir(campaign_name),
        extracted_dir(campaign_name),
        lore_dir(campaign_name),
        sessions_dir(campaign_name),
        notes_dir(campaign_name),
        songbook_dir(campaign_name),
        assets_dir(campaign_name),
        out_dir(campaign_name),
    ]:
        path.mkdir(parents=True, exist_ok=True)


def load_campaign_metadata(campaign_name: str | None = None) -> dict[str, Any]:
    path = campaign_metadata_path(campaign_name)
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def campaign_feature_enabled(feature: str, campaign_name: str | None = None, default: bool = True) -> bool:
    metadata = load_campaign_metadata(campaign_name)
    features = metadata.get("features") or {}
    feature_config = metadata.get(feature) or {}
    if feature in features:
        return bool(features[feature])
    if "enabled" in feature_config:
        return bool(feature_config["enabled"])
    return default


def campaign_database_name(campaign_name: str | None = None) -> str:
    metadata = load_campaign_metadata(campaign_name)
    database = metadata.get("database") or {}
    return database.get("name") or (campaign_name or active_campaign_name())


def campaign_container_name(campaign_name: str | None = None) -> str:
    metadata = load_campaign_metadata(campaign_name)
    database = metadata.get("database") or {}
    return database.get("container") or f"{campaign_name or active_campaign_name()}_db"


def campaign_database_url(campaign_name: str | None = None, host: str = "localhost") -> str:
    metadata = load_campaign_metadata(campaign_name)
    database = metadata.get("database") or {}
    user = database.get("user") or "admin"
    password = database.get("password") or "gofaban"
    port = database.get("port") or 5432
    name = database.get("name") or (campaign_name or active_campaign_name())
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"
