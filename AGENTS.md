# AGENTS.md — Sistema de Gestión de Tickets CEDIR

## Stack
- Flask + SQLAlchemy (PostgreSQL), schema `cedir`
- Supabase self-hosted (`192.168.37.182:8000`) for auth
- Google Gemini AI for ticket OCR/extraction
- Bootstrap 5 + vanilla JS frontend
- JWT guest tokens for embedded Superset dashboards
- **Celery + Redis** for async ticket processing

## Commands

```bash
python3 app.py                    # dev server on :5151
gunicorn app:app -b 0.0.0.0:5151 # production (Dockerfile)
python3 -m py_compile app.py      # syntax check only

# Celery worker (must be running for uploads to work)
celery -A celery_app worker -l info --concurrency=1

# systemd services
sudo systemctl start gestion-tickets.service   # gunicorn web
sudo systemctl start celery-worker.service     # celery worker
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
- **Redis** required for Celery broker (runs on localhost:6379)

## Architecture key points
- Ticket processing flow: upload → Celery task queued → Gemini AI extraction → auto-match via DNI (priority) or name → session-based pending tickets for manual selection → DB insert on confirm
- File uploads are NOT processed synchronously — a Celery task is dispatched, the POST returns immediately, and the frontend polls `/task_status/<task_id>` every 2s until completion
- `tickets_pendientes` live in Flask session (keyed by `index`, NOT DB id)
- Patient lookup by DNI is numeric (`ABS(nro_doc - :dni) < 1000`), not string exact
- All protected routes use `@supabase_helper.login_required` decorator
- `/seleccionar_paciente` receives `ticket_id` (which is the **index** in session list, not DB primary key)
- Gemini prompt files live in `prompts/` with config in `prompts/config.json`

## Async processing (Celery)
- **Broker/Backend**: Redis on localhost:6379
- **Worker concurrency**: 1 (avoids race conditions with module-level `_SCHEMA` global)
- **Task**: `tasks.process_tickets` — wraps `TicketProcessor.process_multiple_tickets`
- **Result flow**: task queued → frontend polls `/task_status/<id>` → on SUCCESS calls `/finalize_task/<id>` which stores flash messages and pending tickets in session, then redirects to `/abm`
- **Task files**: `celery_app.py` (config), `tasks.py` (task definition)
- Gunicorn timeout reduced to 60s (requests are now fast, just file save + task enqueue)

## Conventions
- SQL uses parameterized `:param` syntax (no f-strings for user input) — `text("...")` from SQLAlchemy
- JS uses `escapeHtml()` for XSS prevention on all dynamic content
- Amounts parsed in Argentine format (`.` thousand sep, `,` decimal) then normalized to float
- Dates extracted as DD/MM/YYYY, normalized to YYYY-MM-DD
- Multi-page PDFs processed page-by-page; each page is one ticket
- File uploads timestamped + `secure_filename()` before save

## Files that matter
- `app.py` — all routes (~1200 lines, single file)
- `ticket_processor.py` — Gemini extraction + SQL generation + orchestration
- `protocolo_manager.py` — all DB queries (patients, protocols, candidates)
- `prompt_manager.py` — prompt loading from `prompts/` directory
- `supabase_helper.py` — auth, session, `@login_required` decorator
- `models.py` — SQLAlchemy `Ticket` model for `cedir.ticket`
- `celery_app.py` — Celery app with Redis broker/backend
- `tasks.py` — Celery task `process_tickets`
- `templates/abm.html` — main page with modal for patient selection
- `static/js/upload.js` — file upload + task polling logic
- `static/js/pacientes.js` — AJAX logic for match/search/insert
- `celery_worker.service` — systemd unit for the Celery worker

## Known quirks
- No typechecking, no linter, no CI — verify manually
- Heavy inline debug logging throughout (`logger.info`, `logger.debug`)
- Avatar upload requires Supabase storage bucket named `avatars`
- Processed files only moved after auto-insert (not when pending remain)
- Module-level `_SCHEMA` global in `ticket_processor.py` is a race condition if multiple Celery workers run concurrently — keep `--concurrency=1`
