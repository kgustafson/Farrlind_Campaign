import os
from datetime import date
from pathlib import Path
from uuid import uuid4
from typing import Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from scripts.db_backup import backup_database
from raglib.campaign import active_campaign_name, assets_dir, audio_dir, campaign_feature_enabled, load_campaign_metadata
from web_review.services import artifact_extraction_review, canon, combat_extraction_review, commands, location_extraction_review, lore_item_extraction_review, npc_extraction_review, open_thread_extraction_review, reviews, songbook_drive, workflow


app = FastAPI(title="Campaign Review Workbench")
app.mount("/static", StaticFiles(directory=str(reviews.REPO_ROOT / "web_review" / "static")), name="static")
templates = Jinja2Templates(directory=str(reviews.REPO_ROOT / "web_review" / "templates"))
COMMAND_RESULTS = {}
BACKUP_DOWNLOADS = {}

EDIT_MODE = "edit"
ARCHIVE_MODE = "archive"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
WORLD_MAP_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def interface_mode() -> str:
    value = os.getenv("FARRLIND_INTERFACE_MODE", EDIT_MODE).strip().lower()
    return value if value in {EDIT_MODE, ARCHIVE_MODE} else EDIT_MODE


def can_edit() -> bool:
    return interface_mode() == EDIT_MODE


def app_version() -> str:
    version_path = reviews.REPO_ROOT / "version.md"
    try:
        for line in version_path.read_text(encoding="utf-8").splitlines():
            value = line.strip()
            if value.startswith("v"):
                return value
    except FileNotFoundError:
        return "unversioned"
    return "unversioned"


def app_git_hash() -> str:
    return os.getenv("FARRLIND_GIT_HASH", "").strip()


def app_git_hash_short() -> str:
    value = app_git_hash()
    if not value or value.lower() == "unknown":
        return ""
    return value[:7]


def campaign_metadata() -> dict:
    return load_campaign_metadata()


def campaign_display_name() -> str:
    metadata = campaign_metadata()
    campaign_info = metadata.get("campaign") or {}
    return campaign_info.get("name") or active_campaign_name().replace("_", " ").title()


def archive_title() -> str:
    metadata = campaign_metadata()
    campaign_info = metadata.get("campaign") or {}
    return campaign_info.get("archive_title") or f"The {campaign_display_name()} Archivum"


def archive_subtitle() -> str:
    metadata = campaign_metadata()
    campaign_info = metadata.get("campaign") or {}
    return campaign_info.get("archive_subtitle") or "A campaign canon archive of sessions, lore, people, places, artifacts, and unresolved threads."


def songbook_label() -> str:
    metadata = campaign_metadata()
    songbook = metadata.get("songbook") or {}
    return songbook.get("label") or "Songbook"


def songbook_enabled() -> bool:
    return campaign_feature_enabled("songbook", default=False)


def active_campaign_name_template() -> str:
    return active_campaign_name()


def campaign_audio_dir() -> str:
    return str(audio_dir())


def campaign_world_map_path() -> Optional[Path]:
    assets = assets_dir()
    for suffix in sorted(WORLD_MAP_EXTENSIONS):
        candidate = assets / f"world-map{suffix}"
        if candidate.exists():
            return candidate
    return None


def campaign_world_map_available() -> bool:
    return campaign_world_map_path() is not None


def campaign_world_map_version() -> str:
    path = campaign_world_map_path()
    if path is None:
        return ""
    return str(int(path.stat().st_mtime))


def campaign_world_map_image_url() -> str:
    version = campaign_world_map_version()
    return f"/world-map/image?v={version}" if version else "/world-map/image"


templates.env.globals["app_version"] = app_version
templates.env.globals["app_git_hash_short"] = app_git_hash_short
templates.env.globals["interface_mode"] = interface_mode
templates.env.globals["can_edit"] = can_edit
templates.env.globals["campaign_display_name"] = campaign_display_name
templates.env.globals["archive_title"] = archive_title
templates.env.globals["archive_subtitle"] = archive_subtitle
templates.env.globals["songbook_label"] = songbook_label
templates.env.globals["songbook_enabled"] = songbook_enabled
templates.env.globals["active_campaign_name"] = active_campaign_name_template
templates.env.globals["campaign_audio_dir"] = campaign_audio_dir
templates.env.globals["campaign_world_map_available"] = campaign_world_map_available
templates.env.globals["campaign_world_map_image_url"] = campaign_world_map_image_url


@app.middleware("http")
async def archive_mode_write_guard(request: Request, call_next):
    if not can_edit() and request.method.upper() not in SAFE_METHODS:
        return PlainTextResponse(f"{archive_title()} is running in archive mode.", status_code=403)
    return await call_next(request)


def store_command_result(action: str, result: commands.CommandResult) -> str:
    token = uuid4().hex
    COMMAND_RESULTS[token] = {
        "action": action,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "ok": result.ok,
    }
    return token


def project_document(document: str) -> dict[str, str]:
    choices = {
        "todo": reviews.REPO_ROOT / "todo.md",
        "revision": reviews.REPO_ROOT / "revision.md",
    }
    key = document if document in choices else "todo"
    path = choices[key]
    text = path.read_text(encoding="utf-8")
    return {
        "key": key,
        "title": "Todo" if key == "todo" else "Revision History",
        "filename": path.name,
        "text": text,
        "html": reviews.render_markdown(text),
    }


def redirect_to_review(session_number: int, source: str, view: str, flag: str, bucket: str = "") -> RedirectResponse:
    bucket_param = f"&bucket={bucket}" if bucket else ""
    return RedirectResponse(
        url=f"/sessions/{reviews.session_key(session_number)}/review?source={source}&view={view}{bucket_param}&{flag}",
        status_code=303,
    )


def canon_location_names() -> list[str]:
    try:
        return canon.locations()
    except canon.CanonReadError:
        return []


def macro_locations_to_validate(form_values: dict[str, list[str]]) -> list[str]:
    remove_ids = set(form_values.get("remove_macro_id") or [])
    macro_ids = form_values.get("macro_id") or []
    macro_locations = form_values.get("macro_location") or []
    kept_locations = [
        location
        for index, location in enumerate(macro_locations)
        if index >= len(macro_ids) or macro_ids[index] not in remove_ids
    ]
    return kept_locations + (form_values.get("new_macro_location") or [])


def sync_after_extraction_review(session_number: int) -> list[str]:
    messages: list[str] = []
    try:
        workflow.sync_session_workflow(session_number)
    except workflow.WorkflowWriteError:
        messages.append("Workflow sync skipped after extraction review.")

    if reviews.event_review_ready(session_number) and not reviews.review_path(session_number).exists():
        refresh_result = commands.refresh_event_drafts(session_number)
        if refresh_result.ok:
            messages.append("Refreshed event drafts.")
            try:
                workflow.sync_session_workflow(session_number)
            except workflow.WorkflowWriteError:
                messages.append("Workflow sync skipped after event draft refresh.")
        else:
            messages.append("Event draft refresh failed.")
            if refresh_result.stderr.strip():
                messages.append(refresh_result.stderr.strip())
            elif refresh_result.stdout.strip():
                messages.append(refresh_result.stdout.strip())
            return messages

        init_result = commands.init_review(session_number)
        if init_result.ok:
            messages.append("Initialized final summary review.")
            try:
                workflow.sync_session_workflow(session_number)
            except workflow.WorkflowWriteError:
                messages.append("Workflow sync skipped after event review initialization.")
        else:
            messages.append("Final summary review initialization failed.")
            if init_result.stderr.strip():
                messages.append(init_result.stderr.strip())
    return messages


def location_confirmation_failed(form_values: dict[str, list[str]], form, known_locations: list[str]) -> bool:
    if form.get("confirm_new_locations"):
        return False
    return bool(reviews.unknown_locations(reviews.form_locations(form_values), known_locations))


def create_missing_review_locations(names: list[str], known_locations: list[str], session_number: int, notes: str) -> bool:
    created_or_existing = set(known_locations)
    for name in reviews.unknown_locations(names, list(created_or_existing)):
        values = {
            "name": name,
            "location_type_id": None,
            "parent_location_id": None,
            "description": "",
            "is_underwater": False,
            "is_feywild": False,
            "first_visited_session": session_number,
            "notes": notes,
        }
        try:
            canon.create_location(values)
        except canon.CanonWriteError:
            if name not in canon_location_names():
                return False
        created_or_existing.add(name)
    return True


def optional_int(value: Optional[str]) -> Optional[int]:
    value = (value or "").strip()
    return int(value) if value else None


def checkbox_value(value: Optional[str]) -> bool:
    return value in {"1", "true", "on", "yes"}


def location_form_values(form) -> dict:
    return {
        "name": (form.get("name") or "").strip(),
        "location_type_id": optional_int(form.get("location_type_id")),
        "parent_location_id": optional_int(form.get("parent_location_id")),
        "description": (form.get("description") or "").strip(),
        "is_underwater": checkbox_value(form.get("is_underwater")),
        "is_feywild": checkbox_value(form.get("is_feywild")),
        "first_visited_session": optional_int(form.get("first_visited_session")),
        "notes": (form.get("notes") or "").strip(),
    }


def npc_form_values(form) -> dict:
    return {
        "name": (form.get("name") or "").strip(),
        "alias": (form.get("alias") or "").strip(),
        "faction_id": optional_int(form.get("faction_id")),
        "entity_status_id": optional_int(form.get("entity_status_id")),
        "last_known_location_id": optional_int(form.get("last_known_location_id")),
        "first_seen_session": optional_int(form.get("first_seen_session")),
        "description": (form.get("description") or "").strip(),
        "is_named": checkbox_value(form.get("is_named")),
        "notes": (form.get("notes") or "").strip(),
    }


def artifact_form_values(form) -> dict:
    return {
        "name": (form.get("name") or "").strip(),
        "artifact_type_id": optional_int(form.get("artifact_type_id")),
        "discovered_session": optional_int(form.get("discovered_session")),
        "description": (form.get("description") or "").strip(),
        "lore_significance": (form.get("lore_significance") or "").strip(),
        "is_sentient": checkbox_value(form.get("is_sentient")),
        "is_cursed": checkbox_value(form.get("is_cursed")),
        "is_infernal": checkbox_value(form.get("is_infernal")),
        "notes": (form.get("notes") or "").strip(),
    }


def song_form_values(form, current: Optional[dict] = None) -> dict:
    lyrics_url = (form.get("lyrics_drive_url") or form.get("lyrics_url") or "").strip()
    mp3_url = (form.get("mp3_drive_url") or form.get("mp3_url") or "").strip()
    return {
        "song_number": optional_int(form.get("song_number")) if current is None else current.get("song_number"),
        "order_number": optional_int(form.get("order_number")),
        "title": (form.get("title") or "").strip(),
        "style_id": optional_int(form.get("style_id")),
        "category_id": optional_int(form.get("category_id")),
        "song_type": (form.get("song_type") or "").strip(),
        "short_description": (form.get("short_description") or "").strip(),
        "long_description": (form.get("long_description") or "").strip(),
        "summary": (form.get("summary") or "").strip(),
        "suno_prompt": (form.get("suno_prompt") or "").strip(),
        "musical_key": (form.get("musical_key") or "").strip(),
        "meter": (form.get("meter") or "").strip(),
        "tempo": (form.get("tempo") or "").strip(),
        "instrumentation": (form.get("instrumentation") or "").strip(),
        "lyrics_local_path": (form.get("lyrics_local_path") or "").strip(),
        "mp3_local_path": (form.get("mp3_local_path") or "").strip(),
        "lyrics_url": lyrics_url,
        "mp3_url": mp3_url,
        "written_session": optional_int(form.get("written_session")),
        "in_world_context": (form.get("in_world_context") or "").strip(),
        "is_performed": checkbox_value(form.get("is_performed")),
    }


def timeline_form_text(form, field_name: str, current: dict, current_field: Optional[str] = None) -> str:
    if field_name in form:
        return (form.get(field_name) or "").strip()
    value = current.get(current_field or field_name)
    return str(value or "")


def timeline_location_id(form, field_name: str, current: dict, current_field: Optional[str] = None) -> Optional[int]:
    location_name = timeline_form_text(form, field_name, current, current_field)
    return canon.location_id(location_name)


def timeline_form_values(form, current: dict) -> dict:
    session_date = timeline_form_text(form, "session_date", current)
    return {
        "title": timeline_form_text(form, "title", current),
        "session_date": session_date or None,
        "in_game_date": timeline_form_text(form, "in_game_date", current),
        "primary_location_id": timeline_location_id(form, "primary_location", current),
        "start_location_id": timeline_location_id(form, "start_location", current),
        "end_location_id": timeline_location_id(form, "end_location", current),
        "summary": timeline_form_text(form, "summary", current),
        "notes": timeline_form_text(form, "notes", current),
    }


def lore_item_form_values(form) -> dict:
    return {
        "title": (form.get("title") or "").strip(),
        "category": (form.get("category") or "").strip(),
        "description": (form.get("description") or "").strip(),
        "source_npc_id": optional_int(form.get("source_npc_id")),
        "discovered_session": optional_int(form.get("discovered_session")),
        "is_confirmed": checkbox_value(form.get("is_confirmed")),
        "notes": (form.get("notes") or "").strip(),
    }


def open_thread_form_values(form) -> dict:
    status = (form.get("status") or "open").strip()
    thread_type = (form.get("thread_type") or "lore_mystery").strip()
    valid_statuses = {row["code"] for row in canon.open_thread_statuses()}
    valid_types = set(canon.open_thread_types())
    return {
        "title": (form.get("title") or "").strip(),
        "thread_type": thread_type if thread_type in valid_types else "lore_mystery",
        "status": status if status in valid_statuses else "open",
        "first_session": optional_int(form.get("first_session")),
        "last_session": optional_int(form.get("last_session")),
        "related_location_id": optional_int(form.get("related_location_id")),
        "description": (form.get("description") or "").strip(),
        "resolution": (form.get("resolution") or "").strip(),
        "notes": (form.get("notes") or "").strip(),
    }


def lookup_form_values(form) -> dict[str, str]:
    return {
        "value": (form.get("value") or "").strip(),
        "description": (form.get("description") or "").strip(),
    }


def session_initiation_form_values(form) -> dict:
    return {
        "session_number": (form.get("session_number") or "").strip(),
        "session_date": (form.get("session_date") or "").strip(),
        "title": (form.get("title") or "").strip(),
        "audio_file_path": (form.get("audio_file_path") or "").strip(),
        "transcript_policy": (form.get("transcript_policy") or "use_existing").strip(),
        "notes": (form.get("notes") or "").strip(),
    }


def combat_encounter_form_values(form) -> tuple[dict, list[dict]]:
    values = {
        "session_number": optional_int(form.get("session_number")),
        "title": (form.get("title") or "").strip(),
        "subtype": (form.get("subtype") or "").strip(),
        "location_id": optional_int(form.get("location_id")),
        "participants": (form.get("participants") or "").strip(),
        "outcome": (form.get("outcome") or "unknown").strip(),
        "confidence": (form.get("confidence") or "medium").strip(),
        "notes": (form.get("notes") or "").strip(),
    }
    enemies = []
    for index in range(1, 17):
        if form.get(f"enemy_remove_{index}"):
            continue
        name = (form.get(f"enemy_name_{index}") or "").strip()
        if not name:
            continue
        enemies.append({
            "name": name,
            "enemy_type": (form.get(f"enemy_type_{index}") or "").strip(),
            "quantity": optional_int(form.get(f"enemy_quantity_{index}")),
            "quantity_killed": optional_int(form.get(f"enemy_quantity_killed_{index}")),
            "outcome": (form.get(f"enemy_outcome_{index}") or "unknown").strip(),
            "confidence": (form.get(f"enemy_confidence_{index}") or "medium").strip(),
            "notes": (form.get(f"enemy_notes_{index}") or "").strip(),
        })
    return values, enemies


def form_dict(form) -> dict[str, str]:
    return {key: str(value) for key, value in form.items()}


def lookup_context(lookup_key: str, editing_id: Optional[int] = None, show_modal: bool = False) -> dict:
    definitions = canon.lookup_definitions()
    active = canon.lookup_definition(lookup_key)
    rows = canon.lookup_rows(lookup_key)
    editing = canon.lookup_detail(lookup_key, editing_id) if editing_id is not None else None
    if editing_id is not None and not editing:
        raise HTTPException(status_code=404, detail="Lookup row not found.")
    return {
        "lookup_definitions": definitions,
        "active_lookup": active,
        "lookup_rows": rows,
        "editing": editing,
        "show_lookup_modal": show_modal,
    }


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"rows": reviews.dashboard_rows()},
    )


@app.get("/world-map/image")
def world_map_image():
    path = campaign_world_map_path()
    if path is None:
        raise HTTPException(status_code=404, detail="No campaign world map has been uploaded.")
    media_types = {
        ".gif": "image/gif",
        ".jpeg": "image/jpeg",
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    return FileResponse(path, media_type=media_types.get(path.suffix.lower(), "application/octet-stream"))


@app.post("/world-map")
async def upload_world_map(map_image: UploadFile = File(...)):
    filename = map_image.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in WORLD_MAP_EXTENSIONS:
        raise HTTPException(status_code=400, detail="World map must be a PNG, JPG, WEBP, or GIF image.")
    content_type = (map_image.content_type or "").lower()
    if content_type and not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="World map upload must be an image.")

    content = await map_image.read()
    if not content:
        raise HTTPException(status_code=400, detail="World map upload was empty.")
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="World map image must be 25 MB or smaller.")

    assets = assets_dir()
    assets.mkdir(parents=True, exist_ok=True)
    for extension in WORLD_MAP_EXTENSIONS:
        existing = assets / f"world-map{extension}"
        if existing.exists():
            existing.unlink()
    destination = assets / f"world-map{suffix}"
    destination.write_bytes(content)
    return RedirectResponse(url="/#world-map-modal", status_code=303)


@app.get("/event-review", response_class=HTMLResponse)
def event_review_dashboard(request: Request):
    if not can_edit():
        raise HTTPException(status_code=404, detail="Event review is not available in archive mode.")
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"rows": reviews.dashboard_rows(), "event_review_mode": True},
    )


@app.get("/workflow", response_class=HTMLResponse)
def workflow_index(request: Request, session: Optional[int] = None):
    if not can_edit():
        raise HTTPException(status_code=404, detail="Workflow status is not available in archive mode.")
    try:
        rows = workflow.workflow_rows()
        selected_session = session
        detail = workflow.workflow_detail(selected_session) if selected_session is not None else None
    except workflow.WorkflowReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return templates.TemplateResponse(
        request,
        "workflow.html",
        {
            "rows": rows,
            "selected_session": selected_session,
            "detail": detail,
            "draft_rerun_queued": request.query_params.get("draft_rerun_queued"),
            "draft_rerun_blocked": request.query_params.get("draft_rerun_blocked"),
        },
    )


@app.post("/workflow/sessions/{session}/rerun-draft")
def workflow_rerun_draft(session: str):
    if not can_edit():
        raise HTTPException(status_code=404, detail="Workflow status is not available in archive mode.")
    try:
        session_number = reviews.parse_session_ref(session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    try:
        workflow.enqueue_draft_rerun(session_number)
    except workflow.WorkflowWriteError:
        return RedirectResponse(url=f"/workflow?session={session_number}&draft_rerun_blocked=1", status_code=303)
    return RedirectResponse(url=f"/workflow?session={session_number}&draft_rerun_queued=1", status_code=303)


@app.get("/sessions/{session}/review", response_class=HTMLResponse)
def session_review(request: Request, session: str, source: str = "diary", view: str = "raw", bucket: str = ""):
    try:
        session_number = reviews.parse_session_ref(session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if not can_edit():
        view = "print"
        if source == "summary":
            source = "final"
        elif source not in {"diary", "final"}:
            source = "diary"
    elif reviews.event_review_access_blocked(session_number):
        workspace = reviews.session_workspace(session_number, source, view, bucket)
        workspace["event_review_blocked"] = True
        workspace["missing_extraction_reviews"] = reviews.missing_extraction_reviews(session_number)
        workspace["locations"] = []
        workspace["location_types"] = []
        workspace["command_result"] = None
        return templates.TemplateResponse(request, "session_review.html", workspace)
    workspace = reviews.session_workspace(session_number, source, view, bucket)
    workspace["locations"] = canon_location_names()
    try:
        workspace["location_types"] = canon.location_types()
    except canon.CanonReadError:
        workspace["location_types"] = []
    token = request.query_params.get("command_result")
    workspace["command_result"] = COMMAND_RESULTS.get(token) if token else None
    return templates.TemplateResponse(
        request,
        "session_review.html",
        workspace,
    )


@app.post("/sessions/{session}/review/init")
async def init_session_review(request: Request, session: str):
    if not can_edit():
        raise HTTPException(status_code=404, detail="Event review initialization is not available in archive mode.")
    try:
        session_number = reviews.parse_session_ref(session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if reviews.event_review_access_blocked(session_number):
        return redirect_to_review(session_number, "diary", "raw", "event_review_blocked=1")

    result = commands.init_review(session_number)
    token = store_command_result("Initialize Final Summary Review", result)
    flag = "init_reviewed=1" if result.ok else "init_failed=1"
    return redirect_to_review(session_number, "diary", "raw", f"{flag}&command_result={token}")


@app.post("/sessions/{session}/review/save")
async def save_session_review(request: Request, session: str):
    try:
        session_number = reviews.parse_session_ref(session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    document = reviews.load_review_document(session_number)
    if not document:
        raise HTTPException(status_code=404, detail="Review file has not been initialized.")

    if document.get("status") == "applied":
        raise HTTPException(status_code=409, detail="Applied reviews are locked until explicitly reopened.")

    form = await request.form()
    form_values = {key: form.getlist(key) for key in form.keys()}
    if reviews.final_summary_mode(document) or "final_summary_markdown" in form:
        updated = reviews.update_final_summary_from_form(document, form_values)
    else:
        updated = reviews.update_review_document_from_form(document, form_values)
    try:
        reviews.save_review_document(session_number, updated)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    source = form.get("source") or "narrative"
    view = form.get("view") or "raw"
    return redirect_to_review(session_number, source, view, "saved=1", form.get("bucket") or "")


@app.post("/sessions/{session}/review/save-item")
async def save_session_review_item(request: Request, session: str):
    try:
        session_number = reviews.parse_session_ref(session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    document = reviews.load_review_document(session_number)
    if not document:
        raise HTTPException(status_code=404, detail="Review file has not been initialized.")
    if document.get("status") == "applied":
        raise HTTPException(status_code=409, detail="Applied reviews are locked until explicitly reopened.")

    form = await request.form()
    if reviews.final_summary_mode(document):
        return redirect_to_review(session_number, form.get("source") or "narrative", form.get("view") or "raw", "saved=1", form.get("bucket") or "")

    form_values = {key: form.getlist(key) for key in form.keys()}
    updated = reviews.update_single_review_item_from_form(document, form_values, form.get("save_item_id") or "")
    try:
        reviews.save_review_document(session_number, updated)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return redirect_to_review(session_number, form.get("source") or "diary", form.get("view") or "raw", "item_saved=1", form.get("bucket") or "")


@app.post("/sessions/{session}/review/batch")
async def batch_session_review_items(request: Request, session: str):
    try:
        session_number = reviews.parse_session_ref(session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    document = reviews.load_review_document(session_number)
    if not document:
        raise HTTPException(status_code=404, detail="Review file has not been initialized.")
    if document.get("status") == "applied":
        raise HTTPException(status_code=409, detail="Applied reviews are locked until explicitly reopened.")

    form = await request.form()
    if reviews.final_summary_mode(document):
        return redirect_to_review(session_number, form.get("source") or "narrative", form.get("view") or "raw", "saved=1", form.get("bucket") or "")

    updated, errors = reviews.update_batch_decision(
        document,
        form.getlist("selected_item_id"),
        form.get("batch_decision") or "",
        form.get("batch_reason") or "",
        form.get("batch_macro_event_id") or "",
    )
    if not errors:
        try:
            reviews.save_review_document(session_number, updated)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    flag = "batch_saved=1" if not errors else "batch_failed=1"
    return redirect_to_review(session_number, form.get("source") or "diary", form.get("view") or "raw", flag, form.get("bucket") or "")


@app.post("/sessions/{session}/review/macros")
async def save_session_review_macros(request: Request, session: str):
    try:
        session_number = reviews.parse_session_ref(session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    document = reviews.load_review_document(session_number)
    if not document:
        raise HTTPException(status_code=404, detail="Review file has not been initialized.")
    if document.get("status") == "applied":
        raise HTTPException(status_code=409, detail="Applied reviews are locked until explicitly reopened.")

    form = await request.form()
    if reviews.final_summary_mode(document):
        return redirect_to_review(session_number, form.get("source") or "narrative", form.get("view") or "raw", "saved=1", form.get("bucket") or "")

    form_values = {key: form.getlist(key) for key in form.keys()}
    known_locations = canon_location_names()
    macro_locations = macro_locations_to_validate(form_values)
    if not create_missing_review_locations(macro_locations, known_locations, session_number, "Added from high-level event order."):
        return redirect_to_review(session_number, form.get("source") or "diary", form.get("view") or "raw", "location_add_failed=1&macro_modal=1", form.get("bucket") or "")
    updated = reviews.update_macro_events_from_form(document, form_values)
    try:
        reviews.save_review_document(session_number, updated)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    flag = "macros_saved=1"
    if form.get("review_stage") != "bucketing":
        flag += "&macro_modal=1"
    selected_bucket = form.get("bucket") or ""
    if selected_bucket in set(form_values.get("remove_macro_id") or []):
        selected_bucket = "all"
    return redirect_to_review(session_number, form.get("source") or "diary", form.get("view") or "raw", flag, selected_bucket)


@app.post("/sessions/{session}/review/bucketing")
async def save_session_review_bucketing(request: Request, session: str):
    try:
        session_number = reviews.parse_session_ref(session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    document = reviews.load_review_document(session_number)
    if not document:
        raise HTTPException(status_code=404, detail="Review file has not been initialized.")
    if document.get("status") == "applied":
        raise HTTPException(status_code=409, detail="Applied reviews are locked until explicitly reopened.")

    form = await request.form()
    if reviews.final_summary_mode(document):
        return redirect_to_review(session_number, form.get("source") or "narrative", form.get("view") or "raw", "saved=1", form.get("bucket") or "")

    form_values = {key: form.getlist(key) for key in form.keys()}
    requested_stage = form.get("review_stage") or ""
    updated = reviews.update_bucketing_from_form(document, form_values)
    if requested_stage == "event_resolution":
        errors = reviews.bucketing_errors(updated)
        if errors:
            updated = reviews.set_review_stage(updated, "bucketing")
            flag = "bucketing_failed=1"
        else:
            flag = "bucketing_done=1"
    else:
        flag = "bucketing_saved=1"

    try:
        reviews.save_review_document(session_number, updated)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return redirect_to_review(session_number, form.get("source") or "diary", form.get("view") or "raw", flag, form.get("bucket") or "")


@app.post("/sessions/{session}/review/apply-macros")
async def apply_session_review_macros(request: Request, session: str):
    try:
        session_number = reviews.parse_session_ref(session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    document = reviews.load_review_document(session_number)
    if not document:
        raise HTTPException(status_code=404, detail="Review file has not been initialized.")
    if document.get("status") == "applied":
        raise HTTPException(status_code=409, detail="Applied reviews are locked until explicitly reopened.")

    form = await request.form()
    if reviews.final_summary_mode(document):
        return redirect_to_review(session_number, form.get("source") or "narrative", form.get("view") or "raw", "saved=1", form.get("bucket") or "")

    form_values = {key: form.getlist(key) for key in form.keys()}
    updated = reviews.update_review_document_from_form(document, form_values)
    updated, errors = reviews.apply_macro_event_order(updated)
    if not errors:
        try:
            reviews.save_review_document(session_number, updated)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    flag = "macros_applied=1" if not errors else "macros_apply_failed=1&macro_modal=1"
    return redirect_to_review(session_number, form.get("source") or "diary", form.get("view") or "raw", flag, form.get("bucket") or "")


@app.post("/sessions/{session}/review/merge")
async def merge_session_review_items(request: Request, session: str):
    try:
        session_number = reviews.parse_session_ref(session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    document = reviews.load_review_document(session_number)
    if not document:
        raise HTTPException(status_code=404, detail="Review file has not been initialized.")
    if document.get("status") == "applied":
        raise HTTPException(status_code=409, detail="Applied reviews are locked until explicitly reopened.")

    form = await request.form()
    updated, errors = reviews.merge_review_items(
        document,
        form.getlist("selected_item_id"),
        {
            "sequence": form.get("merge_sequence") or "",
            "canonical_text": form.get("merge_canonical_text") or "",
            "event_type": form.get("merge_event_type") or "",
            "location": form.get("merge_location") or "",
            "significance": form.get("merge_significance") or "",
            "reason": form.get("merge_reason") or "",
        },
    )
    if not errors:
        try:
            reviews.save_review_document(session_number, updated)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    flag = "merged=1" if not errors else "merge_failed=1"
    return redirect_to_review(session_number, form.get("source") or "diary", form.get("view") or "raw", flag)


@app.post("/sessions/{session}/review/create-location")
async def create_location_from_review(request: Request, session: str):
    try:
        session_number = reviews.parse_session_ref(session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    form = await request.form()
    name = (form.get("quick_location_name") or "").strip()
    if not name:
        return redirect_to_review(session_number, form.get("source") or "diary", form.get("view") or "raw", "location_add_failed=1")
    values = {
        "name": name,
        "location_type_id": optional_int(form.get("quick_location_type_id")),
        "parent_location_id": None,
        "description": (form.get("quick_location_description") or "").strip(),
        "is_underwater": False,
        "is_feywild": False,
        "first_visited_session": session_number,
        "notes": "Added from session review.",
    }
    try:
        canon.create_location(values)
    except canon.CanonWriteError:
        return redirect_to_review(session_number, form.get("source") or "diary", form.get("view") or "raw", "location_add_failed=1")
    return redirect_to_review(session_number, form.get("source") or "diary", form.get("view") or "raw", "location_added=1")


@app.post("/sessions/{session}/review/reopen")
async def reopen_session_review(request: Request, session: str):
    try:
        session_number = reviews.parse_session_ref(session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    document = reviews.load_review_document(session_number)
    if not document:
        raise HTTPException(status_code=404, detail="Review file has not been initialized.")

    updated = reviews.reopen_review_document(document)
    try:
        reviews.save_review_document(session_number, updated)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    form = await request.form()
    source = form.get("source") or "diary"
    view = form.get("view") or "raw"
    return redirect_to_review(session_number, source, view, "reopened=1")


@app.post("/sessions/{session}/review/add-item")
async def add_session_review_item(request: Request, session: str):
    try:
        session_number = reviews.parse_session_ref(session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    document = reviews.load_review_document(session_number)
    if not document:
        raise HTTPException(status_code=404, detail="Review file has not been initialized.")
    if document.get("status") == "applied":
        raise HTTPException(status_code=409, detail="Applied reviews are locked until explicitly reopened.")

    form = await request.form()
    item_values = {
        "sequence": form.get("new_sequence") or "",
        "canonical_text": form.get("new_canonical_text") or "",
        "event_type": form.get("new_event_type") or "",
        "location": form.get("new_location") or "",
        "significance": form.get("new_significance") or "",
        "reason": form.get("new_reason") or "",
    }
    updated, errors = reviews.add_review_item(document, item_values)
    if not errors:
        try:
            reviews.save_review_document(session_number, updated)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    source = form.get("source") or "diary"
    view = form.get("view") or "raw"
    flag = "item_added=1" if not errors else "item_add_failed=1"
    return redirect_to_review(session_number, source, view, flag)


@app.post("/sessions/{session}/review/remove-added-item")
async def remove_session_added_item(request: Request, session: str):
    try:
        session_number = reviews.parse_session_ref(session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    document = reviews.load_review_document(session_number)
    if not document:
        raise HTTPException(status_code=404, detail="Review file has not been initialized.")
    if document.get("status") == "applied":
        raise HTTPException(status_code=409, detail="Applied reviews are locked until explicitly reopened.")

    form = await request.form()
    updated, errors = reviews.remove_added_item(document, form.get("remove_item_id") or "")
    if not errors:
        try:
            reviews.save_review_document(session_number, updated)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    source = form.get("source") or "diary"
    view = form.get("view") or "raw"
    flag = "item_removed=1" if not errors else "item_remove_failed=1"
    return redirect_to_review(session_number, source, view, flag)


@app.post("/sessions/{session}/review/mark-reviewed")
async def mark_session_reviewed(request: Request, session: str):
    try:
        session_number = reviews.parse_session_ref(session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    document = reviews.load_review_document(session_number)
    if not document:
        raise HTTPException(status_code=404, detail="Review file has not been initialized.")
    if document.get("status") == "applied":
        raise HTTPException(status_code=409, detail="Applied reviews are locked until explicitly reopened.")

    form = await request.form()
    form_values = {key: form.getlist(key) for key in form.keys()}
    if reviews.final_summary_mode(document) or "final_summary_markdown" in form:
        updated = reviews.update_final_summary_from_form(document, form_values)
    else:
        updated = reviews.update_review_document_from_form(document, form_values)
    marked, errors = reviews.mark_reviewed_document(updated)
    try:
        reviews.save_review_document(session_number, marked)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    try:
        workflow.sync_session_workflow(session_number)
    except workflow.WorkflowWriteError:
        pass

    source = form.get("source") or "narrative"
    view = form.get("view") or "raw"
    if errors:
        result = commands.CommandResult(1, "", "\n".join(errors))
        token = store_command_result("Mark Reviewed Validation", result)
        flag = f"mark_failed=1&command_result={token}"
    else:
        flag = "marked=1"
    return redirect_to_review(session_number, source, view, flag)


@app.post("/sessions/{session}/review/apply")
async def apply_session_review(request: Request, session: str):
    try:
        session_number = reviews.parse_session_ref(session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    document = reviews.load_review_document(session_number)
    if not document:
        raise HTTPException(status_code=404, detail="Review file has not been initialized.")
    if document.get("status") != "reviewed":
        raise HTTPException(status_code=409, detail="Review must be marked reviewed before applying.")

    form = await request.form()
    result = commands.apply_review(session_number)
    try:
        workflow.sync_session_workflow(session_number)
    except workflow.WorkflowWriteError:
        pass
    source = form.get("source") or "diary"
    view = form.get("view") or "raw"
    flag = "applied=1" if result.ok else "apply_failed=1"
    token = store_command_result("Apply to Database", result)
    return redirect_to_review(session_number, source, view, f"{flag}&command_result={token}")


@app.post("/sessions/{session}/review/write-final-summary")
async def write_session_final_summary(request: Request, session: str):
    try:
        session_number = reviews.parse_session_ref(session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    document = reviews.load_review_document(session_number)
    if not document:
        raise HTTPException(status_code=404, detail="Review file has not been initialized.")
    if document.get("status") != "applied":
        raise HTTPException(status_code=409, detail="Review must be applied before writing final summary.")

    form = await request.form()
    result = commands.write_final_summary(session_number)
    try:
        workflow.sync_session_workflow(session_number)
    except workflow.WorkflowWriteError:
        pass
    source = form.get("source") or "diary"
    view = form.get("view") or "raw"
    flag = "final_written=1" if result.ok else "final_failed=1"
    token = store_command_result("Write Final Summary", result)
    return redirect_to_review(session_number, source, view, f"{flag}&command_result={token}")


@app.post("/sessions/{session}/review/health")
async def run_session_health(request: Request, session: str):
    try:
        session_number = reviews.parse_session_ref(session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    form = await request.form()
    result = commands.run_health(session_number=session_number)
    source = form.get("source") or "diary"
    view = form.get("view") or "raw"
    flag = "health_ok=1" if result.ok else "health_failed=1"
    token = store_command_result("Run Health", result)
    return redirect_to_review(session_number, source, view, f"{flag}&command_result={token}")


@app.get("/locations", response_class=HTMLResponse)
def locations_index(request: Request, modal: str = ""):
    try:
        rows = canon.location_rows()
        location_types = canon.location_types()
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return templates.TemplateResponse(
        request,
        "locations.html",
        {
            "locations": rows,
            "location_types": location_types,
            "all_locations": rows,
            "editing": None,
            "show_location_modal": can_edit() and modal == "add",
        },
    )


@app.get("/locations/extractions", response_class=HTMLResponse)
def location_extraction_review_page(request: Request, session: Optional[int] = None):
    if not can_edit():
        raise HTTPException(status_code=404, detail="Location extraction review is not available in archive mode.")
    sessions = location_extraction_review.available_sessions()
    session_number = session if session is not None else (sessions[-1] if sessions else 21)
    try:
        extraction = location_extraction_review.load_extraction(session_number)
    except FileNotFoundError:
        extraction = None
    return templates.TemplateResponse(
        request,
        "location_extraction_review.html",
        {
            "session_number": session_number,
            "available_sessions": sessions,
            "extraction": extraction,
            "reviewed_path": location_extraction_review.reviewed_output_path(session_number),
            "command_result": COMMAND_RESULTS.get(request.query_params.get("command_result", "")),
        },
    )


@app.post("/locations/extractions/apply")
async def apply_location_extraction_review(request: Request):
    if not can_edit():
        raise HTTPException(status_code=404, detail="Location extraction review is not available in archive mode.")
    form = await request.form()
    session_number = optional_int(form.get("session_number")) or 0
    try:
        result = location_extraction_review.apply_review(session_number, form_dict(form))
    except (FileNotFoundError, canon.CanonReadError, canon.CanonWriteError, location_extraction_review.LocationExtractionReviewError) as exc:
        token = store_command_result(
            "Apply Location Extraction Review",
            commands.CommandResult(1, "", str(exc)),
        )
        return RedirectResponse(url=f"/locations/extractions?session={session_number}&apply_failed=1&command_result={token}", status_code=303)
    post_apply_messages = sync_after_extraction_review(session_number)
    token = store_command_result(
        "Apply Location Extraction Review",
        commands.CommandResult(
            0,
            "\n".join([
                "Location extraction review applied.",
                f"Applied: {len(result['applied'])}",
                f"Skipped: {len(result['skipped'])}",
                f"Review decisions: {result['reviewed_path']}",
                "",
                *result["applied"],
                *post_apply_messages,
            ]),
            "",
        ),
    )
    return RedirectResponse(url=f"/locations/extractions?session={session_number}&command_result={token}", status_code=303)


@app.post("/locations")
async def create_location(request: Request):
    form = await request.form()
    values = location_form_values(form)
    if not values["name"]:
        return RedirectResponse(url="/locations?create_failed=1", status_code=303)
    try:
        canon.create_location(values)
    except canon.CanonWriteError:
        return RedirectResponse(url="/locations?create_failed=1", status_code=303)
    return RedirectResponse(url="/locations?created=1", status_code=303)


@app.get("/locations/{location_id}/edit", response_class=HTMLResponse)
def edit_location(request: Request, location_id: int):
    if not can_edit():
        return RedirectResponse(url="/locations", status_code=303)
    try:
        rows = canon.location_rows()
        location_types = canon.location_types()
        editing = canon.location_detail(location_id)
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if not editing:
        raise HTTPException(status_code=404, detail="Location not found.")
    return templates.TemplateResponse(
        request,
        "locations.html",
        {
            "locations": rows,
            "location_types": location_types,
            "all_locations": [row for row in rows if row["id"] != location_id],
            "editing": editing,
            "show_location_modal": True,
        },
    )


@app.post("/locations/{location_id}")
async def update_location(request: Request, location_id: int):
    form = await request.form()
    values = location_form_values(form)
    if not values["name"]:
        return RedirectResponse(url=f"/locations/{location_id}/edit?update_failed=1", status_code=303)
    try:
        canon.update_location(location_id, values)
    except canon.CanonWriteError:
        return RedirectResponse(url=f"/locations/{location_id}/edit?update_failed=1", status_code=303)
    return RedirectResponse(url="/locations?updated=1", status_code=303)


@app.post("/locations/{location_id}/delete")
async def delete_location(location_id: int):
    try:
        canon.delete_location(location_id)
    except canon.CanonWriteError:
        return RedirectResponse(url="/locations?delete_failed=1", status_code=303)
    return RedirectResponse(url="/locations?deleted=1", status_code=303)


@app.get("/npcs", response_class=HTMLResponse)
def npcs_index(request: Request, modal: str = ""):
    try:
        rows = canon.npc_rows()
        statuses = canon.entity_statuses()
        factions = canon.factions()
        locations = canon.location_rows()
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return templates.TemplateResponse(
        request,
        "npcs.html",
        {
            "npcs": rows,
            "statuses": statuses,
            "factions": factions,
            "locations": locations,
            "editing": None,
            "show_npc_modal": can_edit() and modal == "add",
        },
    )


@app.get("/npcs/extractions", response_class=HTMLResponse)
def npc_extraction_review_page(request: Request, session: Optional[int] = None):
    if not can_edit():
        raise HTTPException(status_code=404, detail="NPC extraction review is not available in archive mode.")
    sessions = npc_extraction_review.available_sessions()
    session_number = session if session is not None else (sessions[-1] if sessions else 21)
    try:
        extraction = npc_extraction_review.load_extraction(session_number)
    except FileNotFoundError:
        extraction = None
    return templates.TemplateResponse(
        request,
        "npc_extraction_review.html",
        {
            "session_number": session_number,
            "available_sessions": sessions,
            "extraction": extraction,
            "reviewed_path": npc_extraction_review.reviewed_output_path(session_number),
            "command_result": COMMAND_RESULTS.get(request.query_params.get("command_result", "")),
        },
    )


@app.post("/npcs/extractions/apply")
async def apply_npc_extraction_review(request: Request):
    if not can_edit():
        raise HTTPException(status_code=404, detail="NPC extraction review is not available in archive mode.")
    form = await request.form()
    session_number = optional_int(form.get("session_number")) or 0
    try:
        result = npc_extraction_review.apply_review(session_number, form_dict(form))
    except (FileNotFoundError, canon.CanonReadError, canon.CanonWriteError, npc_extraction_review.NpcExtractionReviewError) as exc:
        token = store_command_result("Apply NPC Extraction Review", commands.CommandResult(1, "", str(exc)))
        return RedirectResponse(url=f"/npcs/extractions?session={session_number}&apply_failed=1&command_result={token}", status_code=303)
    post_apply_messages = sync_after_extraction_review(session_number)
    token = store_command_result(
        "Apply NPC Extraction Review",
        commands.CommandResult(
            0,
            "\n".join([
                "NPC extraction review applied.",
                f"Applied: {len(result['applied'])}",
                f"Skipped: {len(result['skipped'])}",
                f"Review decisions: {result['reviewed_path']}",
                "",
                *result["applied"],
                *post_apply_messages,
            ]),
            "",
        ),
    )
    return RedirectResponse(url=f"/npcs/extractions?session={session_number}&command_result={token}", status_code=303)


@app.post("/npcs")
async def create_npc(request: Request):
    form = await request.form()
    values = npc_form_values(form)
    if not values["name"]:
        return RedirectResponse(url="/npcs?create_failed=1", status_code=303)
    try:
        canon.create_npc(values)
    except canon.CanonWriteError:
        return RedirectResponse(url="/npcs?create_failed=1", status_code=303)
    return RedirectResponse(url="/npcs?created=1", status_code=303)


@app.get("/npcs/{npc_id}/edit", response_class=HTMLResponse)
def edit_npc(request: Request, npc_id: int):
    if not can_edit():
        return RedirectResponse(url="/npcs", status_code=303)
    try:
        rows = canon.npc_rows()
        statuses = canon.entity_statuses()
        factions = canon.factions()
        locations = canon.location_rows()
        editing = canon.npc_detail(npc_id)
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if not editing:
        raise HTTPException(status_code=404, detail="NPC not found.")
    return templates.TemplateResponse(
        request,
        "npcs.html",
        {
            "npcs": rows,
            "statuses": statuses,
            "factions": factions,
            "locations": locations,
            "editing": editing,
            "show_npc_modal": True,
        },
    )


@app.post("/npcs/{npc_id}")
async def update_npc(request: Request, npc_id: int):
    form = await request.form()
    values = npc_form_values(form)
    if not values["name"]:
        return RedirectResponse(url=f"/npcs/{npc_id}/edit?update_failed=1", status_code=303)
    try:
        canon.update_npc(npc_id, values)
    except canon.CanonWriteError:
        return RedirectResponse(url=f"/npcs/{npc_id}/edit?update_failed=1", status_code=303)
    return RedirectResponse(url="/npcs?updated=1", status_code=303)


@app.post("/npcs/{npc_id}/delete")
async def delete_npc(npc_id: int):
    try:
        canon.delete_npc(npc_id)
    except canon.CanonWriteError:
        return RedirectResponse(url="/npcs?delete_failed=1", status_code=303)
    return RedirectResponse(url="/npcs?deleted=1", status_code=303)


@app.get("/artifacts", response_class=HTMLResponse)
def artifacts_index(request: Request, modal: str = ""):
    try:
        rows = canon.artifact_rows()
        artifact_types = canon.artifact_types()
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return templates.TemplateResponse(
        request,
        "artifacts.html",
        {
            "artifacts": rows,
            "artifact_types": artifact_types,
            "editing": None,
            "show_artifact_modal": can_edit() and modal == "add",
        },
    )


@app.get("/artifacts/extractions", response_class=HTMLResponse)
def artifact_extraction_review_page(request: Request, session: Optional[int] = None):
    if not can_edit():
        raise HTTPException(status_code=404, detail="Artifact extraction review is not available in archive mode.")
    sessions = artifact_extraction_review.available_sessions()
    session_number = session if session is not None else (sessions[-1] if sessions else 21)
    try:
        extraction = artifact_extraction_review.load_extraction(session_number)
    except FileNotFoundError:
        extraction = None
    return templates.TemplateResponse(
        request,
        "artifact_extraction_review.html",
        {
            "session_number": session_number,
            "available_sessions": sessions,
            "extraction": extraction,
            "reviewed_path": artifact_extraction_review.reviewed_output_path(session_number),
            "command_result": COMMAND_RESULTS.get(request.query_params.get("command_result", "")),
        },
    )


@app.post("/artifacts/extractions/apply")
async def apply_artifact_extraction_review(request: Request):
    if not can_edit():
        raise HTTPException(status_code=404, detail="Artifact extraction review is not available in archive mode.")
    form = await request.form()
    session_number = optional_int(form.get("session_number")) or 0
    try:
        result = artifact_extraction_review.apply_review(session_number, form_dict(form))
    except (FileNotFoundError, canon.CanonReadError, canon.CanonWriteError, artifact_extraction_review.ArtifactExtractionReviewError) as exc:
        token = store_command_result("Apply Artifact Extraction Review", commands.CommandResult(1, "", str(exc)))
        return RedirectResponse(url=f"/artifacts/extractions?session={session_number}&apply_failed=1&command_result={token}", status_code=303)
    post_apply_messages = sync_after_extraction_review(session_number)
    token = store_command_result(
        "Apply Artifact Extraction Review",
        commands.CommandResult(
            0,
            "\n".join([
                "Artifact extraction review applied.",
                f"Applied: {len(result['applied'])}",
                f"Skipped: {len(result['skipped'])}",
                f"Review decisions: {result['reviewed_path']}",
                "",
                *result["applied"],
                *post_apply_messages,
            ]),
            "",
        ),
    )
    return RedirectResponse(url=f"/artifacts/extractions?session={session_number}&command_result={token}", status_code=303)


@app.post("/artifacts")
async def create_artifact(request: Request):
    form = await request.form()
    values = artifact_form_values(form)
    if not values["name"]:
        return RedirectResponse(url="/artifacts?create_failed=1", status_code=303)
    try:
        canon.create_artifact(values)
    except canon.CanonWriteError:
        return RedirectResponse(url="/artifacts?create_failed=1", status_code=303)
    return RedirectResponse(url="/artifacts?created=1", status_code=303)


@app.get("/artifacts/{artifact_id}/edit", response_class=HTMLResponse)
def edit_artifact(request: Request, artifact_id: int):
    if not can_edit():
        return RedirectResponse(url="/artifacts", status_code=303)
    try:
        rows = canon.artifact_rows()
        artifact_types = canon.artifact_types()
        editing = canon.artifact_detail(artifact_id)
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if not editing:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    return templates.TemplateResponse(
        request,
        "artifacts.html",
        {
            "artifacts": rows,
            "artifact_types": artifact_types,
            "editing": editing,
            "show_artifact_modal": True,
        },
    )


@app.post("/artifacts/{artifact_id}")
async def update_artifact(request: Request, artifact_id: int):
    form = await request.form()
    values = artifact_form_values(form)
    if not values["name"]:
        return RedirectResponse(url=f"/artifacts/{artifact_id}/edit?update_failed=1", status_code=303)
    try:
        canon.update_artifact(artifact_id, values)
    except canon.CanonWriteError:
        return RedirectResponse(url=f"/artifacts/{artifact_id}/edit?update_failed=1", status_code=303)
    return RedirectResponse(url="/artifacts?updated=1", status_code=303)


@app.post("/artifacts/{artifact_id}/delete")
async def delete_artifact(artifact_id: int):
    try:
        canon.delete_artifact(artifact_id)
    except canon.CanonWriteError:
        return RedirectResponse(url="/artifacts?delete_failed=1", status_code=303)
    return RedirectResponse(url="/artifacts?deleted=1", status_code=303)


@app.get("/lore-items", response_class=HTMLResponse)
def lore_items_index(request: Request, modal: str = ""):
    try:
        rows = canon.lore_item_rows()
        categories = canon.lore_categories()
        npcs = canon.npc_rows()
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return templates.TemplateResponse(
        request,
        "lore_items.html",
        {
            "lore_items": rows,
            "categories": categories,
            "npcs": npcs,
            "editing": None,
            "show_lore_modal": can_edit() and modal == "add",
        },
    )


@app.get("/lore-items/extractions", response_class=HTMLResponse)
def lore_item_extraction_review_page(request: Request, session: Optional[int] = None):
    if not can_edit():
        raise HTTPException(status_code=404, detail="Lore item extraction review is not available in archive mode.")
    sessions = lore_item_extraction_review.available_sessions()
    session_number = session if session is not None else (sessions[-1] if sessions else 21)
    try:
        extraction = lore_item_extraction_review.load_extraction(session_number)
    except FileNotFoundError:
        extraction = None
    return templates.TemplateResponse(
        request,
        "lore_item_extraction_review.html",
        {
            "session_number": session_number,
            "available_sessions": sessions,
            "extraction": extraction,
            "reviewed_path": lore_item_extraction_review.reviewed_output_path(session_number),
            "command_result": COMMAND_RESULTS.get(request.query_params.get("command_result", "")),
        },
    )


@app.post("/lore-items/extractions/apply")
async def apply_lore_item_extraction_review(request: Request):
    if not can_edit():
        raise HTTPException(status_code=404, detail="Lore item extraction review is not available in archive mode.")
    form = await request.form()
    session_number = optional_int(form.get("session_number")) or 0
    try:
        result = lore_item_extraction_review.apply_review(session_number, form_dict(form))
    except (FileNotFoundError, canon.CanonReadError, canon.CanonWriteError, lore_item_extraction_review.LoreItemExtractionReviewError) as exc:
        token = store_command_result("Apply Lore Item Extraction Review", commands.CommandResult(1, "", str(exc)))
        return RedirectResponse(url=f"/lore-items/extractions?session={session_number}&apply_failed=1&command_result={token}", status_code=303)
    post_apply_messages = sync_after_extraction_review(session_number)
    token = store_command_result(
        "Apply Lore Item Extraction Review",
        commands.CommandResult(
            0,
            "\n".join([
                "Lore item extraction review applied.",
                f"Applied: {len(result['applied'])}",
                f"Skipped: {len(result['skipped'])}",
                f"Review decisions: {result['reviewed_path']}",
                "",
                *result["applied"],
                *post_apply_messages,
            ]),
            "",
        ),
    )
    return RedirectResponse(url=f"/lore-items/extractions?session={session_number}&command_result={token}", status_code=303)


@app.post("/lore-items")
async def create_lore_item(request: Request):
    form = await request.form()
    values = lore_item_form_values(form)
    if not values["title"] or not values["description"]:
        return RedirectResponse(url="/lore-items?create_failed=1", status_code=303)
    try:
        canon.create_lore_item(values)
    except canon.CanonWriteError:
        return RedirectResponse(url="/lore-items?create_failed=1", status_code=303)
    return RedirectResponse(url="/lore-items?created=1", status_code=303)


@app.get("/lore-items/{lore_item_id}/edit", response_class=HTMLResponse)
def edit_lore_item(request: Request, lore_item_id: int):
    if not can_edit():
        return RedirectResponse(url="/lore-items", status_code=303)
    try:
        rows = canon.lore_item_rows()
        categories = canon.lore_categories()
        npcs = canon.npc_rows()
        editing = canon.lore_item_detail(lore_item_id)
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if not editing:
        raise HTTPException(status_code=404, detail="Lore item not found.")
    return templates.TemplateResponse(
        request,
        "lore_items.html",
        {
            "lore_items": rows,
            "categories": categories,
            "npcs": npcs,
            "editing": editing,
            "show_lore_modal": True,
        },
    )


@app.post("/lore-items/{lore_item_id}")
async def update_lore_item(request: Request, lore_item_id: int):
    form = await request.form()
    values = lore_item_form_values(form)
    if not values["title"] or not values["description"]:
        return RedirectResponse(url=f"/lore-items/{lore_item_id}/edit?update_failed=1", status_code=303)
    try:
        canon.update_lore_item(lore_item_id, values)
    except canon.CanonWriteError:
        return RedirectResponse(url=f"/lore-items/{lore_item_id}/edit?update_failed=1", status_code=303)
    return RedirectResponse(url="/lore-items?updated=1", status_code=303)


@app.post("/lore-items/{lore_item_id}/delete")
async def delete_lore_item(lore_item_id: int):
    try:
        canon.delete_lore_item(lore_item_id)
    except canon.CanonWriteError:
        return RedirectResponse(url="/lore-items?delete_failed=1", status_code=303)
    return RedirectResponse(url="/lore-items?deleted=1", status_code=303)


@app.get("/open-threads", response_class=HTMLResponse)
def open_threads_index(request: Request, modal: str = ""):
    try:
        rows = canon.open_thread_rows()
        locations = canon.location_rows()
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return templates.TemplateResponse(
        request,
        "open_threads.html",
        {
            "threads": rows,
            "statuses": canon.open_thread_statuses(),
            "thread_types": canon.open_thread_types(),
            "locations": locations,
            "editing": None,
            "show_thread_modal": can_edit() and modal == "add",
        },
    )


@app.post("/open-threads")
async def create_open_thread(request: Request):
    form = await request.form()
    values = open_thread_form_values(form)
    if not values["title"]:
        return RedirectResponse(url="/open-threads?create_failed=1", status_code=303)
    try:
        canon.create_open_thread(values)
    except canon.CanonWriteError:
        return RedirectResponse(url="/open-threads?create_failed=1", status_code=303)
    return RedirectResponse(url="/open-threads?created=1", status_code=303)


@app.get("/open-threads/extractions", response_class=HTMLResponse)
def open_thread_extraction_review_page(request: Request, session: Optional[int] = None):
    if not can_edit():
        raise HTTPException(status_code=404, detail="Open thread extraction review is not available in archive mode.")
    sessions = open_thread_extraction_review.available_sessions()
    session_number = session if session is not None else (sessions[-1] if sessions else 21)
    try:
        extraction = open_thread_extraction_review.load_extraction(session_number)
    except FileNotFoundError:
        extraction = None
    return templates.TemplateResponse(
        request,
        "open_thread_extraction_review.html",
        {
            "session_number": session_number,
            "available_sessions": sessions,
            "extraction": extraction,
            "reviewed_path": open_thread_extraction_review.reviewed_output_path(session_number),
            "command_result": COMMAND_RESULTS.get(request.query_params.get("command_result", "")),
        },
    )


@app.post("/open-threads/extractions/apply")
async def apply_open_thread_extraction_review(request: Request):
    if not can_edit():
        raise HTTPException(status_code=404, detail="Open thread extraction review is not available in archive mode.")
    form = await request.form()
    session_number = optional_int(form.get("session_number")) or 0
    try:
        result = open_thread_extraction_review.apply_review(session_number, form_dict(form))
    except (FileNotFoundError, canon.CanonReadError, canon.CanonWriteError, open_thread_extraction_review.OpenThreadExtractionReviewError) as exc:
        token = store_command_result("Apply Open Thread Extraction Review", commands.CommandResult(1, "", str(exc)))
        return RedirectResponse(url=f"/open-threads/extractions?session={session_number}&apply_failed=1&command_result={token}", status_code=303)
    post_apply_messages = sync_after_extraction_review(session_number)
    token = store_command_result(
        "Apply Open Thread Extraction Review",
        commands.CommandResult(
            0,
            "\n".join([
                "Open thread extraction review applied.",
                f"Applied: {len(result['applied'])}",
                f"Skipped: {len(result['skipped'])}",
                f"Review decisions: {result['reviewed_path']}",
                "",
                *result["applied"],
                *post_apply_messages,
            ]),
            "",
        ),
    )
    return RedirectResponse(url=f"/open-threads/extractions?session={session_number}&command_result={token}", status_code=303)


@app.get("/open-threads/{thread_id}/edit", response_class=HTMLResponse)
def edit_open_thread(request: Request, thread_id: int):
    if not can_edit():
        return RedirectResponse(url="/open-threads", status_code=303)
    try:
        rows = canon.open_thread_rows()
        locations = canon.location_rows()
        editing = canon.open_thread_detail(thread_id)
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if not editing:
        raise HTTPException(status_code=404, detail="Open thread not found.")
    return templates.TemplateResponse(
        request,
        "open_threads.html",
        {
            "threads": rows,
            "statuses": canon.open_thread_statuses(),
            "thread_types": canon.open_thread_types(),
            "locations": locations,
            "editing": editing,
            "show_thread_modal": True,
        },
    )


@app.post("/open-threads/{thread_id}")
async def update_open_thread(request: Request, thread_id: int):
    form = await request.form()
    values = open_thread_form_values(form)
    if not values["title"]:
        return RedirectResponse(url=f"/open-threads/{thread_id}/edit?update_failed=1", status_code=303)
    try:
        canon.update_open_thread(thread_id, values)
    except canon.CanonWriteError:
        return RedirectResponse(url=f"/open-threads/{thread_id}/edit?update_failed=1", status_code=303)
    return RedirectResponse(url="/open-threads?updated=1", status_code=303)


@app.post("/open-threads/{thread_id}/delete")
async def delete_open_thread(thread_id: int):
    try:
        canon.delete_open_thread(thread_id)
    except canon.CanonWriteError:
        return RedirectResponse(url="/open-threads?delete_failed=1", status_code=303)
    return RedirectResponse(url="/open-threads?deleted=1", status_code=303)


@app.get("/combat-encounters", response_class=HTMLResponse)
def combat_encounters_index(request: Request, modal: str = ""):
    try:
        rows = canon.combat_encounter_rows()
        sessions = canon.session_rows()
        locations = canon.location_rows()
        outcomes = canon.lookup_rows("combat-outcomes")
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return templates.TemplateResponse(
        request,
        "combat_encounters.html",
        {
            "encounters": rows,
            "murder_hobo_count": canon.murder_hobo_count(rows),
            "sessions": sessions,
            "locations": locations,
            "outcomes": outcomes,
            "editing": None,
            "show_combat_modal": can_edit() and modal == "add",
        },
    )


@app.get("/combat-encounters/extractions", response_class=HTMLResponse)
def combat_extraction_review_page(request: Request, session: Optional[int] = None):
    if not can_edit():
        raise HTTPException(status_code=404, detail="Combat extraction review is not available in archive mode.")
    sessions = combat_extraction_review.available_sessions()
    session_number = session if session is not None else (sessions[-1] if sessions else 21)
    try:
        extraction = combat_extraction_review.load_extraction(session_number)
    except FileNotFoundError:
        extraction = None
    return templates.TemplateResponse(
        request,
        "combat_extraction_review.html",
        {
            "session_number": session_number,
            "available_sessions": sessions,
            "extraction": extraction,
            "reviewed_path": combat_extraction_review.reviewed_output_path(session_number),
            "command_result": COMMAND_RESULTS.get(request.query_params.get("command_result", "")),
        },
    )


@app.post("/combat-encounters/extractions/apply")
async def apply_combat_extraction_review(request: Request):
    if not can_edit():
        raise HTTPException(status_code=404, detail="Combat extraction review is not available in archive mode.")
    form = await request.form()
    session_number = optional_int(form.get("session_number")) or 0
    try:
        result = combat_extraction_review.apply_review(session_number, form_dict(form))
    except (FileNotFoundError, canon.CanonReadError, canon.CanonWriteError, combat_extraction_review.CombatExtractionReviewError) as exc:
        token = store_command_result("Apply Combat Extraction Review", commands.CommandResult(1, "", str(exc)))
        return RedirectResponse(url=f"/combat-encounters/extractions?session={session_number}&apply_failed=1&command_result={token}", status_code=303)
    post_apply_messages = sync_after_extraction_review(session_number)
    token = store_command_result(
        "Apply Combat Extraction Review",
        commands.CommandResult(
            0,
            "\n".join([
                "Combat extraction review applied.",
                f"Applied: {len(result['applied'])}",
                f"Skipped: {len(result['skipped'])}",
                f"Review decisions: {result['reviewed_path']}",
                "",
                *result["applied"],
                *post_apply_messages,
            ]),
            "",
        ),
    )
    return RedirectResponse(url=f"/combat-encounters/extractions?session={session_number}&command_result={token}", status_code=303)


@app.post("/combat-encounters")
async def create_combat_encounter(request: Request):
    form = await request.form()
    values, enemies = combat_encounter_form_values(form)
    if not values["session_number"] or not values["title"]:
        return RedirectResponse(url="/combat-encounters?create_failed=1", status_code=303)
    try:
        canon.create_combat_encounter(values, enemies)
    except canon.CanonWriteError:
        return RedirectResponse(url="/combat-encounters?create_failed=1", status_code=303)
    return RedirectResponse(url="/combat-encounters?created=1", status_code=303)


@app.get("/combat-encounters/{encounter_id}/edit", response_class=HTMLResponse)
def edit_combat_encounter(request: Request, encounter_id: int):
    if not can_edit():
        return RedirectResponse(url="/combat-encounters", status_code=303)
    try:
        rows = canon.combat_encounter_rows()
        sessions = canon.session_rows()
        locations = canon.location_rows()
        outcomes = canon.lookup_rows("combat-outcomes")
        editing = canon.combat_encounter_detail(encounter_id)
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if not editing:
        raise HTTPException(status_code=404, detail="Combat encounter not found.")
    return templates.TemplateResponse(
        request,
        "combat_encounters.html",
        {
            "encounters": rows,
            "murder_hobo_count": canon.murder_hobo_count(rows),
            "sessions": sessions,
            "locations": locations,
            "outcomes": outcomes,
            "editing": editing,
            "show_combat_modal": True,
        },
    )


@app.post("/combat-encounters/{encounter_id}")
async def update_combat_encounter(request: Request, encounter_id: int):
    form = await request.form()
    values, enemies = combat_encounter_form_values(form)
    if not values["session_number"] or not values["title"]:
        return RedirectResponse(url=f"/combat-encounters/{encounter_id}/edit?update_failed=1", status_code=303)
    try:
        canon.update_combat_encounter(encounter_id, values, enemies)
    except canon.CanonWriteError:
        return RedirectResponse(url=f"/combat-encounters/{encounter_id}/edit?update_failed=1", status_code=303)
    return RedirectResponse(url="/combat-encounters?updated=1", status_code=303)


@app.post("/combat-encounters/{encounter_id}/delete")
async def delete_combat_encounter(encounter_id: int):
    try:
        canon.delete_combat_encounter(encounter_id)
    except canon.CanonWriteError:
        return RedirectResponse(url="/combat-encounters?delete_failed=1", status_code=303)
    return RedirectResponse(url="/combat-encounters?deleted=1", status_code=303)


@app.get("/timeline", response_class=HTMLResponse)
def timeline_index(request: Request):
    try:
        timeline = canon.campaign_timeline()
        locations = canon.locations()
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return templates.TemplateResponse(
        request,
        "timeline.html",
        {"timeline": timeline, "locations": locations},
    )


@app.post("/timeline/session/{session_number}/update")
async def update_timeline_session(request: Request, session_number: int):
    if not can_edit():
        raise HTTPException(status_code=404, detail="Timeline editing is not available in archive mode.")
    form = await request.form()
    current = canon.session_timeline_detail(session_number)
    if not current:
        raise HTTPException(status_code=404, detail="Session was not found.")
    known_locations = canon_location_names()
    location_values = {
        "new_location": [
            timeline_form_text(form, "primary_location", current),
            timeline_form_text(form, "start_location", current),
            timeline_form_text(form, "end_location", current),
        ]
    }
    if location_confirmation_failed(location_values, form, known_locations):
        return RedirectResponse(url=f"/timeline?location_confirm_failed=1#edit-session-{session_number:02d}-modal", status_code=303)
    if not create_missing_review_locations(
        reviews.form_locations(location_values),
        known_locations,
        session_number,
        "Created from campaign timeline edit.",
    ):
        return RedirectResponse(url=f"/timeline?location_create_failed=1#edit-session-{session_number:02d}-modal", status_code=303)
    try:
        canon.update_session_timeline(session_number, timeline_form_values(form, current))
        workflow.sync_session_workflow(session_number)
    except (canon.CanonWriteError, workflow.WorkflowWriteError):
        return RedirectResponse(url=f"/timeline?update_failed=1#edit-session-{session_number:02d}-modal", status_code=303)
    return RedirectResponse(url=f"/timeline?updated=1#session-{session_number:02d}-modal", status_code=303)


@app.get("/project-utilities", response_class=HTMLResponse)
def project_utilities(request: Request, document: str = "todo", command_result: str = "", backup: str = "", modal: str = ""):
    if not can_edit():
        raise HTTPException(status_code=404, detail="Project utilities are not available in archive mode.")
    try:
        active_document = project_document(document)
    except OSError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    try:
        next_session = workflow.next_session_number()
    except workflow.WorkflowReadError:
        next_session = 0
    return templates.TemplateResponse(
        request,
        "project_utilities.html",
        {
            "active_document": active_document,
            "command_result": COMMAND_RESULTS.get(command_result) if command_result else None,
            "backup": BACKUP_DOWNLOADS.get(backup) if backup else None,
            "next_session_number": next_session,
            "today": date.today().isoformat(),
            "show_session_modal": modal == "initiate-session",
        },
    )


@app.post("/project-utilities/initiate-session")
async def project_utilities_initiate_session(request: Request):
    if not can_edit():
        raise HTTPException(status_code=404, detail="Project utilities are not available in archive mode.")
    form = await request.form()
    values = session_initiation_form_values(form)
    try:
        session_number = workflow.initiate_session(values)
    except workflow.WorkflowWriteError as exc:
        token = store_command_result("Initiate Session", commands.CommandResult(1, "", str(exc)))
        return RedirectResponse(url=f"/project-utilities?command_result={token}&modal=initiate-session", status_code=303)
    if workflow.auto_intake_enabled():
        try:
            workflow.enqueue_auto_intake(session_number, values.get("transcript_policy", "use_existing"))
        except workflow.WorkflowWriteError as exc:
            token = store_command_result("Queue Auto Intake", commands.CommandResult(1, "", str(exc)))
            return RedirectResponse(url=f"/project-utilities?command_result={token}&modal=initiate-session", status_code=303)
    return RedirectResponse(url=f"/workflow?session={session_number}", status_code=303)


@app.get("/project-utilities/lookups", response_class=HTMLResponse)
def project_lookup_tables(request: Request, table: str = "artifact-types", modal: str = ""):
    if not can_edit():
        raise HTTPException(status_code=404, detail="Project utilities are not available in archive mode.")
    try:
        context = lookup_context(table, show_modal=(modal == "add"))
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return templates.TemplateResponse(request, "project_lookups.html", context)


@app.get("/project-utilities/lookups/{lookup_key}/{lookup_id}/edit", response_class=HTMLResponse)
def edit_project_lookup_value(request: Request, lookup_key: str, lookup_id: int):
    if not can_edit():
        raise HTTPException(status_code=404, detail="Project utilities are not available in archive mode.")
    try:
        context = lookup_context(lookup_key, editing_id=lookup_id, show_modal=True)
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return templates.TemplateResponse(request, "project_lookups.html", context)


@app.post("/project-utilities/lookups/{lookup_key}")
async def create_project_lookup_value(request: Request, lookup_key: str):
    if not can_edit():
        raise HTTPException(status_code=404, detail="Project utilities are not available in archive mode.")
    form = await request.form()
    values = lookup_form_values(form)
    if not values["value"]:
        return RedirectResponse(url=f"/project-utilities/lookups?table={lookup_key}&create_failed=1", status_code=303)
    try:
        canon.create_lookup_value(lookup_key, values["value"], values["description"])
    except (canon.CanonReadError, canon.CanonWriteError):
        return RedirectResponse(url=f"/project-utilities/lookups?table={lookup_key}&create_failed=1", status_code=303)
    return RedirectResponse(url=f"/project-utilities/lookups?table={lookup_key}&created=1", status_code=303)


@app.post("/project-utilities/lookups/{lookup_key}/{lookup_id}")
async def update_project_lookup_value(request: Request, lookup_key: str, lookup_id: int):
    if not can_edit():
        raise HTTPException(status_code=404, detail="Project utilities are not available in archive mode.")
    form = await request.form()
    values = lookup_form_values(form)
    if not values["value"]:
        return RedirectResponse(url=f"/project-utilities/lookups/{lookup_key}/{lookup_id}/edit?update_failed=1", status_code=303)
    try:
        canon.update_lookup_value(lookup_key, lookup_id, values["value"], values["description"])
    except (canon.CanonReadError, canon.CanonWriteError):
        return RedirectResponse(url=f"/project-utilities/lookups/{lookup_key}/{lookup_id}/edit?update_failed=1", status_code=303)
    return RedirectResponse(url=f"/project-utilities/lookups?table={lookup_key}&updated=1", status_code=303)


@app.post("/project-utilities/lookups/{lookup_key}/{lookup_id}/delete")
def delete_project_lookup_value(lookup_key: str, lookup_id: int):
    if not can_edit():
        raise HTTPException(status_code=404, detail="Project utilities are not available in archive mode.")
    try:
        canon.delete_lookup_value(lookup_key, lookup_id)
    except (canon.CanonReadError, canon.CanonWriteError):
        return RedirectResponse(url=f"/project-utilities/lookups?table={lookup_key}&delete_failed=1", status_code=303)
    return RedirectResponse(url=f"/project-utilities/lookups?table={lookup_key}&deleted=1", status_code=303)


@app.post("/project-utilities/backup")
def project_utilities_backup():
    if not can_edit():
        raise HTTPException(status_code=404, detail="Project utilities are not available in archive mode.")
    try:
        path = backup_database()
    except Exception as exc:  # pragma: no cover - surfaced to operator
        token = store_command_result("Backup Database", commands.CommandResult(1, "", str(exc)))
        return RedirectResponse(url=f"/project-utilities?command_result={token}", status_code=303)
    token = uuid4().hex
    BACKUP_DOWNLOADS[token] = {
        "token": token,
        "path": str(path),
        "filename": path.name,
        "size": path.stat().st_size,
    }
    return RedirectResponse(url=f"/project-utilities?backup={token}", status_code=303)


@app.get("/project-utilities/backups/{token}")
def project_utilities_backup_download(token: str):
    if not can_edit():
        raise HTTPException(status_code=404, detail="Project utilities are not available in archive mode.")
    backup = BACKUP_DOWNLOADS.get(token)
    if not backup:
        raise HTTPException(status_code=404, detail="Backup file not found.")
    path = reviews.REPO_ROOT / "backups" / backup["filename"]
    if not path.exists() or str(path) != backup["path"]:
        raise HTTPException(status_code=404, detail="Backup file not found.")
    return FileResponse(path, media_type="application/sql", filename=backup["filename"])


@app.post("/project-utilities/smoke-test")
def project_utilities_smoke_test():
    if not can_edit():
        raise HTTPException(status_code=404, detail="Project utilities are not available in archive mode.")
    result = commands.run_smoke_test(os.getenv("FARRLIND_SMOKE_BASE_URL", "http://127.0.0.1:8000"))
    token = store_command_result("Run Smoke Test", result)
    return RedirectResponse(url=f"/project-utilities?command_result={token}", status_code=303)


@app.post("/project-utilities/export-static-archive")
def project_utilities_export_static_archive():
    if not can_edit():
        raise HTTPException(status_code=404, detail="Project utilities are not available in archive mode.")
    result = commands.run_static_export(os.getenv("FARRLIND_STATIC_EXPORT_BASE_URL", "http://web_archive:8000"))
    token = store_command_result("Export Static Archive", result)
    return RedirectResponse(url=f"/project-utilities?command_result={token}", status_code=303)


@app.post("/project-utilities/publish-static-archive")
def project_utilities_publish_static_archive():
    if not can_edit():
        raise HTTPException(status_code=404, detail="Project utilities are not available in archive mode.")
    result = commands.publish_static_archive(
        base_url=os.getenv("FARRLIND_STATIC_EXPORT_BASE_URL", "http://web_archive:8000"),
        static_repo=os.getenv("CAMPAIGN_STATIC_REPO_PATH") or os.getenv("FARRLIND_STATIC_REPO_PATH", ""),
        push=os.getenv("FARRLIND_STATIC_PUBLISH_PUSH", "").strip().lower() in {"1", "true", "yes", "on"},
    )
    token = store_command_result("Publish Static Archive", result)
    return RedirectResponse(url=f"/project-utilities?command_result={token}", status_code=303)


def songbook_template_context(editing: Optional[dict] = None, show_modal: bool = False) -> dict:
    songs = canon.songbook_rows()
    foreword = canon.songbook_foreword()
    drive_manifest = songbook_drive.drive_manifest() if can_edit() and show_modal else {"lyrics": [], "audio": []}
    lyrics_options = drive_manifest.get("lyrics") or []
    audio_options = drive_manifest.get("audio") or []
    current_lyrics_option = songbook_drive.current_file_option(editing.get("lyrics_url") if editing else "", lyrics_options)
    current_audio_option = songbook_drive.current_file_option(editing.get("mp3_url") if editing else "", audio_options)
    return {
        "songs": songs,
        "foreword": foreword,
        "foreword_html": reviews.render_markdown(foreword.get("text", "")),
        "editing": editing,
        "show_song_modal": show_modal,
        "song_styles": canon.song_styles() if can_edit() and show_modal else [],
        "song_categories": canon.song_categories() if can_edit() and show_modal else [],
        "next_song_number": canon.next_song_number() if can_edit() and show_modal else None,
        "next_order_number": canon.next_song_order_number() if can_edit() and show_modal else None,
        "drive_manifest": drive_manifest,
        "lyrics_drive_options": ([current_lyrics_option] if current_lyrics_option else []) + lyrics_options,
        "audio_drive_options": ([current_audio_option] if current_audio_option else []) + audio_options,
    }


@app.get("/songbook", response_class=HTMLResponse)
def songbook_index(request: Request, modal: str = ""):
    if not songbook_enabled():
        raise HTTPException(status_code=404, detail="Songbook is not enabled for this campaign.")
    try:
        context = songbook_template_context(show_modal=can_edit() and modal == "add")
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return templates.TemplateResponse(
        request,
        "songbook.html",
        context,
    )


@app.post("/songbook")
async def create_songbook_entry(request: Request):
    if not songbook_enabled():
        raise HTTPException(status_code=404, detail="Songbook is not enabled for this campaign.")
    form = await request.form()
    values = song_form_values(form)
    try:
        canon.create_song(values)
    except canon.CanonWriteError:
        return RedirectResponse(url="/songbook?modal=add&create_failed=1", status_code=303)
    return RedirectResponse(url="/songbook?created=1", status_code=303)


@app.get("/songbook/{song_number}/edit", response_class=HTMLResponse)
def edit_songbook_entry(request: Request, song_number: int):
    if not songbook_enabled():
        raise HTTPException(status_code=404, detail="Songbook is not enabled for this campaign.")
    if not can_edit():
        raise HTTPException(status_code=404, detail="Songbook editing is not available in archive mode.")
    try:
        editing = canon.songbook_detail(song_number)
        if not editing:
            raise HTTPException(status_code=404, detail="Song not found.")
        context = songbook_template_context(editing=editing, show_modal=True)
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return templates.TemplateResponse(request, "songbook.html", context)


@app.post("/songbook/{song_number}")
async def update_songbook_entry(request: Request, song_number: int):
    if not songbook_enabled():
        raise HTTPException(status_code=404, detail="Songbook is not enabled for this campaign.")
    form = await request.form()
    current = canon.songbook_detail(song_number)
    if not current:
        raise HTTPException(status_code=404, detail="Song not found.")
    try:
        canon.update_song(song_number, song_form_values(form, current=current))
    except canon.CanonWriteError:
        return RedirectResponse(url=f"/songbook/{song_number}/edit?update_failed=1", status_code=303)
    return RedirectResponse(url="/songbook?updated=1", status_code=303)


@app.post("/songbook/{song_number}/delete")
async def delete_songbook_entry(song_number: int):
    if not songbook_enabled():
        raise HTTPException(status_code=404, detail="Songbook is not enabled for this campaign.")
    try:
        canon.delete_song(song_number)
    except canon.CanonWriteError:
        return RedirectResponse(url="/songbook?delete_failed=1", status_code=303)
    return RedirectResponse(url="/songbook?deleted=1", status_code=303)


@app.post("/songbook/{song_number}/move")
async def move_songbook_entry(request: Request, song_number: int):
    if not songbook_enabled():
        raise HTTPException(status_code=404, detail="Songbook is not enabled for this campaign.")
    form = await request.form()
    direction = (form.get("direction") or "").strip()
    if direction not in {"up", "down"}:
        return RedirectResponse(url="/songbook?reorder_failed=1", status_code=303)
    try:
        canon.move_song(song_number, direction)
    except canon.CanonWriteError:
        return RedirectResponse(url="/songbook?reorder_failed=1", status_code=303)
    return RedirectResponse(url="/songbook?reordered=1", status_code=303)


@app.get("/songbook/{song_number}/lyrics", response_class=HTMLResponse)
def songbook_lyrics(request: Request, song_number: int):
    if not songbook_enabled():
        raise HTTPException(status_code=404, detail="Songbook is not enabled for this campaign.")
    try:
        song = canon.songbook_detail(song_number)
        lyrics_text = canon.songbook_lyrics(song_number)
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if not song or lyrics_text is None:
        raise HTTPException(status_code=404, detail="Song lyrics not found.")
    return templates.TemplateResponse(
        request,
        "song_lyrics.html",
        {
            "song": song,
            "lyrics_text": lyrics_text,
        },
    )


@app.get("/songbook/{song_number}/audio")
def songbook_audio(song_number: int):
    if not songbook_enabled():
        raise HTTPException(status_code=404, detail="Songbook is not enabled for this campaign.")
    try:
        path = canon.songbook_asset_path(song_number, "audio")
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if path is None:
        raise HTTPException(status_code=404, detail="Song audio not found.")
    return FileResponse(path, media_type="audio/mpeg")


@app.get("/api/review-status")
def api_review_status():
    return [row.__dict__ for row in reviews.dashboard_rows()]


@app.get("/api/workflow")
def api_workflow():
    if not can_edit():
        raise HTTPException(status_code=404, detail="Workflow status is not available in archive mode.")
    try:
        return workflow.workflow_rows()
    except workflow.WorkflowReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/api/workflow/sessions/{session}")
def api_workflow_session(session: str):
    if not can_edit():
        raise HTTPException(status_code=404, detail="Workflow status is not available in archive mode.")
    try:
        session_number = reviews.parse_session_ref(session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    try:
        detail = workflow.workflow_detail(session_number)
    except workflow.WorkflowReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if detail is None:
        raise HTTPException(status_code=404, detail="Workflow state not found.")
    return detail


@app.get("/api/sessions/{session}/review")
def api_session_review(session: str, source: str = "diary", view: str = "raw"):
    try:
        session_number = reviews.parse_session_ref(session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    workspace = reviews.session_workspace(session_number, source, view)
    workspace["summary"] = workspace["summary"].__dict__
    return workspace


@app.get("/api/sessions/{session}/source", response_class=PlainTextResponse)
def api_session_source(session: str, source: str = "diary"):
    try:
        session_number = reviews.parse_session_ref(session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    _label, text = reviews.source_text(session_number, source)
    return text


@app.get("/api/locations")
def api_locations():
    try:
        return canon.locations()
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/api/npcs")
def api_npcs():
    try:
        return canon.npc_rows()
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/api/artifacts")
def api_artifacts():
    try:
        return canon.artifact_rows()
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/api/lore-items")
def api_lore_items():
    try:
        return canon.lore_item_rows()
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/api/combat-encounters")
def api_combat_encounters():
    try:
        return canon.combat_encounter_rows()
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/api/timeline")
def api_timeline():
    try:
        return canon.campaign_timeline()
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/api/songbook")
def api_songbook():
    if not songbook_enabled():
        raise HTTPException(status_code=404, detail="Songbook is not enabled for this campaign.")
    try:
        return canon.songbook_rows()
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/api/event-types")
def api_event_types():
    try:
        loaded = canon.event_types()
    except canon.CanonReadError:
        loaded = []
    return loaded or reviews.EVENT_TYPES
