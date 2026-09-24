# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-04-21

## User Preferences

<!-- How the user likes things done. Code style, tools, patterns, communication. -->
- NUNCA commitar dados de personagens nem dados sensíveis: database.db (tokens), .env, .secret_key, .nicegui/ (sessão), nomes/IDs de personagens em docs/.wolf, Client Secret. Conferir `git status`/diff antes de qualquer commit.
- Prioriza facilitar o primeiro uso por usuário leigo (Windows, sem conhecimento técnico). Textos de UI em português.

## Key Learnings
- Personagem 'conectado' = `refresh_token IS NOT NULL` (discovery e crawler já filtram assim). invalid_grant no refresh → tokens zerados; o personagem aparece como 'Login expirado' no checklist e em Configurações → Personagens conectados.
- EVERef reference-data: reprocessamento fica em types.json[tid].type_materials (type_materials.json vem vazio). Fuzzwork SQLite: https://www.fuzzwork.co.uk/dump/latest-sqlite.db.gz (gzip, ~150 MB → ~476 MB), mesmas tabelas invTypes/industryActivity*/invTypeMaterials.
- Refresh token de personagem sem uso há meses volta invalid_grant — o personagem precisa logar de novo.

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
- [2026-09-24] NiceGUI: não chamar `refreshable.refresh()` em timer para atualizar texto — recria o elemento (pisca e perde estado de expansion). Atualizar labels no lugar e só dar refresh quando a estrutura mudar.
- [2026-09-24] .bat: nunca usar < ou > fora de aspas (nem em comentário) — o cmd redireciona. Aspas aninhadas em set "X=..."..."" deixam trechos fora de aspas.
- [2026-09-24] Push direto na main quando o usuário pedir: se o checkout for bloqueado por .wolf/*, usar `git push origin <branch>:main` (fast-forward) e `git branch -f main`.
- [2026-09-24] run.log do NiceGUI pode ter bytes binários: usar `grep -a`.
- [2026-09-24] Não usar `pkill -f run.py` (ou padrão que case com o próprio comando do shell): mata o shell da ferramenta (exit 144). Matar pelo PID ou usar padrão com caminho absoluto exclusivo.
- [2026-09-24] Arquivos da raiz (.bat, .gitignore) usam CRLF — editar preservando CRLF; .bat em ASCII puro.

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->
- [2026-09-24] Login EVE SSO via PKCE (`app/services/sso.py`) com Client ID embutido (`DEFAULT_EVE_CLIENT_ID` em config.py = app "Eve Curioso" do usuário) para o usuário leigo não precisar criar app/.env. O Client Secret NUNCA vai para o código/repo, só no .env local. `EVE_CLIENT_SECRET` é opcional: se presente, `sso_token_auth()` usa Basic auth; senão manda client_id no corpo. Todo POST em /v2/oauth/token deve usar `sso_token_auth()`.
- [2026-09-24] Primeiro uso automático em `app/services/first_run.py`: no startup importa SDE se faltar itens OU reprocessamento (subprocesso de import_sde.py; EVERef e, se falhar, Fuzzwork) e baixa preços de Jita se o cache estiver vazio. UI em `ui/components/setup_panel.py`: banner em todas as páginas + checklist no Dashboard. Login enfileira discovery de assets na hora.
- [2026-09-24] Launcher único `Iniciar.bat` com .venv local em eve_industry_tool/.venv; reinstala deps quando requirements.txt difere de .venv/requirements.installed. SECRET_KEY auto-gerada em eve_industry_tool/.secret_key.
- [2026-09-24] Linux: `iniciar.sh` usa .venv-linux (não colide com o .venv do Windows no mesmo disco) e abre no navegador por padrão (pywebview no venv não acha GTK/Qt). No NiceGUI, passar window_size força native — só passar quando native=True.
