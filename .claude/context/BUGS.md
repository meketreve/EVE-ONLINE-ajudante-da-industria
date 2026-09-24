# Bugs resolvidos

<!-- Um bloco por bug. Colocar a mensagem de erro literal para o grep achar. -->

## 2026-09-24 — reprocessing_materials com 0 linhas após importar SDE
- **Sintoma:** reprocessamento vazio; log "0 entradas de reprocessamento".
- **Causa:** EVERef moveu os dados para `types.json` → `type_materials`.
- **Correção:** `scripts/import_sde.py` lê de `types_data` (commit 5f1433f).

## 2026-09-24 — Importar SDE via Fuzzwork: HTTP 404
- **Sintoma:** download do Fuzzwork falha.
- **Causa:** URL `sqlite-latest.sqlite.bz2` virou `latest-sqlite.db.gz`.
- **Correção:** nova URL + gzip em streaming (commit 5f1433f).

## 2026-09-24 — Iniciar.bat não achava Python via py/python
- **Sintoma:** só achava Python nas pastas padrão; criava arquivo `=`.
- **Causa:** `>=` fora de aspas no `set "CHECK=..."` virava redirecionamento.
- **Correção:** checagem inline sem `<`/`>` (commit e77fe05).

## 2026-09-24 — Painel "Tudo pronto para usar" some e volta
- **Sintoma:** checklist pisca durante downloads.
- **Causa:** `render.refresh()` a cada 3 s recriava o card.
- **Correção:** refresh só quando o estado dos passos muda (`setup_panel.py`).

## 2026-09-24 — Dashboard mostra 2 personagens, Configurações 1
- **Sintoma:** contagem divergente.
- **Causa:** checklist contava personagens com login expirado.
- **Correção:** `invalid_grant` zera tokens; checklist e Configurações mostram conectado/expirado.

## 2026-09-24 — Login falha sem EVE_CALLBACK_URL no .env
- **Causa:** callback padrão na porta 8000; app roda na 8765.
- **Correção:** `APP_PORT` em `config.py`.
