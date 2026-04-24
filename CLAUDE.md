# OpenWolf

@.wolf/OPENWOLF.md

This project uses OpenWolf for context management. Read and follow .wolf/OPENWOLF.md every session. Check .wolf/cerebrum.md before generating code. Check .wolf/anatomy.md before reading files.


# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Local web application for EVE Online industrialists to calculate production costs, profit margins, and item rentability. Integrates with EVE SSO (OAuth2) and the ESI API. The project is **functional and in active development** — core features are complete and work is underway on the import ranking system and freight cost integration.

## Tech Stack

- **Backend**: Python, FastAPI, SQLAlchemy (async), HTTPX
- **Frontend**: Jinja2 templates, HTMX, CSS
- **Database**: SQLite (`database.db`) with WAL mode for concurrency
- **Auth**: EVE SSO (OAuth2)
- **External data**: ESI API + SDE (Static Data Export via EVERef/Fuzzwork)
- **Async runtime**: aiosqlite, asyncio

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Import SDE data (one-time setup)
python scripts/import_sde.py

# Run the development server
uvicorn app.main:app --reload

# Run tests
pytest

# Lint
ruff check .
```

## Directory Structure

```
eve_industry_tool/
├── app/
│   ├── main.py                    # FastAPI app entry point, lifespan management, scheduler
│   ├── config.py                  # Settings (EVE_CLIENT_ID, ESI base URL, DB path, etc.)
│   ├── api/                       # Route handlers
│   │   ├── auth.py                # EVE SSO OAuth2 login/callback/logout
│   │   ├── items.py               # Item browsing & search
│   │   ├── industry.py            # Cost calculation & import ranking (IN DEVELOPMENT)
│   │   ├── market.py              # Market data & structure management
│   │   ├── settings.py            # User settings persistence (IN DEVELOPMENT)
│   │   └── discovery.py           # Structure discovery API
│   ├── services/                  # Business logic layer
│   │   ├── esi_client.py          # EVE API wrapper with async HTTP + token refresh
│   │   ├── industry_calculator.py # Cost & profit formulas
│   │   ├── market_service.py      # Price caching & retrieval (IN DEVELOPMENT)
│   │   ├── blueprint_service.py   # Blueprint materials + ME reduction
│   │   ├── character_service.py   # Character data, skills, trading fee calculation
│   │   ├── discovery_service.py   # Upwell structure discovery pipeline
│   │   ├── crawler_service.py     # Market data crawling from structures
│   │   └── job_runner.py          # In-memory async job queue with deduplication
│   ├── models/                    # SQLAlchemy ORM models
│   │   ├── user.py                # User accounts
│   │   ├── character.py           # EVE characters with OAuth tokens
│   │   ├── item.py                # Manufacturable items from SDE
│   │   ├── blueprint.py           # Blueprints & materials
│   │   ├── production_queue.py    # User's production queue
│   │   ├── user_settings.py       # App settings (IN DEVELOPMENT — freight field added)
│   │   ├── cache.py               # Market prices, structures, skills (IN DEVELOPMENT)
│   │   ├── market_order.py        # Raw market orders from structure crawls
│   │   ├── market_snapshot.py     # Aggregated market data (best sell/buy)
│   │   ├── structure.py           # Upwell structure metadata
│   │   ├── job.py                 # Discovery & crawl job tracking
│   │   └── market_structure.py    # Discoverable structures index
│   ├── database/
│   │   └── database.py            # SQLite setup, migrations, session management (IN DEVELOPMENT)
│   └── templates/                 # Jinja2 HTML + HTMX
│       ├── base.html              # Navigation & layout
│       ├── index.html             # Dashboard
│       ├── items.html             # Item browser with search
│       ├── item_detail.html       # Single item calculation form
│       ├── login.html             # SSO login page
│       ├── market.html            # Market overview
│       ├── settings.html          # App settings (IN DEVELOPMENT)
│       ├── ranking.html           # Import opportunities ranking (IN DEVELOPMENT)
│       ├── production_queue.html  # Queue management
│       └── partials/              # HTMX fragments
│           ├── items_table.html
│           └── calculation_result.html
├── scripts/
│   ├── import_sde.py              # SDE data import (EVERef or Fuzzwork)
│   ├── atualizar_estruturas.py    # Structure discovery & update
│   ├── atualizar_precos_mercado.py # Market price refresh
│   └── ordens_null.py             # Null-sec order aggregation
├── static/
│   └── style.css
├── database.db                    # SQLite main DB (~15 MB with SDE data)
├── requirements.txt
└── .env                           # EVE_CLIENT_ID, EVE_CLIENT_SECRET, SECRET_KEY
```

## Architecture

**Request flow**: Browser → FastAPI → Services → ESI API / SQLite

**Core engines**:
- `Auth` (`auth.py`): OAuth2 via EVE SSO — login redirect, code exchange, token storage (access + refresh), 7-day sessions
- `Industry Engine` (`industry_calculator.py`): Computes production cost and profit
- `Market Engine` (`market_service.py`): Aggregates prices from public hubs, private structures, and manual overrides
- `Blueprint Engine` (`blueprint_service.py`): Handles T1 and T2 production specs with ME reduction
- `Discovery Engine` (`discovery_service.py`): Automated Upwell structure discovery via character assets, multi-character fallback
- `Job Runner` (`job_runner.py`): In-memory async queue — discovery (3 workers) and crawl (2 workers)

**Scheduler** (in `main.py` lifespan):
- Every 15 min: Recrawl all accessible structures
- Every 1 hour: Clean stale orders (48+ hours old)
- Every 6 hours: Rediscovery of structures from all character assets

**Data sources**:
- **ESI**: Live data (character, skills, market orders, private structures) — cached in SQLite
- **SDE**: Static game data (items, blueprints, materials) — imported once via `scripts/import_sde.py`
- **User config**: Settings stored in `user_settings` table (ME level, cost indices, taxes, freight)

## Key Business Logic

**Production cost**:
```
Material Cost = Σ(quantity × material_price)
Job Cost = system_cost_index + facility_tax + SCC_tax
Total Cost = Material Cost + Job Cost + broker_fee + sales_tax + logistics + freight
```

**Profit**:
```
Gross Profit = sale_price - production_cost
Net Profit   = sale_price - production_cost - taxes - fees
```

**Import Ranking** (in development):
```
Import Margin = local_sell_price - (source_sell_price + freight_cost_per_m3 × volume) - taxes
```
Compares Jita/Amarr prices vs. local market to identify import opportunities.

**Skill-based trading fees**:
- Reads `Broker Relations` and `Accounting` from ESI (1-hour cache)
- Overrides default tax rates for cost/profit calculation

**Invention (T2)**: Framework exists, requires success chance, datacores, and decryptors as cost inputs (incomplete).

## Database Schema (16 Tables)

| Table | Purpose | Status |
|-------|---------|--------|
| `users` | User accounts | Complete |
| `characters` | EVE characters + OAuth tokens | Complete |
| `items` | Item catalog (SDE) | Complete |
| `blueprints` | Blueprint specs | Complete |
| `blueprint_materials` | Material requirements | Complete |
| `production_queue` | User's production plans | Complete |
| `user_settings` | Global app settings | In development |
| `market_price_cache` | Cached prices (5 min TTL) | In development |
| `market_orders_raw` | Raw orders from structure crawls | Complete |
| `market_snapshots` | Aggregated market data | Complete |
| `structures` | Upwell structure metadata | Complete |
| `structure_discovery_sources` | Where structures were found | Complete |
| `market_structures` | Discoverable structures index | Complete |
| `structure_cache` | Structure info cache (24h TTL) | Complete |
| `skill_cache` | Character skills (1h TTL) | Complete |
| `discovery_jobs` / `crawl_jobs` | Job execution history | Complete |

Migrations are embedded in `database.py → create_tables()`. Adding new columns requires adding an `ALTER TABLE` migration block there.

## Required ESI OAuth2 Scopes

```
esi-skills.read_skills.v1
esi-characters.read_blueprints.v1
esi-markets.structure_markets.v1
esi-corporations.read_structures.v1
```

## Key ESI Endpoints

- `GET /characters/{character_id}` — character info
- `GET /characters/{character_id}/skills` — skills
- `GET /characters/{character_id}/blueprints` — owned blueprints
- `GET /markets/{region_id}/orders` — public market
- `GET /markets/structures/{structure_id}` — private structure market (requires auth)
- `GET /universe/structures/{structure_id}` — structure info

## Cache TTLs

| Data | TTL | Storage |
|------|-----|---------|
| Public region market prices | 5 minutes | `market_price_cache` |
| Private structure market | 4 hours | `market_orders_raw` + `market_snapshots` |
| Character skills | 1 hour | `skill_cache` |
| Structure info | 24 hours | `structure_cache` |

## Active Development (as of 2026-03-14)

8 files currently modified (staged in git):

1. **`api/industry.py`** — Rewriting ranking endpoint as "import_ranking": compare source vs. local market
2. **`api/settings.py`** — Added freight cost field support
3. **`models/cache.py`** — Added `total_volume` column to `MarketPriceCache`
4. **`models/user_settings.py`** — Added `default_freight_cost_per_m3` field
5. **`services/market_service.py`** — Updated caching logic
6. **`templates/ranking.html`** — New UI for import opportunities
7. **`templates/settings.html`** — Freight cost input field
8. **`database/database.py`** — Migration for `freight_cost` column

## Planned Features (todo.md)

1. Side-by-side price comparison for BOM items
2. Enhanced production queue with aggregate material list
3. ME efficiency per BOM item (not just global)
4. Recursive BOM calculation (components of components)
5. Flag BOM items to buy-as-is instead of manufacture
6. Market projection with configurable time windows (1 wk / 2 wk / 1 mo)
7. Database-backed price updates for BOM (avoid ESI calls mid-calculation)
8. Station bonuses (ME, TE) in settings
9. Auto-detect structure rigs from personal assets
10. Structure registry with manual bonus entry
11. Market volume graphs & predictive analytics
