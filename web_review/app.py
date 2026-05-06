from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from web_review.services import canon, commands, reviews


app = FastAPI(title="Farrlind Review Workbench")
app.mount("/static", StaticFiles(directory=str(reviews.REPO_ROOT / "web_review" / "static")), name="static")
templates = Jinja2Templates(directory=str(reviews.REPO_ROOT / "web_review" / "templates"))
COMMAND_RESULTS = {}


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


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"rows": reviews.dashboard_rows()},
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


@app.get("/api/review-status")
def api_review_status():
    return [row.__dict__ for row in reviews.dashboard_rows()]


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


@app.get("/api/event-types")
def api_event_types():
    try:
        loaded = canon.event_types()
    except canon.CanonReadError:
        loaded = []
    return loaded or reviews.EVENT_TYPES
