# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-09-24T17:15:54.645Z
> Files: 70 tracked | Anatomy hits: 0 | Misses: 0

## ../../../../home/meketreve/.claude/projects/-mnt-SSD-git-projeto-EVE-ONLINE---ajudante-da-industria/memory/

- `no-sensitive-commits.md` (~252 tok)

## ./

- `.gitignore` — Git ignore rules (~402 tok)
- `CLAUDE.md` — OpenWolf (~2655 tok)
- `Iniciar.bat` — launcher único: acha/instala Python 3.11+, cria .venv, instala deps quando requirements muda, roda app.main (~900 tok)
- `iniciar.sh` — launcher Linux: .venv-linux, deps, abre no navegador (EVE_TOOL_NATIVE=0); --sem-secret testa PKCE, --nativo janela nativa (~700 tok)
- `iniciar.sh` — EVE Industry Tool — iniciar no Linux (~819 tok)
- `README.md` — Project documentation (~1952 tok)

## .claude/

- `settings.json` (~441 tok)
- `settings.local.json` (~1701 tok)

## .claude/rules/

- `openwolf.md` (~313 tok)

## eve_industry_tool/

- `database.db-shm` (~8737 tok)
- `requirements.txt` — Python dependencies (~27 tok)

## eve_industry_tool/.nicegui/

- `storage-general.json` (~393 tok)
- `storage-user-0bc9d455-9f3f-4374-8240-c98b4aea04a6.json` (~18 tok)
- `storage-user-48caea18-e26b-4c72-87c0-b0aefa918d3e.json` (~370 tok)
- `storage-user-54a9d09e-e955-488f-8a8c-e57a023bbc31.json` (~18 tok)

## eve_industry_tool/app/

- `config.py` — Settings: sso_token_auth (~763 tok)
- `main.py` — handle_oauth_callback, startup, shutdown (~3230 tok)

## eve_industry_tool/app/database/

- `__init__.py` (~0 tok)
- `database.py` — Base: get_db, init_db, create_tables (~1183 tok)

## eve_industry_tool/app/models/

- `__init__.py` (~0 tok)
- `blueprint.py` — Flask blueprint (~361 tok)
- `cache.py` — SQLAlchemy: MarketPriceCache (market_price_cache) (~691 tok)
- `character.py` — SQLAlchemy: Character (characters) (~355 tok)
- `item.py` — SQLAlchemy: Item (items) (~256 tok)
- `job.py` — SQLAlchemy: DiscoveryJob (discovery_jobs) (~805 tok)
- `manufacturing_structure.py` — SQLAlchemy: ManufacturingStructure (manufacturing_structures) (~390 tok)
- `market_order.py` — SQLAlchemy: MarketOrder (market_orders_raw) (~484 tok)
- `market_snapshot.py` — SQLAlchemy: MarketSnapshot (market_snapshots) (~378 tok)
- `market_structure.py` — SQLAlchemy: MarketStructure (market_structures) (~301 tok)
- `production_queue.py` — SQLAlchemy: ProductionQueue (production_queue) (~814 tok)
- `reprocessing.py` — SQLAlchemy: ReprocessingMaterial (reprocessing_materials) (~181 tok)
- `structure.py` — SQLAlchemy: Structure (structures) (~1008 tok)
- `user_settings.py` — SQLAlchemy: UserSettings (user_settings) (~430 tok)
- `user.py` — SQLAlchemy: User (users) (~180 tok)

## eve_industry_tool/app/services/

- `__init__.py` (~0 tok)
- `blueprint_service.py` — class: is_leaf, get_recursive_bom, aggregate_bom_leaves (~4920 tok)
- `character_service.py` — get_character, get_fresh_token, get_skill_levels, calculate_sales_tax + 3 more (~3594 tok)
- `crawler_service.py` — run_crawl_job (~5116 tok)
- `discovery_service.py` — enqueue_asset_discovery, enqueue_validate (~3277 tok)
- `esi_client.py` — ESIError: client, close, get_character_info, get_character_skills + 14 more (~3514 tok)
- `first_run.py` — is_running, sde_missing, ensure_sde, ensure_hub_prices (~2664 tok)
- `first_run.py` — tasks, ensure_sde (itens OU reprocessamento vazios; fallback Fuzzwork), ensure_hub_prices (Jita), run_first_run, get_checklist (~2300 tok)
- `industry_calculator.py` — from: total_cost, calculate_production_cost, calculate_profit, apply_me_level (~1255 tok)
- `job_runner.py` — JobRunner: start, stop, enqueue (~878 tok)
- `market_service.py` — clear_price_cache, get_prices_cache_only, refresh_prices_for_types, get_best_price + 4 more (~4298 tok)
- `settings_service.py` — load_settings, save_settings (~1462 tok)
- `sso.py` — start_login, pop_verifier (~441 tok)

## eve_industry_tool/app/ui/

- `__init__.py` — NiceGUI UI package (~7 tok)
- `auth_page.py` — login_page, do_login, check_auth (~902 tok)
- `dashboard_page.py` — dashboard_page (~1218 tok)
- `industry_page.py` — industry_page (~11989 tok)
- `items_page.py` — items_page, run_search, on_search_change, run_search_page (~1854 tok)
- `layout.py` — page_layout (~1026 tok)
- `queue_page.py` — queue_page, show_add_dialog, add_item, show_bom_dialog (~4333 tok)
- `ranking_item_page.py` — ranking_item_page (~3558 tok)
- `ranking_page.py` — ranking_page, do_refresh_prices, refresh_ranking, do_compare (~11286 tok)
- `reprocessing_page.py` — reprocessing_page, do_calculate (~5084 tok)
- `settings_page.py` — settings_page, save_settings, do_logout, do_login_from_settings (~12076 tok)

## eve_industry_tool/app/ui/components/

- `__init__.py` — NiceGUI UI components package (~10 tok)
- `bom_tree.py` — render_bom_tree (~4092 tok)
- `cost_breakdown.py` — render_cost_breakdown (~1441 tok)
- `price_chart.py` — render_price_charts (~998 tok)
- `setup_panel.py` — first_run_banner (progresso/erro + Tentar de novo), setup_checklist (Dashboard) (~1400 tok)
- `setup_panel.py` — first_run_banner, refresh, setup_checklist, render (~1609 tok)
- `structure_selector.py` — render_structure_selector, get_structure_bonuses (~586 tok)

## eve_industry_tool/scripts/

- `atualizar_estruturas.py` — ScriptESIClient: close, refresh_token, get_corp_structures_with_market, get_universe_market_structure_ids + 7 more (~6124 tok)
- `atualizar_precos_mercado.py` — ESIClient: client, close, refresh_token, get_structure_orders + 4 more (~3917 tok)
- `import_sde.py` — download_everef, import_from_everef, download_fuzzwork, import_from_fuzzwork (~5420 tok)
- `ordens_null.py` — Client: close, refresh_token, get_structure_info, get_system_name + 6 more (~4859 tok)
