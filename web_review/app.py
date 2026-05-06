from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from web_review.services import canon, commands, reviews


app = FastAPI(title="Farrlind Review Workbench")
app.mount("/static", StaticFiles(directory=str(reviews.REPO_ROOT / "web_review" / "static")), name="static")
templates = Jinja2Templates(directory=str(reviews.REPO_ROOT / "web_review" / "templates"))


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
    try:
        workspace["locations"] = canon.locations()
    except canon.CanonReadError:
        workspace["locations"] = []
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
    updated = reviews.update_review_document_from_form(document, form_values)
    try:
        reviews.save_review_document(session_number, updated)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    source = form.get("source") or "diary"
    view = form.get("view") or "raw"
    return RedirectResponse(
        url=f"/sessions/{reviews.session_key(session_number)}/review?source={source}&view={view}&saved=1",
        status_code=303,
    )


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
    return RedirectResponse(
        url=f"/sessions/{reviews.session_key(session_number)}/review?source={source}&view={view}&reopened=1",
        status_code=303,
    )


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
    return RedirectResponse(
        url=f"/sessions/{reviews.session_key(session_number)}/review?source={source}&view={view}&{flag}",
        status_code=303,
    )


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
    return RedirectResponse(
        url=f"/sessions/{reviews.session_key(session_number)}/review?source={source}&view={view}&{flag}",
        status_code=303,
    )


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
    updated = reviews.update_review_document_from_form(document, form_values)
    marked, errors = reviews.mark_reviewed_document(updated)
    try:
        reviews.save_review_document(session_number, marked)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    source = form.get("source") or "diary"
    view = form.get("view") or "raw"
    flag = "marked=1" if not errors else "mark_failed=1"
    return RedirectResponse(
        url=f"/sessions/{reviews.session_key(session_number)}/review?source={source}&view={view}&{flag}",
        status_code=303,
    )


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
    return RedirectResponse(
        url=f"/sessions/{reviews.session_key(session_number)}/review?source={source}&view={view}&{flag}",
        status_code=303,
    )


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
    return RedirectResponse(
        url=f"/sessions/{reviews.session_key(session_number)}/review?source={source}&view={view}&{flag}",
        status_code=303,
    )


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
