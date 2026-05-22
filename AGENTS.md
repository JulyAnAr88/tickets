# AGENTS.md — Sistema de Gestión de Tickets CEDIR

## Stack
- Flask + SQLAlchemy (PostgreSQL), schema `cedir`
- Supabase self-hosted (`192.168.37.182:8000`) for auth
- Google Gemini AI for ticket OCR/extraction
- Bootstrap 5 + vanilla JS frontend
- JWT guest tokens for embedded Superset dashboards

## Commands

```bash
python3 app.py              # dev server on :5151
gunicorn app:app -b 0.0.0.0:5151  # production (Dockerfile)
python3 -m py_compile app.py  # syntax check only (no lint/typecheck configured)
```

No test framework — tests are standalone scripts:
```bash
python3 test_flujo_seleccion.py
python3 test_darkmode.py
```

## Setup requirements
- `.env` required (not committed): DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD, SECRET_KEY, SUPABASE_URL/KEY/JWT_SECRET, GEMINI_API_KEY, UPLOAD_FOLDER, PROCESSED_FOLDER
- PostgreSQL must have `pg_trgm` extension for name similarity search
- `poppler-utils` system package needed for PDF processing (pdf2image)
- Upload folder defaults to `/home/files/incoming/`, processed to `/home/files/processed/`

## Architecture key points
- Ticket processing flow: upload → Gemini AI extraction → auto-match via DNI (priority) or name → session-based pending tickets for manual selection → DB insert on confirm
- `tickets_pendientes` live in Flask session (keyed by `index`, NOT DB id)
- Patient lookup by DNI is numeric (`ABS(nro_doc - :dni) < 1000`), not string exact
- All protected routes use `@supabase_helper.login_required` decorator
- `/seleccionar_paciente` receives `ticket_id` (which is the **index** in session list, not DB primary key)
- Gemini prompt files live in `prompts/` with config in `prompts/config.json`

## Conventions
- SQL uses parameterized `:param` syntax (no f-strings for user input) — `text("...")` from SQLAlchemy
- JS uses `escapeHtml()` for XSS prevention on all dynamic content
- Amounts parsed in Argentine format (`.` thousand sep, `,` decimal) then normalized to float
- Dates extracted as DD/MM/YYYY, normalized to YYYY-MM-DD
- Multi-page PDFs processed page-by-page; each page is one ticket
- File uploads timestamped + `secure_filename()` before save

## Files that matter
- `app.py` — all routes (~870 lines, single file)
- `ticket_processor.py` — Gemini extraction + SQL generation + orchestration
- `protocolo_manager.py` — all DB queries (patients, protocols, candidates)
- `prompt_manager.py` — prompt loading from `prompts/` directory
- `supabase_helper.py` — auth, session, `@login_required` decorator
- `models.py` — SQLAlchemy `Ticket` model for `cedir.ticket`
- `templates/abm.html` — main page with modal for patient selection
- `static/js/pacientes.js` — AJAX logic for match/search/insert

## Known quirks
- No typechecking, no linter, no CI — verify manually
- Heavy inline debug logging throughout (`logger.info`, `logger.debug`)
- Avatar upload requires Supabase storage bucket named `avatars`
- Processed files only moved after auto-insert (not when pending remain)
