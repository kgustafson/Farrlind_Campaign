import os
from datetime import date
from uuid import uuid4
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from scripts.db_backup import backup_database
from web_review.services import canon, commands, lore, reviews, workflow


app = FastAPI(title="Farrlind Review Workbench")
app.mount("/static", StaticFiles(directory=str(reviews.REPO_ROOT / "web_review" / "static")), name="static")
templates = Jinja2Templates(directory=str(reviews.REPO_ROOT / "web_review" / "templates"))
COMMAND_RESULTS = {}
BACKUP_DOWNLOADS = {}

EDIT_MODE = "edit"
ARCHIVE_MODE = "archive"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


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


templates.env.globals["app_version"] = app_version
templates.env.globals["interface_mode"] = interface_mode
templates.env.globals["can_edit"] = can_edit


@app.middleware("http")
async def archive_mode_write_guard(request: Request, call_next):
    if not can_edit() and request.method.upper() not in SAFE_METHODS:
        return PlainTextResponse("Farrlind Archivum is running in archive mode.", status_code=403)
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
        "notes": (form.get("notes") or "").strip(),
    }


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
        },
    )


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
    known_locations = canon_location_names()
    if location_confirmation_failed(form_values, form, known_locations):
        return redirect_to_review(session_number, form.get("source") or "diary", form.get("view") or "raw", "location_confirm_failed=1", form.get("bucket") or "")
    updated = reviews.update_review_document_from_form(document, form_values)
    try:
        reviews.save_review_document(session_number, updated)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    source = form.get("source") or "diary"
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
    form_values = {key: form.getlist(key) for key in form.keys()}
    known_locations = canon_location_names()
    if location_confirmation_failed(form_values, form, known_locations):
        return redirect_to_review(session_number, form.get("source") or "diary", form.get("view") or "raw", "location_confirm_failed=1", form.get("bucket") or "")
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
    form_values = {key: form.getlist(key) for key in form.keys()}
    known_locations = canon_location_names()
    macro_locations = form_values.get("macro_location", []) + form_values.get("new_macro_location", [])
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
    return redirect_to_review(session_number, form.get("source") or "diary", form.get("view") or "raw", flag, form.get("bucket") or "")


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
    known_locations = canon_location_names()
    if location_confirmation_failed({"new_location": [form.get("merge_location") or ""]}, form, known_locations):
        return redirect_to_review(session_number, form.get("source") or "diary", form.get("view") or "raw", "location_confirm_failed=1")
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
    known_locations = canon_location_names()
    if location_confirmation_failed({"new_location": [form.get("new_location") or ""]}, form, known_locations):
        return redirect_to_review(session_number, form.get("source") or "diary", form.get("view") or "raw", "location_confirm_failed=1")
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
    known_locations = canon_location_names()
    if location_confirmation_failed(form_values, form, known_locations):
        return redirect_to_review(session_number, form.get("source") or "diary", form.get("view") or "raw", "location_confirm_failed=1")
    updated = reviews.update_review_document_from_form(document, form_values)
    marked, errors = reviews.mark_reviewed_document(updated)
    try:
        reviews.save_review_document(session_number, marked)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    source = form.get("source") or "diary"
    view = form.get("view") or "raw"
    flag = "marked=1" if not errors else "mark_failed=1"
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
    result = commands.run_health()
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
def combat_encounters_index(request: Request):
    try:
        rows = canon.combat_encounter_rows()
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return templates.TemplateResponse(
        request,
        "combat_encounters.html",
        {
            "encounters": rows,
            "murder_hobo_count": canon.murder_hobo_count(rows),
        },
    )


@app.get("/timeline", response_class=HTMLResponse)
def timeline_index(request: Request):
    try:
        timeline = canon.campaign_timeline()
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return templates.TemplateResponse(
        request,
        "timeline.html",
        {"timeline": timeline},
    )


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
            workflow.enqueue_auto_intake(session_number)
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


@app.get("/songbook", response_class=HTMLResponse)
def songbook_index(request: Request):
    try:
        songs = canon.songbook_rows()
        foreword = canon.songbook_foreword()
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return templates.TemplateResponse(
        request,
        "songbook.html",
        {"songs": songs, "foreword": foreword, "foreword_html": reviews.render_markdown(foreword.get("text", ""))},
    )


@app.get("/songbook/{song_number}/lyrics", response_class=HTMLResponse)
def songbook_lyrics(request: Request, song_number: int):
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
    try:
        path = canon.songbook_asset_path(song_number, "audio")
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if path is None:
        raise HTTPException(status_code=404, detail="Song audio not found.")
    return FileResponse(path, media_type="audio/mpeg")


@app.get("/wells", response_class=HTMLResponse)
def wells_lore(request: Request):
    lore_text = lore.read_wells_of_magic()
    return templates.TemplateResponse(
        request,
        "wells.html",
        {"lore_text": lore_text, "lore_html": reviews.render_markdown(lore_text)},
    )


@app.post("/wells")
async def save_wells_lore(request: Request):
    form = await request.form()
    try:
        lore.write_wells_of_magic(form.get("lore_text") or "")
    except OSError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return RedirectResponse(url="/wells?saved=1", status_code=303)


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
