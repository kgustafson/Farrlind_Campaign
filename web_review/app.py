from uuid import uuid4
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from web_review.services import canon, commands, lore, reviews, workflow


app = FastAPI(title="Farrlind Review Workbench")
app.mount("/static", StaticFiles(directory=str(reviews.REPO_ROOT / "web_review" / "static")), name="static")
templates = Jinja2Templates(directory=str(reviews.REPO_ROOT / "web_review" / "templates"))
COMMAND_RESULTS = {}


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


def redirect_to_review(session_number: int, source: str, view: str, flag: str) -> RedirectResponse:
    return RedirectResponse(
        url=f"/sessions/{reviews.session_key(session_number)}/review?source={source}&view={view}&{flag}",
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


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"rows": reviews.dashboard_rows()},
    )


@app.get("/workflow", response_class=HTMLResponse)
def workflow_index(request: Request, session: Optional[int] = None):
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
def session_review(request: Request, session: str, source: str = "diary", view: str = "raw"):
    try:
        session_number = reviews.parse_session_ref(session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    workspace = reviews.session_workspace(session_number, source, view)
    workspace["locations"] = canon_location_names()
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
        return redirect_to_review(session_number, form.get("source") or "diary", form.get("view") or "raw", "location_confirm_failed=1")
    updated = reviews.update_review_document_from_form(document, form_values)
    try:
        reviews.save_review_document(session_number, updated)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    source = form.get("source") or "diary"
    view = form.get("view") or "raw"
    return redirect_to_review(session_number, source, view, "saved=1")


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
            "show_location_modal": modal == "add",
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
            "show_npc_modal": modal == "add",
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
            "show_artifact_modal": modal == "add",
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


@app.get("/combat-encounters", response_class=HTMLResponse)
def combat_encounters_index(request: Request):
    try:
        rows = canon.combat_encounter_rows()
    except canon.CanonReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return templates.TemplateResponse(
        request,
        "combat_encounters.html",
        {"encounters": rows},
    )


@app.get("/wells", response_class=HTMLResponse)
def wells_lore(request: Request):
    return templates.TemplateResponse(
        request,
        "wells.html",
        {"lore_text": lore.read_wells_of_magic()},
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
    try:
        return workflow.workflow_rows()
    except workflow.WorkflowReadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/api/workflow/sessions/{session}")
def api_workflow_session(session: str):
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


@app.get("/api/event-types")
def api_event_types():
    try:
        loaded = canon.event_types()
    except canon.CanonReadError:
        loaded = []
    return loaded or reviews.EVENT_TYPES
