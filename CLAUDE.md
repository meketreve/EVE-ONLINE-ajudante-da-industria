# Contexto do projeto

@.claude/context/STATUS.md
@.claude/context/TODO.md
@.claude/context/MAP.md
@.claude/context/LEARNINGS.md

# EVE Industry Tool

Aplicação local para industrialistas do EVE Online: custo de produção, lucro, ranking de importação,
reprocessamento e mercados de estruturas. Integra EVE SSO (OAuth2 com PKCE) e a ESI. Público-alvo inclui
usuário leigo no Windows, então o primeiro uso tem que funcionar sem configuração.

Comandos, caminhos e fluxos estão em `.claude/context/MAP.md`. Bugs já resolvidos em `.claude/context/BUGS.md`
(consultar antes de corrigir um erro).

## Stack

- **UI**: NiceGUI (`app/ui/`, páginas com `@ui.page`), janela nativa via pywebview no Windows; navegador no
  Linux (`EVE_TOOL_NATIVE=0`)
- **Backend**: Python 3.11–3.13, SQLAlchemy async + aiosqlite, HTTPX
- **Banco**: SQLite `eve_industry_tool/database.db` (WAL)
- **Dados**: ESI (ao vivo, cacheado no SQLite) + SDE via EVERef (padrão) ou Fuzzwork (`scripts/import_sde.py`)

## Arquitetura

- **Cache-first**: páginas só leem do SQLite; chamadas à ESI acontecem em tarefas de background que atualizam o banco.
- **Startup** (`app/main.py`): `init_db` → workers do `job_runner` (discovery 3, crawl 2) → `first_run.run_first_run`
  (SDE se faltar itens/reprocessamento, depois preços de Jita) → scheduler (recrawl 15 min, limpeza 1 h, discovery 6 h).
- **Login**: `services/sso.py` monta a URL PKCE → `/auth/callback` em `main.py` troca code+verifier → grava
  `Character` → enfileira discovery de assets. Todos os personagens com `refresh_token` são usados em background.
- **Tokens**: `character_service.get_fresh_token` renova; `invalid_grant` zera os tokens (personagem aparece como
  "Login expirado"). Todo POST em `/v2/oauth/token` usa `config.sso_token_auth()`.

## Regras de negócio

```
Material Cost = Σ(quantidade × preço_unitário)
Job Cost      = item_value_ajustado × (SCI + facility_tax + SCC)
Net Profit    = sell_price × (1 - broker_fee - sales_tax) - total_cost
ME            = ceil(qty_base × (1 - blueprint_ME/100) × (1 - estrutura_ME/100))   # por nó do BOM
Margem import = preço_local × (1 - sales_tax - broker_fee) - preço_fonte - frete/un.
```

Broker fee e sales tax vêm das skills do personagem (Broker Relations, Accounting) quando disponíveis.

## Convenções

- Textos de UI em português.
- Migrations: bloco `ALTER TABLE` em `app/database/database.py → create_tables()` (sem Alembic).
- NiceGUI: atualizar textos no lugar; `refreshable.refresh()` só quando a estrutura muda (senão pisca).
- Fim de linha: código em LF; `Iniciar.bat` em CRLF e ASCII puro, sem `<`/`>` fora de aspas.
- **Nunca commitar** `database.db*`, `.env`, `.secret_key`, `.nicegui/`, Client Secret nem nomes/IDs de
  personagens. O Client ID em `config.py` é público (PKCE) e pode ficar no código.
