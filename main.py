"""
IRDA Regulations Impact Analysis — internal web app
Bharat Bima Insurance Broking, 2026
"""

import json
import os
import re
import tempfile
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Optional

import markdown as md_lib
from anthropic import Anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_required = ["SESSION_SECRET", "ANTHROPIC_API_KEY", "USER_CODES"]
for _k in _required:
    if not os.environ.get(_k):
        raise RuntimeError(f"Required environment variable {_k} is not set")

SESSION_SECRET: str = os.environ["SESSION_SECRET"]
ANTHROPIC_API_KEY: str = os.environ["ANTHROPIC_API_KEY"]
USER_CODES: dict[str, str] = json.loads(os.environ["USER_CODES"])
DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
DEBUG: bool = os.environ.get("DEBUG", "false").lower() == "true"

SESSION_MAX_AGE = 7 * 24 * 3600  # 7 days

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI()
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    max_age=SESSION_MAX_AGE,
    https_only=not DEBUG,
    same_site="lax",
)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ---------------------------------------------------------------------------
# Rate limiting (in-memory; resets on server restart — acceptable per spec)
# ---------------------------------------------------------------------------

LOCKOUT_THRESHOLD = 5
LOCKOUT_WINDOW = 15 * 60  # 15 minutes

_attempts_ip: dict = defaultdict(lambda: {"count": 0, "window_start": 0.0})
_attempts_code: dict = defaultdict(lambda: {"count": 0, "window_start": 0.0})
_attempts_lock = Lock()


def _refresh_window(tracker: dict, now: float) -> None:
    if now - tracker["window_start"] > LOCKOUT_WINDOW:
        tracker["count"] = 0
        tracker["window_start"] = now


def is_locked_out(ip: str, code: str) -> bool:
    now = time.time()
    with _attempts_lock:
        for tracker in (_attempts_ip[ip], _attempts_code[code]):
            _refresh_window(tracker, now)
            if tracker["count"] >= LOCKOUT_THRESHOLD:
                return True
    return False


def record_failed(ip: str, code: str) -> None:
    now = time.time()
    with _attempts_lock:
        for tracker in (_attempts_ip[ip], _attempts_code[code]):
            _refresh_window(tracker, now)
            tracker["count"] += 1


def reset_attempts(ip: str, code: str) -> None:
    with _attempts_lock:
        _attempts_ip[ip] = {"count": 0, "window_start": 0.0}
        _attempts_code[code] = {"count": 0, "window_start": 0.0}


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def get_session_user(request: Request) -> Optional[str]:
    email = request.session.get("email")
    created_at = request.session.get("created_at", 0)
    if not email:
        return None
    if time.time() - created_at > SESSION_MAX_AGE:
        request.session.clear()
        return None
    return email


def require_user_html(request: Request):
    """Return email or RedirectResponse to login."""
    user = get_session_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return user


def require_user_api(request: Request):
    """Return email or JSONResponse 401."""
    user = get_session_user(request)
    if user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return user


# ---------------------------------------------------------------------------
# Extracted text — loaded once at startup
# ---------------------------------------------------------------------------

def _load_extracted() -> tuple[str, list[str], Optional[str]]:
    """Return (full_context_text, all_markers, extraction_date)."""
    parts: list[str] = []
    all_markers: list[str] = []
    extraction_date: Optional[str] = None

    for name in ("paper", "data"):
        path = Path(f"extracted/{name}.json")
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        label = "MAIN CONSULTATION PAPER" if name == "paper" else "SUPPORTING DATA PAPER"
        parts.append(f"=== {label} ===\n{data['full_text']}")
        all_markers.extend(data.get("markers", []))
        if extraction_date is None:
            extraction_date = data.get("extracted_at")

    return "\n\n".join(parts), all_markers, extraction_date


EXTRACTED_TEXT, KNOWN_MARKERS, EXTRACTION_DATE = _load_extracted()

_SYSTEM_PROMPT_BASE = (
    "You are a precise regulatory document assistant for Bharat Bima Insurance Broking. "
    "Your role is to answer questions ONLY from the IRDAI source documents provided below — "
    "the consultation paper 'Recalibrating Economics of Insurance Distribution' "
    "(main paper + supporting data paper).\n\n"
    "Rules:\n"
    "1. Every factual claim MUST cite the exact marker as it appears in the source text. "
    "Paragraph markers appear as [Para N] (e.g. [Para 45]); cite these as 'Para 45'. "
    "Section headers appear as 'Section N' (e.g. Section 9). "
    "Tables are 'Table N', Graphs are 'Graph N', Boxes are 'Box N'.\n"
    "2. If a question is not covered in the source documents, say explicitly: "
    "'This is not covered in the source documents.'\n"
    "3. Do not infer, speculate, or use outside knowledge.\n"
    "4. Do not fabricate citation markers — only cite markers that literally appear in "
    "the text below.\n\n"
    "Source documents follow:\n\n"
)

SYSTEM_PROMPT: str = _SYSTEM_PROMPT_BASE + EXTRACTED_TEXT

# ---------------------------------------------------------------------------
# Citation validation
# ---------------------------------------------------------------------------

_CITE_RE = re.compile(
    r'\b(?:'
    r'Para(?:graph)?\s+\d+'
    r'|Section\s+\d+(?:\.\d+)*'
    r'|Table\s+\d+'
    r'|Graph\s+\d+'
    r'|Box\s+\d+[A-Z]?'
    r'|Annexure\s+(?:\d+|[IVX]+)'
    r'|Annex\s+(?:\d+|[IVX]+)'
    r')\b',
    re.IGNORECASE,
)


def _norm(m: str) -> str:
    m = m.strip().lower()
    m = re.sub(r'\s+', ' ', m)
    m = re.sub(r'\bparagraph\b', 'para', m)
    m = re.sub(r'\bannex\b(?!ure)', 'annexure', m)
    return m


_KNOWN_NORM: frozenset[str] = frozenset(_norm(x) for x in KNOWN_MARKERS)


def validate_citations(text: str) -> str:
    """Replace unverifiable citation markers with a flagged note."""
    if not _KNOWN_NORM:
        # Extracted text not yet available — pass through unchanged
        return text

    def replacer(m: re.Match) -> str:
        raw = m.group(0)
        if _norm(raw) not in _KNOWN_NORM:
            return f"{raw} [citation not found in source document]"
        return raw

    return _CITE_RE.sub(replacer, text)


# ---------------------------------------------------------------------------
# Anthropic client
# ---------------------------------------------------------------------------

_anthropic = Anthropic(api_key=ANTHROPIC_API_KEY)


async def chat_with_claude(messages: list[dict]) -> str:
    """Call Claude with the cached system prompt, return validated response text."""
    response = _anthropic.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=messages,
    )
    raw = response.content[0].text
    return validate_citations(raw)


# ---------------------------------------------------------------------------
# Submission persistence
# ---------------------------------------------------------------------------

_SUBMISSIONS_FILE = DATA_DIR / "submissions.json"
_sub_lock = Lock()


def _read_submissions() -> dict:
    if not _SUBMISSIONS_FILE.exists():
        return {"entries": []}
    return json.loads(_SUBMISSIONS_FILE.read_text(encoding="utf-8"))


def _write_atomic(data: dict) -> None:
    _SUBMISSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=_SUBMISSIONS_FILE.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _SUBMISSIONS_FILE)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def add_submission_entry(question_num: int, author_email: str, text: str) -> dict:
    entry = {
        "id": str(uuid.uuid4()),
        "question_num": question_num,
        "author_email": author_email,
        "text": text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "is_final": False,
    }
    with _sub_lock:
        data = _read_submissions()
        data["entries"].append(entry)
        _write_atomic(data)
    return entry


def mark_entry_final(entry_id: str) -> bool:
    """Mark entry as final; auto-unmark any previous final for the same question."""
    with _sub_lock:
        data = _read_submissions()
        target = next((e for e in data["entries"] if e["id"] == entry_id), None)
        if target is None:
            return False
        q = target["question_num"]
        for e in data["entries"]:
            if e["question_num"] == q:
                e["is_final"] = e["id"] == entry_id
        _write_atomic(data)
    return True


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------

def load_questions() -> list[dict]:
    path = Path("questions/questions.json")
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    qs = data.get("questions", [])
    return [q for q in qs if not str(q.get("text", "")).startswith("PLACEHOLDER")]


# ---------------------------------------------------------------------------
# Analysis documents
# ---------------------------------------------------------------------------

def load_analysis_docs() -> list[dict]:
    """Return metadata list for all .md files in analysis/."""
    docs = []
    for md_file in sorted(Path("analysis").glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        # Derive title from first # heading or filename
        title_match = re.search(r'^#{1,2}\s+(.+)$', text, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else md_file.stem.replace("_", " ").replace("-", " ").title()
        docs.append({"slug": md_file.stem, "title": title, "filename": md_file.name})
    return docs


def render_analysis_doc(slug: str) -> Optional[str]:
    path = Path("analysis") / f"{slug}.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    return md_lib.markdown(text, extensions=["tables", "fenced_code", "toc"])


# ---------------------------------------------------------------------------
# Routes — Login / Logout
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if get_session_user(request):
        return RedirectResponse("/home", status_code=303)
    return RedirectResponse("/login", status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if get_session_user(request):
        return RedirectResponse("/home", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login", response_class=HTMLResponse)
async def login_post(request: Request, code: str = Form(...)):
    ip = request.client.host if request.client else "unknown"
    code = code.strip()

    if is_locked_out(ip, code):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Too many failed attempts. Please wait 15 minutes and try again."},
            status_code=429,
        )

    email = USER_CODES.get(code)
    if not email:
        record_failed(ip, code)
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid access code. Please try again."},
            status_code=401,
        )

    reset_attempts(ip, code)
    request.session["email"] = email
    request.session["created_at"] = time.time()
    return RedirectResponse("/home", status_code=303)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# ---------------------------------------------------------------------------
# Routes — Home
# ---------------------------------------------------------------------------

@app.get("/home", response_class=HTMLResponse)
async def home(request: Request):
    result = require_user_html(request)
    if isinstance(result, RedirectResponse):
        return result
    user_email = result
    return templates.TemplateResponse(
        "home.html",
        {"request": request, "user_email": user_email, "section": "home"},
    )


# ---------------------------------------------------------------------------
# Routes — Chat
# ---------------------------------------------------------------------------

@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    result = require_user_html(request)
    if isinstance(result, RedirectResponse):
        return result
    user_email = result

    extraction_display = "not yet extracted"
    if EXTRACTION_DATE:
        try:
            dt = datetime.fromisoformat(EXTRACTION_DATE)
            extraction_display = dt.strftime("%-d %b %Y, %H:%M UTC")
        except Exception:
            extraction_display = EXTRACTION_DATE

    docs_ready = bool(EXTRACTED_TEXT)
    return templates.TemplateResponse(
        "chat.html",
        {
            "request": request,
            "user_email": user_email,
            "section": "chat",
            "extraction_date": extraction_display,
            "docs_ready": docs_ready,
        },
    )


@app.post("/api/chat")
async def chat_api(request: Request):
    result = require_user_api(request)
    if isinstance(result, JSONResponse):
        return result

    if not EXTRACTED_TEXT:
        return JSONResponse(
            {"error": "Source documents have not been extracted yet. Run extract.py first."},
            status_code=503,
        )

    body = await request.json()
    messages = body.get("messages", [])
    if not messages or messages[-1].get("role") != "user":
        return JSONResponse({"error": "messages must end with a user turn"}, status_code=400)

    # Limit history to last 20 turns to keep token usage reasonable
    messages = messages[-20:]

    try:
        answer = await chat_with_claude(messages)
    except Exception as exc:
        return JSONResponse({"error": f"AI error: {exc}"}, status_code=502)

    return JSONResponse({"answer": answer})


# ---------------------------------------------------------------------------
# Routes — Analysis
# ---------------------------------------------------------------------------

@app.get("/analysis", response_class=HTMLResponse)
async def analysis_list(request: Request):
    result = require_user_html(request)
    if isinstance(result, RedirectResponse):
        return result
    user_email = result
    docs = load_analysis_docs()
    return templates.TemplateResponse(
        "analysis_list.html",
        {"request": request, "user_email": user_email, "section": "analysis", "docs": docs},
    )


@app.get("/analysis/{slug}", response_class=HTMLResponse)
async def analysis_doc(request: Request, slug: str):
    result = require_user_html(request)
    if isinstance(result, RedirectResponse):
        return result
    user_email = result

    # Sanitise slug to prevent path traversal
    if not re.fullmatch(r'[A-Za-z0-9_\-]+', slug):
        return HTMLResponse("Not found", status_code=404)

    html_content = render_analysis_doc(slug)
    if html_content is None:
        return HTMLResponse("Document not found", status_code=404)

    docs = load_analysis_docs()
    title = next((d["title"] for d in docs if d["slug"] == slug), slug)

    return templates.TemplateResponse(
        "analysis_doc.html",
        {
            "request": request,
            "user_email": user_email,
            "section": "analysis",
            "title": title,
            "content": html_content,
        },
    )


# ---------------------------------------------------------------------------
# Routes — Submission List
# ---------------------------------------------------------------------------

@app.get("/submission", response_class=HTMLResponse)
async def submission_page(request: Request):
    result = require_user_html(request)
    if isinstance(result, RedirectResponse):
        return result
    user_email = result

    questions = load_questions()
    with _sub_lock:
        data = _read_submissions()
    entries = data.get("entries", [])

    # Group entries by question number
    by_q: dict[int, list[dict]] = defaultdict(list)
    for e in entries:
        by_q[e["question_num"]].append(e)

    # Sort entries within each question chronologically
    for q_entries in by_q.values():
        q_entries.sort(key=lambda e: e["timestamp"])

    # Attach display name (first part of email before @)
    for e in entries:
        e["display_name"] = e["author_email"].split("@")[0]

    questions_with_entries = [
        {
            **q,
            "entries": by_q.get(q["num"], []),
            "final_entry": next((e for e in by_q.get(q["num"], []) if e["is_final"]), None),
        }
        for q in questions
    ]

    placeholder_mode = len(questions) == 0
    return templates.TemplateResponse(
        "submission.html",
        {
            "request": request,
            "user_email": user_email,
            "section": "submission",
            "questions": questions_with_entries,
            "placeholder_mode": placeholder_mode,
        },
    )


@app.post("/api/submission/entry")
async def add_entry_api(request: Request):
    result = require_user_api(request)
    if isinstance(result, JSONResponse):
        return result
    user_email = result

    body = await request.json()
    q_num = body.get("question_num")
    text = (body.get("text") or "").strip()

    if not isinstance(q_num, int) or q_num < 1:
        return JSONResponse({"error": "question_num must be a positive integer"}, status_code=400)
    if not text:
        return JSONResponse({"error": "text must not be empty"}, status_code=400)
    if len(text) > 20000:
        return JSONResponse({"error": "text exceeds 20,000 character limit"}, status_code=400)

    entry = add_submission_entry(q_num, user_email, text)
    entry["display_name"] = user_email.split("@")[0]
    return JSONResponse({"entry": entry})


@app.post("/api/submission/entry/{entry_id}/final")
async def mark_final_api(request: Request, entry_id: str):
    result = require_user_api(request)
    if isinstance(result, JSONResponse):
        return result

    if not re.fullmatch(r'[0-9a-f\-]{36}', entry_id):
        return JSONResponse({"error": "invalid entry id"}, status_code=400)

    ok = mark_entry_final(entry_id)
    if not ok:
        return JSONResponse({"error": "entry not found"}, status_code=404)
    return JSONResponse({"ok": True})
