from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


PipelineStatus = Literal["planned", "running", "succeeded", "failed", "needs_review"]
FindingSeverity = Literal["info", "warning", "error"]


class PipelineModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AudioChunk(PipelineModel):
    chunk_id: str
    source_audio: Path
    chunk_audio_path: Optional[Path] = None
    start_seconds: float = Field(ge=0)
    end_seconds: Optional[float] = Field(default=None, ge=0)
    materialized: bool = False


class ChunkManifest(PipelineModel):
    session_id: str
    source_audio: Path
    output_dir: Path
    chunk_seconds: int = Field(gt=0)
    overlap_seconds: int = Field(ge=0)
    created_at: datetime
    chunks: list[AudioChunk]


class TranscriptSegment(PipelineModel):
    start_seconds: Optional[float] = Field(default=None, ge=0)
    end_seconds: Optional[float] = Field(default=None, ge=0)
    text: str


class TranscriptChunk(PipelineModel):
    chunk_id: str
    source_audio: Path
    chunk_audio_path: Optional[Path] = None
    start_seconds: float = Field(ge=0)
    end_seconds: Optional[float] = Field(default=None, ge=0)
    text: str
    segments: list[TranscriptSegment] = Field(default_factory=list)
    model_name: str
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    status: PipelineStatus = "succeeded"
    metadata: dict[str, Optional[Union[str, int, float, bool]]] = Field(default_factory=dict)


class StitchedTranscript(PipelineModel):
    session_id: str
    text: str
    chunks: list[TranscriptChunk]
    warnings: list[str] = Field(default_factory=list)


class ValidationFinding(PipelineModel):
    code: str
    severity: FindingSeverity
    message: str
    chunk_id: Optional[str] = None


class ValidationReport(PipelineModel):
    session_id: str
    status: PipelineStatus
    findings: list[ValidationFinding] = Field(default_factory=list)
    checked_at: datetime


class PipelineRunResult(PipelineModel):
    session_id: str
    status: PipelineStatus
    manifest_path: Path
    transcript_chunk_paths: list[Path]
    stitched_markdown_path: Path
    stitched_json_path: Path
    validation_json_path: Path
    validation_markdown_path: Path
    warnings: list[str] = Field(default_factory=list)
