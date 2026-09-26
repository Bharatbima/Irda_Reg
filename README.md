# IRDAI Consultation Analysis — Internal Tool
**Bharat Bima Insurance Broking** · Submission deadline: 25 October 2026

Internal web app for querying the IRDAI draft consultation paper
*"Recalibrating Economics of Insurance Distribution"* and drafting the team's
submission answers collaboratively.

---

## Three sections (all behind login)

| Section | Purpose |
|---|---|
| **Ask the Documents** | Chat interface — answers from the paper + data PDF only, every claim cited |
| **Our Analysis** | Read-only rendered view of internal analysis markdown files |
| **Submission List** | Append-only answer drafts for the 32 consultation questions |

---

## Environment variables

Set these in your `.env` (local) or Railway service variables (production).

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Your Anthropic API key |
| `SESSION_SECRET` | Yes | Random 32+ char string for signing session cookies |
| `USER_CODES` | Yes | JSON string mapping 6-digit codes to emails: `{"123456":"a@b.co","234567":"c@d.co"}` |
| `DATA_DIR` | No | Directory for `submissions.json`. Default `data/`. On Railway set to your volume mount path (e.g. `/data`) |
| `DEBUG` | No | Set `true` locally to allow non-HTTPS cookies. Default `false` |

Generate a session secret:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Running locally

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy and fill in environment variables
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY, SESSION_SECRET, USER_CODES at minimum

# 3. Place source PDFs
# source_docs/paper.pdf   — main consultation paper
# source_docs/data.pdf    — supporting data paper
# (Already done if you cloned with the files in place)

# 4. Extract PDF text (run once; re-run if PDFs change)
python extract.py

# 5. Place analysis markdown files
# Drop your .md files into analysis/
# They are rendered read-only at /analysis

# 6. Fill in questions
# Edit questions/questions.json — replace placeholder entries with the
# actual 32 IRDAI consultation question texts

# 7. Start the server
uvicorn main:app --reload --port 8000
# Open http://localhost:8000
```

---

## Deploying to Railway

1. **Create a new Railway project** and link this repository.

2. **Add environment variables** in Railway → Settings → Variables:
   - `ANTHROPIC_API_KEY`
   - `SESSION_SECRET`
   - `USER_CODES`
   - `DATA_DIR` → set to `/data`

3. **Add a persistent volume**:
   - Railway → your service → Volumes → Add Volume
   - Mount path: `/data`
   - This is where `submissions.json` lives; it survives redeploys.

4. **Run the extraction step** — either:
   - SSH into the Railway shell and run `python extract.py`, OR
   - Add a build command in `railway.toml`:
     ```toml
     [build]
     buildCommand = "pip install -r requirements.txt && python extract.py"
     ```
   Note: extraction requires the PDFs to be present. If they are committed
   (not recommended for large files), this works automatically. Otherwise
   extract locally and commit the `extracted/` JSON files instead.

5. **Place analysis documents**: commit your `.md` files to `analysis/` and push.

6. Railway will build and deploy automatically on each push.

---

## File layout

```
source_docs/          PDFs — paper.pdf and data.pdf
analysis/             Team analysis .md files (read-only in app)
extracted/            Generated JSON from extract.py (gitignored)
questions/
  questions.json      32 IRDAI consultation questions
data/                 Railway volume (gitignored) — holds submissions.json
templates/            Jinja2 HTML templates
static/style.css      App stylesheet
extract.py            PDF extraction script (run once)
main.py               FastAPI server
requirements.txt
railway.toml
```

---

## Security notes

- All routes except `/login` require a valid session cookie (httpOnly, SameSite=Lax).
- Login is rate-limited: 5 failures per IP or per code within 15 minutes triggers a lockout.
- The Anthropic API key is never sent to the browser.
- Sessions expire after 7 days.
- Submission entries are append-only and author-attributed; they cannot be deleted.
