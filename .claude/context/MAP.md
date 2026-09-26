# Mapa do projeto

## Comandos
| Ação | Comando |
|---|---|
| Build | — (Python puro) |
| Teste (tudo) | — (não há testes no repo) |
| Teste (um só) | — |
| Lint/format | `ruff check eve_industry_tool` (ruff não está no requirements; ~300 avisos antigos) |
| Rodar (Linux) | `./iniciar.sh` (navegador) · `./iniciar.sh --sem-secret` testa PKCE |
| Rodar (Windows) | `Iniciar.bat` |
| Rodar (manual) | `cd eve_industry_tool && python -m app.main` · `EVE_TOOL_NATIVE=0` abre no navegador |
| Checar autoupdate | `python3 atualizar.py` numa cópia **sem `.git`** (`EVE_TOOL_UPDATE_API=<url>` aponta para uma API falsa em testes) |
| Publicar release | skill `/release` (VERSION → commit → `gh release create vX.Y.Z`) |
| Reimportar SDE | `cd eve_industry_tool && python scripts/import_sde.py [--source fuzzwork] [--force-download]` |

## Onde fica cada coisa
- `atualizar.py` + `VERSION` (raiz) — autoupdate por GitHub Release; manifesto local em `.arquivos-instalados`
- `.claude/skills/release/SKILL.md` — passo a passo da release; `.claude/context/WORKFLOW.md` — quando lembrar dela
- `Iniciar.bat` / `iniciar.sh` — launchers (bloco 0 = autoupdate + reinício); venv em `eve_industry_tool/.venv` (Windows) e `.venv-linux` (Linux)
- `eve_industry_tool/app/main.py` — entry point, callback OAuth, scheduler, startup (`run_first_run`)
- `eve_industry_tool/app/config.py` — `DEFAULT_EVE_CLIENT_ID`, `APP_PORT`, `SECRET_KEY` automática, `sso_token_auth()`
- `app/services/sso.py` — URL de login com PKCE (state + verifier)
- `app/services/first_run.py` — SDE/preços automáticos (`tasks`) e `get_checklist()`
- `app/ui/components/setup_panel.py` — banner de progresso e checklist do Dashboard
- `app/services/character_service.py` — `get_fresh_token` (invalid_grant zera tokens = login expirado)
- `app/ui/settings_page.py` — Configurações, seção "Personagens conectados", botões de scripts/SDE
- `scripts/import_sde.py` — importador EVERef (padrão) / Fuzzwork
- `app/database/database.py` — migrations `ALTER TABLE` no startup (sem Alembic)

## Pontos de entrada e fluxos principais
- Startup → `init_db` → workers de job → `run_first_run` (SDE se faltar itens/reprocessamento, depois preços de Jita) → scheduler (crawl 15 min, limpeza 1 h, discovery 6 h)
- Login → `start_login()` abre o SSO → `/auth/callback` troca code+verifier por tokens → grava `Character` → enfileira discovery de assets
- Páginas leem só do SQLite (cache-first); ESI só em tarefas de background
