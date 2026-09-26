# TODO

## Agora
- [ ] Publicar release v1.0.0 (`/release`)
- [ ] Testar `Iniciar.bat` no Windows (máquina sem Python → winget → venv → app)

## Depois
- [ ] Empacotar como `.exe` (PyInstaller/Nuitka) e publicar em GitHub Release
- [ ] Tooltips nos termos técnicos (ME, TE, SCI, SCC, broker fee)
- [ ] Assistente de primeiro uso (hub, mercado local, sistema de produção)
- [ ] Manter login entre aberturas (hoje o startup limpa a sessão)

## Ideias / talvez
- Refatorar: `industry_page.py`, `ranking_page.py` e `settings_page.py` são grandes — extrair seções para `ui/components/`
- Migrations para Alembic antes de mais mudanças de schema
- Dividir `esi_client.py` (18 métodos) em clientes de personagem/mercado/estrutura
- Unificar a lógica de crawl duplicada entre `scripts/atualizar_precos_mercado.py` e `crawler_service.py`
- Testes de serviço para `industry_calculator` e a recursão do `blueprint_service`
- Detectar rigs de estrutura nos assets e aplicar bônus automaticamente
- Checar atualização do SDE periodicamente (meta.json do EVERef traz build_time)
- Checklist reagir a login expirado sem precisar recarregar o Dashboard
