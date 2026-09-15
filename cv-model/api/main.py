"""
FastAPI backend for the HR CV Shortlisting System.

Wraps the cv_ranker model pipeline in HTTP endpoints the React frontend calls.

Run it:
    uvicorn api.main:app --reload --port 8000

Interactive API docs once running: http://localhost:8000/docs
"""

from __future__ import annotations

import datetime as dt
import logging
import shutil
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

from fastapi import (
    BackgroundTasks, Cookie, Depends, FastAPI, File, Form, HTTPException,
    Request, Response, UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cv_ranker.config import settings  # noqa: E402
from cv_ranker.documents import SUPPORTED, read_document  # noqa: E402
from cv_ranker.extract import extract_jd  # noqa: E402
from cv_ranker.pipeline import (  # noqa: E402
    MissingRequirementsError,
    prepare_job,
    run_ranking,
)
from cv_ranker.schema import JobProfile  # noqa: E402

from . import auth, db  # noqa: E402
from .config import auth_settings  # noqa: E402

log = logging.getLogger("api")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

STORAGE = Path(__file__).parent.parent / "storage" / "runs"
STORAGE.mkdir(parents=True, exist_ok=True)

MAX_CVS = 100
MAX_FILE_MB = 15

app = FastAPI(
    title="HR CV Shortlisting API",
    version="0.1.0",
    description=(
        "Decision-support API. It ranks candidates and explains every score; "
        "it never selects or rejects anyone. A human makes the final call."
    ),
)

# The Vite dev server runs on a different port, so the browser needs CORS.
#
# Any localhost port is allowed, not a fixed list: Vite picks the next free
# port (5174, 5175, …) when 5173 is taken, and a hardcoded list silently
# blocked those — the frontend then fell back to demo mode and showed
# simulated candidates for real uploaded CVs, which is far worse than a
# visible error.
#
# Tighten this to the real deployed origin before production.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_pool = ThreadPoolExecutor(max_workers=2)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class RequirementOut(BaseModel):
    mentioned: bool
    quoted_text: Optional[str] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    level: Optional[str] = None
    field_of_study: Optional[str] = None


class JDAnalysisOut(BaseModel):
    job_title: str
    summary: Optional[str] = None
    detected_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    requirements: dict[str, RequirementOut]
    missing_requirements: list[str]
    jd_filename: Optional[str] = None


class ManualOverride(BaseModel):
    text: Optional[str] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    level: Optional[str] = None
    field_of_study: Optional[str] = None


class HealthOut(BaseModel):
    status: str
    llm_provider: str
    llm_model: str
    embed_provider: str
    embed_model: str
    semantic_matching_real: bool
    warnings: list[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _save_upload(dest_dir: Path, upload: UploadFile) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = Path(upload.filename or "unnamed").name  # strip any path components
    target = dest_dir / name
    with target.open("wb") as fh:
        shutil.copyfileobj(upload.file, fh)
    size_mb = target.stat().st_size / (1024 * 1024)
    if size_mb > MAX_FILE_MB:
        target.unlink(missing_ok=True)
        raise HTTPException(413, f"{name} is {size_mb:.1f}MB — limit is {MAX_FILE_MB}MB.")
    return target


def _job_from_run(run: dict[str, Any]) -> JobProfile:
    job = JobProfile.from_dict(run["jd_profile"] or {}, source_file=run.get("jd_filename"))
    job.manual_overrides = run.get("manual_overrides") or {}
    if run.get("required_skills"):
        job.required_skills = run["required_skills"]
    return job


def _analysis_payload(job: JobProfile, filename: str | None) -> JDAnalysisOut:
    reqs = {}
    for key in ("qualification", "experience", "age"):
        raw = job.requirements.get(key) or {}
        reqs[key] = RequirementOut(
            mentioned=bool(raw.get("mentioned")),
            quoted_text=raw.get("quoted_text"),
            min_value=raw.get("min_value"),
            max_value=raw.get("max_value"),
            level=raw.get("level"),
            field_of_study=raw.get("field_of_study"),
        )
    return JDAnalysisOut(
        job_title=job.job_title,
        summary=job.summary,
        detected_skills=job.required_skills,
        preferred_skills=job.preferred_skills,
        requirements=reqs,
        missing_requirements=job.missing_requirements(),
        jd_filename=filename,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.on_event("startup")
def _warm_embedder() -> None:
    """Load the embedding model in the background at startup.

    The first load downloads the model (~90MB) and can take a minute. Doing it
    here means /api/health stays fast and the first real ranking isn't slow.
    """
    def _load() -> None:
        try:
            from cv_ranker.embeddings import get_embedder

            log.info("Warming embedding model (first run downloads it)…")
            get_embedder()
            log.info("Embedding model ready.")
        except Exception as e:  # noqa: BLE001
            log.warning("Embedding model could not be pre-loaded: %s", e)

    _pool.submit(_load)

    auth.seed_admins()
    for warning in auth_settings.warnings():
        log.warning("AUTH: %s", warning)


@app.get("/api/health", response_model=HealthOut)
def health() -> HealthOut:
    """What the system is actually running — surfaced so nobody has to guess.

    Deliberately cheap: it reports configuration and does NOT force the
    embedding model to load. Loading it here made the very first health check
    take longer than the frontend's timeout, so the UI reported "backend not
    reachable" while the backend was in fact busy starting up correctly.
    """
    warnings: list[str] = []
    real = settings.embed_provider != "hash"
    embed_name = settings.embed_model if real else "hash-trigram (NOT semantic)"

    if not real:
        warnings.append(
            "Semantic matching is NOT active — rankings are structural only. "
            "Set EMBED_PROVIDER=sentence_transformers."
        )
    if settings.llm_provider in ("stub", "fixture"):
        warnings.append(
            f"LLM_PROVIDER={settings.llm_provider} — extraction is replayed, not real. "
            "Set a real provider before trusting any result."
        )

    return HealthOut(
        status="ok",
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model,
        embed_provider=settings.embed_provider,
        embed_model=embed_name,
        semantic_matching_real=real,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Signing in
# ---------------------------------------------------------------------------
#
# Two ways in, one gate. Whether a person proves an email address or a phone
# number, the same allowlist decides whether they get a session — proving an
# address belongs to you is not the same as being allowed to read CVs.


class EmailIn(BaseModel):
    email: str


class CodeIn(BaseModel):
    email: str
    code: str


class PhoneTokenIn(BaseModel):
    """The token Firebase hands the browser once it has checked the SMS code."""

    id_token: str


class UserOut(BaseModel):
    # `must_set_password` used to live here, reported as "this account has no
    # password hash in OUR database, so send them back to choose one".
    #
    # Passwords moved to Firebase. Our database now holds a hash for nobody,
    # so that flag was true for every single user — and the site, obeying it,
    # bounced everyone from the workspace back to the sign-in page, which
    # bounced them forward again because they were signed in. The screen
    # flickered and the dashboard never rendered.
    #
    # It is not set to False; it is gone. A field that answers a question this
    # system no longer asks is a trap for the next person reading the code.
    email: str
    name: str
    role: str


def _user_out(user: dict[str, Any]) -> UserOut:
    return UserOut(email=user["email"], name=user["name"], role=user["role"])


class SignInOut(BaseModel):
    # "signed_in"  -> the session cookie is set, go to the workspace
    # "code_sent"  -> ask for the code that was emailed
    status: str
    user: Optional["UserOut"] = None
    email: Optional[str] = None


class PasswordIn(BaseModel):
    email: str
    password: str


class NewPasswordIn(BaseModel):
    password: str


class SignInOptions(BaseModel):
    email: bool
    phone: bool
    firebase_email: bool
    open_access: bool
    warnings: list[str]


@app.get("/api/auth/options", response_model=SignInOptions)
def auth_options() -> SignInOptions:
    """What the sign-in page should offer.

    Phone is hidden rather than shown-and-broken when Firebase is not
    configured: a button that cannot work reads as a fault in the system.
    """
    return SignInOptions(
        email=True,
        phone=auth_settings.phone_enabled,
        # Same credentials as the phone route: if Firebase can verify a token
        # at all, it can verify one carrying an email — a link or Google.
        firebase_email=auth_settings.phone_enabled,
        open_access=auth_settings.open_access,
        warnings=auth_settings.warnings(),
    )


@app.post("/api/auth/signin", response_model=SignInOut)
def auth_signin(body: PasswordIn, response: Response) -> SignInOut:
    """The one sign-in screen: an address and a password.

    The allowlist is checked first, so an address nobody authorised is turned
    away before a code is created or an email is sent. After that the account
    decides what happens — a returning person is signed in, and a first-time
    one is emailed a code, with the password they just typed held until that
    code comes back.
    """
    try:
        outcome = auth.begin_sign_in(body.email, body.password)
    except auth.NotAuthorised as e:
        raise HTTPException(403, str(e)) from e
    except auth.AccountLocked as e:
        raise HTTPException(423, str(e)) from e
    except auth.BadPassword as e:
        raise HTTPException(400, str(e)) from e
    except auth.WeakPassword as e:
        raise HTTPException(400, str(e)) from e
    except auth.TooSoon as e:
        raise HTTPException(429, str(e)) from e
    except auth.MailError as e:
        log.error("Could not send sign-in code: %s", e)
        raise HTTPException(502, "The code could not be emailed. Try again shortly.") from e

    if outcome["status"] == "signed_in":
        auth.start_session(outcome["user"], response)
        return SignInOut(status="signed_in", user=_user_out(outcome["user"]))
    return SignInOut(status="code_sent", email=outcome["email"])


@app.post("/api/auth/reset", response_model=SignInOut)
def auth_reset(body: PasswordIn) -> SignInOut:
    """Forgotten password: choose a new one, then prove the address by code."""
    try:
        outcome = auth.begin_reset(body.email, body.password)
    except auth.NotAuthorised as e:
        raise HTTPException(403, str(e)) from e
    except auth.WeakPassword as e:
        raise HTTPException(400, str(e)) from e
    except auth.TooSoon as e:
        raise HTTPException(429, str(e)) from e
    except auth.MailError as e:
        log.error("Could not send sign-in code: %s", e)
        raise HTTPException(502, "The code could not be emailed. Try again shortly.") from e
    return SignInOut(status="code_sent", email=outcome["email"])


@app.post("/api/auth/password/set", response_model=UserOut)
def auth_set_password(body: NewPasswordIn, response: Response,
                      user: dict[str, Any] = Depends(auth.current_user)) -> UserOut:
    """Choose a password, or replace a forgotten one.

    Requires a session, which is only obtained by receiving the emailed code —
    so proving the address still gates this, and there is no separate reset
    token to secure.
    """
    try:
        auth.set_password(user["email"], body.password)
    except auth.WeakPassword as e:
        raise HTTPException(400, str(e)) from e
    except auth.NotAuthorised as e:
        raise HTTPException(403, str(e)) from e

    # Every session for this person ends, then a fresh one is issued on this
    # response. Changing a password is what somebody does when they think
    # another person has got in, so the old sessions must not survive it — and
    # issuing the replacement here is what stops that logging out the person
    # who just set it.
    db.delete_sessions_for(user["email"])
    updated = db.get_user(user["email"])
    auth.start_session(updated, response)
    return _user_out(updated)


@app.post("/api/auth/email/request")
def auth_request_code(body: EmailIn) -> dict[str, Any]:
    try:
        return auth.request_code(body.email)
    except auth.NotAuthorised as e:
        if auth_settings.reveal_unauthorised:
            raise HTTPException(403, str(e)) from e
        # Same answer either way, so nobody can discover who has access by
        # trying addresses.
        log.info("Sign-in refused for an unlisted address.")
        return {"email": auth.normalise_email(body.email),
                "expires_in_minutes": auth_settings.code_ttl_minutes}
    except auth.TooSoon as e:
        raise HTTPException(429, str(e)) from e
    except auth.MailError as e:
        # The code was created but nobody received it. Saying "sent" here
        # leaves the user waiting for an email that will never arrive.
        log.error("Could not send sign-in code: %s", e)
        raise HTTPException(502, "The code could not be emailed. Try again shortly.") from e


@app.post("/api/auth/email/verify", response_model=UserOut)
def auth_verify_code(body: CodeIn, response: Response) -> UserOut:
    try:
        user = auth.verify_code(body.email, body.code)
    except auth.NotAuthorised as e:
        raise HTTPException(403, str(e)) from e
    except auth.BadCode as e:
        raise HTTPException(400, str(e)) from e

    auth.start_session(user, response)
    return _user_out(user)


@app.post("/api/auth/phone/verify", response_model=UserOut)
def auth_phone_verify(body: PhoneTokenIn, response: Response) -> UserOut:
    """Sign in with a number Firebase has already verified.

    The browser does the SMS round trip with Firebase and arrives here holding
    a signed token. This checks the signature, reads the number out of it, and
    then asks the same question the email route asks: is this person listed?
    A valid token is proof of a phone, never proof of permission.
    """
    try:
        user = auth.sign_in_with_phone(body.id_token)
    except auth.FirebaseUnavailable as e:
        # Nothing the caller can fix — the server has no Firebase credentials.
        log.error("Phone sign-in attempted with no Firebase configured: %s", e)
        raise HTTPException(503, "Phone sign-in is not set up on this server.") from e
    except auth.BadPhoneToken as e:
        raise HTTPException(400, str(e)) from e
    except auth.NotAuthorised as e:
        raise HTTPException(403, str(e)) from e

    auth.start_session(user, response)
    return _user_out(user)


@app.post("/api/auth/firebase/verify", response_model=UserOut)
def auth_firebase_verify(body: PhoneTokenIn, response: Response) -> UserOut:
    """Sign in with an address Firebase has already verified.

    Serves both Firebase email routes — the one-time link and Google — because
    both arrive here holding the same thing: a signed token naming a mailbox
    Firebase has proved. This checks the signature, reads the address out, and
    then asks the question every route asks: is this person listed?

    It exists because our own mail route cannot deliver to an arbitrary address
    on the free tier of the configured provider, and a sign-in that depends on
    an email nobody receives is not a sign-in.
    """
    try:
        user = auth.sign_in_with_firebase_email(body.id_token)
    except auth.FirebaseUnavailable as e:
        log.error("Firebase sign-in attempted with no Firebase configured: %s", e)
        raise HTTPException(503, "Firebase sign-in is not set up on this server.") from e
    except auth.BadEmailToken as e:
        raise HTTPException(400, str(e)) from e
    except auth.NotAuthorised as e:
        raise HTTPException(403, str(e)) from e

    auth.start_session(user, response)
    return _user_out(user)


@app.get("/api/auth/me", response_model=UserOut)
def auth_me(user: dict[str, Any] = Depends(auth.current_user)) -> UserOut:
    return _user_out(user)


@app.post("/api/auth/logout")
def auth_logout(response: Response,
                session: Optional[str] = Cookie(default=None, alias=auth.SESSION_COOKIE)
                ) -> dict[str, str]:
    user = auth.user_for_token(session)
    if user:
        db.log_audit(user["email"], "signed_out")
    auth.end_session(session, response)
    return {"status": "signed out"}


# --- managing who may sign in (administrators only) ------------------------


class NewUserIn(BaseModel):
    email: str
    name: str
    role: str = "hr"
    phone: Optional[str] = None


@app.get("/api/auth/users")
def auth_list_users(admin: dict[str, Any] = Depends(auth.require_admin)) -> dict[str, Any]:
    return {"users": db.list_users()}


@app.post("/api/auth/users")
def auth_add_user(body: NewUserIn,
                  admin: dict[str, Any] = Depends(auth.require_admin)) -> dict[str, Any]:
    email = auth.normalise_email(body.email)
    if "@" not in email:
        raise HTTPException(400, "That does not look like an email address.")
    if body.role not in ("hr", "admin"):
        raise HTTPException(400, "Role must be 'hr' or 'admin'.")

    db.upsert_user(
        email,
        name=body.name.strip() or email.split("@")[0],
        role=body.role,
        phone=auth.normalise_phone(body.phone) if body.phone else None,
        active=True,
        added_by=admin["email"],
    )
    db.log_audit(admin["email"], "user_added", detail=f"{email} as {body.role}")
    return {"user": db.get_user(email)}


@app.post("/api/auth/users/{email}/active")
def auth_set_active(email: str, active: bool,
                    admin: dict[str, Any] = Depends(auth.require_admin)) -> dict[str, Any]:
    email = auth.normalise_email(email)
    if db.get_user(email) is None:
        raise HTTPException(404, "No such user.")
    if email == admin["email"] and not active:
        # Otherwise the last administrator can lock themselves out and nobody
        # is left who can let anyone back in.
        raise HTTPException(400, "You cannot deactivate your own account.")

    db.set_user_active(email, active)
    if not active:
        # An existing session must stop working now, not when it expires.
        db.delete_sessions_for(email)
    db.log_audit(admin["email"], "user_activated" if active else "user_deactivated",
                 detail=email)
    return {"user": db.get_user(email)}


@app.post("/api/jd/analyze", response_model=JDAnalysisOut)
async def analyze_jd(
    jd_file: Optional[UploadFile] = File(None),
    jd_text: Optional[str] = Form(None),
    job_title: Optional[str] = Form(None),
    user: dict[str, Any] = Depends(auth.current_user),
) -> JDAnalysisOut:
    """Run the three-field presence check on a job description.

    A JD is mandatory — this is the rule from the product spec, enforced here
    so it cannot be bypassed by calling the API directly.
    """
    if not jd_file and not (jd_text or "").strip():
        raise HTTPException(400, "A job description is required — upload a file or paste the text.")

    filename = None
    text = jd_text or ""
    if jd_file:
        tmp = STORAGE / "_jd_tmp" / uuid.uuid4().hex
        path = _save_upload(tmp, jd_file)
        filename = path.name
        try:
            text = read_document(path).text
        except Exception as e:  # noqa: BLE001
            raise HTTPException(422, f"Could not read the job description: {e}") from e
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    try:
        job = extract_jd(text=text)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"JD analysis failed: {e}") from e

    if job_title and not job.job_title:
        job.job_title = job_title

    db.log_audit(user["email"], "analyze_jd", detail=job.job_title or filename or "pasted text")
    return _analysis_payload(job, filename)


@app.post("/api/runs")
async def create_run(
    background: BackgroundTasks,
    job_title: str = Form(...),
    jd_text: Optional[str] = Form(None),
    jd_file: Optional[UploadFile] = File(None),
    cvs: list[UploadFile] = File(...),
    required_skills: str = Form("[]"),          # JSON array
    manual_overrides: str = Form("{}"),         # JSON object
    top_n: int = Form(10),
    user: dict[str, Any] = Depends(auth.current_user),
) -> JSONResponse:
    """Start a ranking run. Returns immediately; poll /api/runs/{id} for progress."""
    import json

    if not jd_file and not (jd_text or "").strip():
        raise HTTPException(400, "A job description is required.")
    if not cvs:
        raise HTTPException(400, "At least one CV is required.")
    if len(cvs) > MAX_CVS:
        raise HTTPException(400, f"Batch limit is {MAX_CVS} CVs; {len(cvs)} were sent.")

    try:
        skills = json.loads(required_skills) or []
        manual = json.loads(manual_overrides) or {}
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"Malformed required_skills or manual_overrides: {e}") from e

    run_id = f"run-{uuid.uuid4().hex[:12]}"
    run_dir = STORAGE / run_id
    cv_dir = run_dir / "cvs"

    # Persist uploads before doing anything slow, so a crash mid-run is recoverable.
    text = jd_text or ""
    jd_filename = None
    if jd_file:
        p = _save_upload(run_dir, jd_file)
        jd_filename = p.name
        try:
            text = read_document(p).text
        except Exception as e:  # noqa: BLE001
            shutil.rmtree(run_dir, ignore_errors=True)
            raise HTTPException(422, f"Could not read the job description: {e}") from e

    saved: list[str] = []
    rejected: list[dict[str, str]] = []
    for up in cvs:
        name = Path(up.filename or "unnamed").name
        if Path(name).suffix.lower() not in SUPPORTED:
            rejected.append({"path": name, "reason": f"Unsupported file type {Path(name).suffix}"})
            continue
        try:
            saved.append(str(_save_upload(cv_dir, up)))
        except HTTPException as e:
            rejected.append({"path": name, "reason": str(e.detail)})

    if not saved:
        shutil.rmtree(run_dir, ignore_errors=True)
        raise HTTPException(400, "No valid CV files were uploaded.")

    # Analyse the JD now so the blocking rule is applied before we accept the run.
    try:
        job = prepare_job(jd_text=text, manual_overrides=manual,
                          required_skills=skills or None)
    except Exception as e:  # noqa: BLE001
        shutil.rmtree(run_dir, ignore_errors=True)
        raise HTTPException(502, f"JD analysis failed: {e}") from e

    if job_title:
        job.job_title = job_title

    missing = job.missing_requirements()
    if missing:
        shutil.rmtree(run_dir, ignore_errors=True)
        return JSONResponse(
            status_code=422,
            content={
                "error": "missing_requirements",
                "missing": missing,
                "message": (
                    "Cannot rank: these requirements were not found in the job "
                    "description and were not supplied manually."
                ),
            },
        )

    import json as _json

    db.upsert_run({
        "id": run_id,
        "title": job.job_title or job_title,
        "status": "processing",
        "created_at": _now(),
        "updated_at": _now(),
        "created_by": user["name"] or user["email"],
        "version": 1,
        "top_n": top_n,
        "jd_text": text,
        "jd_filename": jd_filename,
        "jd_profile_json": _json.dumps(
            {
                "job_title": job.job_title,
                "summary": job.summary,
                "responsibilities_text": job.responsibilities_text,
                "required_skills": job.required_skills,
                "preferred_skills": job.preferred_skills,
                "requirements": job.requirements,
            },
            ensure_ascii=False,
        ),
        "manual_json": _json.dumps(manual),
        "skills_json": _json.dumps(job.required_skills),
        "progress_done": 0,
        "progress_total": len(saved),
        "progress_current": None,
        "results_json": None,
        "failures_json": _json.dumps(rejected),
        "versions_json": None,
        "error": None,
    })
    db.log_audit(user["email"], "start_ranking", run_id,
                 f"{job.job_title} — {len(saved)} CVs")

    _pool.submit(_execute_run, run_id, job, saved, rejected, top_n)

    return JSONResponse(status_code=202, content={"run_id": run_id, "status": "processing",
                                                  "total": len(saved), "rejected": rejected})


def _execute_run(run_id: str, job: JobProfile, cv_paths: list[str],
                 rejected: list[dict[str, str]], top_n: int) -> None:
    """Background worker. Never raises — failures are recorded on the run."""
    import json as _json

    def progress(done: int, total: int, path: str) -> None:
        db.update_run(run_id, progress_done=done, progress_total=total,
                      progress_current=Path(path).name, updated_at=_now())

    try:
        result = run_ranking(job, cv_paths, progress=progress)
        failures = rejected + [{"path": Path(f.path).name, "reason": f.reason}
                               for f in result.failures]
        db.update_run(
            run_id,
            status="completed",
            updated_at=_now(),
            progress_done=len(cv_paths),
            progress_total=len(cv_paths),
            results_json=_json.dumps(result.to_dict(), ensure_ascii=False),
            failures_json=_json.dumps(failures, ensure_ascii=False),
            versions_json=_json.dumps(result.versions),
        )
        db.log_audit("system", "ranking_completed", run_id,
                     f"{len(result.scores)} candidates scored "
                     f"(engine {result.versions.get('scoring_engine')})")
    except MissingRequirementsError as e:
        db.update_run(run_id, status="failed", updated_at=_now(),
                      error=f"missing_requirements: {', '.join(e.missing)}")
    except Exception as e:  # noqa: BLE001
        log.exception("Run %s failed", run_id)
        db.update_run(run_id, status="failed", updated_at=_now(), error=str(e))
        db.log_audit("system", "ranking_failed", run_id, str(e))


@app.get("/api/runs")
def list_runs(user: dict[str, Any] = Depends(auth.current_user)) -> dict[str, Any]:
    runs = db.list_runs()
    return {
        "runs": [
            {
                "id": r["id"],
                "title": r["title"],
                "status": r["status"],
                "created_at": r["created_at"],
                "created_by": r["created_by"],
                "version": r["version"],
                "top_n": r["top_n"],
                "candidate_count": len((r.get("results") or {}).get("ranking", [])),
                "required_skills": r["required_skills"],
            }
            for r in runs
        ]
    }


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, top_n: Optional[int] = None,
            user: dict[str, Any] = Depends(auth.current_user)) -> dict[str, Any]:
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")

    payload: dict[str, Any] = {
        "id": run["id"],
        "title": run["title"],
        "status": run["status"],
        "created_at": run["created_at"],
        "created_by": run["created_by"],
        "version": run["version"],
        "top_n": top_n or run["top_n"],
        "required_skills": run["required_skills"],
        "manual_overrides": run["manual_overrides"],
        "progress": {
            "done": run["progress_done"],
            "total": run["progress_total"],
            "current": run["progress_current"],
        },
        "failures": run["failures"],
        "versions": run["versions"],
        "error": run["error"],
    }

    jd = run.get("jd_profile") or {}
    payload["requirements"] = jd.get("requirements", {})
    payload["jd_filename"] = run.get("jd_filename")

    results = run.get("results")
    if results:
        ranking = results.get("ranking", [])
        limit = top_n or run["top_n"]
        payload["results"] = {**results, "ranking": ranking[:limit]}
        payload["total_candidates"] = len(ranking)
    return payload


@app.delete("/api/runs/{run_id}")
def delete_run(run_id: str,
               user: dict[str, Any] = Depends(auth.current_user)) -> dict[str, str]:
    if not db.get_run(run_id):
        raise HTTPException(404, "Run not found")
    db.delete_run(run_id)
    shutil.rmtree(STORAGE / run_id, ignore_errors=True)
    db.log_audit(user["email"], "delete_run", run_id)
    return {"status": "deleted"}


@app.get("/api/audit")
def audit(limit: int = 200,
          user: dict[str, Any] = Depends(auth.require_admin)) -> dict[str, Any]:
    """Append-only audit log — administrators only.

    `total` is returned alongside the page because the page alone is a trap:
    two hundred lines with no count looks exactly like a complete record, and
    this is the one screen in the system where believing you have seen
    everything, when you have not, actually matters.
    """
    limit = max(1, min(limit, 1000))
    return {"entries": db.list_audit(limit), "total": db.count_audit(), "limit": limit}


@app.get("/api")
def api_root() -> dict[str, str]:
    return {
        "service": "HR CV Shortlisting API",
        "docs": "/docs",
        "health": "/api/health",
        "note": "Decision support only — a human makes the final hiring decision.",
    }


# ---------------------------------------------------------------------------
# Serving the website from the same address as the API
# ---------------------------------------------------------------------------
#
# In development the two run separately: Vite on one port, this API on another.
# When deployed there is one address for both, which removes the CORS problem
# and, more importantly, removes the possibility of the site being live while
# the API it depends on is not — the failure that once let simulated candidates
# appear alongside real uploaded CVs.
#
# Mounted last, so every /api/... route above still wins.

FRONTEND_DIST = Path(__file__).parent.parent / "web"

if FRONTEND_DIST.is_dir():
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str) -> FileResponse:
        """Serve the built site, falling back to index.html for client routes."""
        candidate = (FRONTEND_DIST / full_path).resolve()
        # Resolve before comparing: without this, a path like "../../.env" would
        # escape the directory and hand out files that are not part of the site.
        if (
            full_path
            and FRONTEND_DIST.resolve() in candidate.parents
            and candidate.is_file()
        ):
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")

else:
    @app.get("/")
    def root() -> dict[str, str]:
        return api_root()
