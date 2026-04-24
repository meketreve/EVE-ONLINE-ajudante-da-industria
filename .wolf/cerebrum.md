# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-04-21

## User Preferences

<!-- How the user likes things done. Code style, tools, patterns, communication. -->

## Key Learnings

- **Project:** EVE ONLINE - ajudante da industria
- **Description:** Aplicação desktop local para industrialistas do EVE Online calcularem custos de produção, margens de lucro e oportunidades de importação. Integra EVE SSO (OAuth2) e ESI API.
- **Stack:** Python, FastAPI, SQLAlchemy async, HTTPX, Jinja2+HTMX, SQLite (WAL), aiosqlite. NiceGUI migration in progress (see commit ca75d33).
- **Data sources:** ESI (live, cached in SQLite) + SDE via EVERef/Fuzzwork (`scripts/import_sde.py`).
- **DB migrations:** embedded in `database.py → create_tables()` as `ALTER TABLE` blocks. No Alembic.
- **Job runner:** in-memory async queue, discovery (3 workers) + crawl (2 workers). Scheduler in `main.py` lifespan.
- **Cache TTLs:** region market 5min, structure market 4h, skills 1h, structure info 24h.

## Do-Not-Repeat

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->