# Aprendizados

## Preferências do usuário
- Foco em facilitar o primeiro uso por usuário leigo (Windows). Textos de UI em português.
- NUNCA commitar dados de personagens nem sensíveis: `database.db*`, `.env`, `.secret_key`, `.nicegui/`, Client Secret, nomes/IDs de personagens em docs. Conferir o diff antes de commitar.
- Pode fazer push direto na `main` quando pedir.

## Pegadinhas (versão, API, CI)
- 2026-09-24 — EVERef: reprocessamento está em `types.json[tid].type_materials`; `type_materials.json` vem vazio.
- 2026-09-24 — Fuzzwork SQLite mudou para `https://www.fuzzwork.co.uk/dump/latest-sqlite.db.gz` (gzip); tabelas iguais.
- 2026-09-24 — `.bat`: `<`/`>` fora de aspas viram redirecionamento; aspas aninhadas em `set "X=..."` deixam trechos de fora.
- 2026-09-24 — Janela nativa no Windows depende de pythonnet: usar Python 3.11–3.13.
- 2026-09-24 — NiceGUI: passar `window_size` força `native`; `refreshable.refresh()` em timer recria o elemento (pisca).
- 2026-09-24 — Refresh token sem uso há meses volta `invalid_grant`: personagem precisa logar de novo.
- 2026-09-24 — Personagem "conectado" = `refresh_token IS NOT NULL` (discovery e crawler já filtram assim).
- 2026-09-24 — Log do NiceGUI pode ter bytes binários: usar `grep -a`.
- 2026-09-24 — Push direto na main com checkout bloqueado por arquivos locais: `git push origin <branch>:main` (fast-forward) e `git branch -f main`.
- Migrations ficam em `database.py → create_tables()` como blocos `ALTER TABLE` (sem Alembic). TTLs: mercado de região 5 min, estrutura 4 h, skills 1 h, info de estrutura 24 h.
- 2026-09-24 — Repo mudou para `meketreve/EVE-ONLINE-ajudante-da-industria` (sem traço triplo).

## Erros a não repetir
- 2026-09-24 — `pkill -f <padrão>` que casa com o próprio comando mata o shell da ferramenta. Matar pelo PID (via `ss -ltnp`).
- 2026-09-24 — Arquivos da raiz com CRLF (`.bat`): preservar; `.gitignore` e código em LF (HEAD é LF).

## Decisões e o porquê
- 2026-09-24 — Login PKCE com Client ID embutido: usuário não cria app nem `.env`. Secret opcional só no `.env` local.
- 2026-09-24 — Primeiro uso automático + checklist em vez de passos manuais no README.
- 2026-09-24 — OpenWolf removido (`.wolf/`, hooks e regras); o contexto do projeto fica só em `.claude/context/`.
- 2026-09-24 — `.gitattributes`: `*.bat -text` (mantém CRLF no ZIP do GitHub), `*.sh eol=lf`.
