# EVE Industry Tool

Aplicação **desktop local** para industrialistas do **EVE Online** calcularem custos de produção, margens de lucro e oportunidades de importação. Integra com EVE SSO (OAuth2) e ESI API para dados ao vivo de personagem, mercado e estruturas.

Interface gráfica nativa via **NiceGUI** — abre como janela desktop, sem browser externo.

---

## Funcionalidades

| Módulo | Descrição |
|--------|-----------|
| **Calculadora de Produção** | BOM recursivo, ME por item e por estrutura, bônus de estrutura, job cost (SCI + facility tax + SCC), taxas, lucro bruto e líquido |
| **Comparação de Preços no BOM** | Seleção de estrutura de manufatura por sub-componente — identifica o que vale importar ou fabricar em outra instalação |
| **Fila de Produção** | Jobs planejados com BOM agregado, lista de compras unificada com botão de cópia |
| **Ranking de Importação** | Itens com maior margem entre mercado fonte e local, com cálculo de frete |
| **Comparador de Lista** | Cola uma lista de itens e compara custo de importar vs comprar localmente |
| **Projeção de Mercado** | Histórico ESI com charts de volume e preço, projeção 7/14/30 dias |
| **Reprocessamento** | Calcula se vale reprocessar o item ou vendê-lo diretamente |
| **Estruturas de Manufatura** | Cadastro de Raitaru/Azbel/Sotiyo com bônus ME aplicado no cálculo |
| **Descoberta de Estruturas** | Escaneia assets pessoais para encontrar citadelas acessíveis com mercado |
| **Mercados Privados** | Crawl automático a cada 15 min de ordens de estruturas Upwell |
| **Login via EVE SSO** | Acesso a skills, assets e mercados privados do personagem |

---

## Stack

| Camada | Tecnologia |
|--------|------------|
| GUI | NiceGUI (`native=True`) + pywebview |
| Backend | Python 3.11+, SQLAlchemy async (aiosqlite) |
| Banco | SQLite (WAL mode) |
| Auth | EVE SSO (OAuth2) |
| Dados EVE | ESI API + SDE (Static Data Export via EVERef/Fuzzwork) |

---

## Arquitetura de dados

O app segue o padrão **cache-first com atualizações em background**:

- Todas as consultas leem do banco SQLite local (resposta imediata)
- Chamadas à ESI só ocorrem para atualizar o banco, nunca para responder ao usuário diretamente
- Refresh de preços em massa (ex: todas as ordens de Jita) roda via `asyncio.create_task` — sem bloquear a UI
- Scheduler interno: recrawl de estruturas a cada 15 min, limpeza de ordens a cada 1h, rediscovery a cada 6h

---

## Como usar (Windows)

1. Baixe o projeto (botão **Code → Download ZIP** no GitHub) e extraia em uma pasta.
2. Dê dois cliques em **`Iniciar.bat`**.
3. Clique em **Entrar com EVE Online** e autorize o personagem no navegador.

Só isso. Na primeira execução o `Iniciar.bat`:

- procura o Python 3.11+ e, se não houver, oferece instalar via `winget`;
- cria um ambiente isolado em `eve_industry_tool/.venv` e instala as dependências (reinstala sozinho quando `requirements.txt` muda);
- abre o app, que baixa sozinho os dados do jogo (SDE, ~14 MB; se falhar, usa o Fuzzwork) e os preços de Jita, com aviso de progresso;
- no Dashboard, um checklist de **Primeiros passos** mostra o que está pronto e o que falta configurar.

Não é preciso criar conta de desenvolvedor nem arquivo `.env`: o login usa o fluxo **PKCE** do EVE SSO com o Client ID do projeto (`DEFAULT_EVE_CLIENT_ID` em `app/config.py`). A `SECRET_KEY` da sessão é gerada no primeiro uso e guardada em `eve_industry_tool/.secret_key`.

---

## Instalação manual / desenvolvimento

Requer Python 3.11+.

```bash
cd eve_industry_tool
pip install -r requirements.txt
python -m app.main
```

O SDE é importado automaticamente se o banco estiver vazio. Para reimportar: **Configurações → Importar SDE**, ou `python scripts/import_sde.py`.

### Usar a sua própria aplicação EVE (opcional)

Registre uma aplicação em [developers.eveonline.com](https://developers.eveonline.com) com callback `http://localhost:8765/auth/callback` e os escopos abaixo, e crie `eve_industry_tool/.env`:

```env
EVE_CLIENT_ID=seu_client_id
# Opcional — sem ele o login usa PKCE (recomendado para app desktop)
EVE_CLIENT_SECRET=seu_client_secret
```

**Escopos ESI necessários:**
```
esi-skills.read_skills.v1
esi-characters.read_blueprints.v1
esi-assets.read_assets.v1
esi-markets.structure_markets.v1
esi-corporations.read_structures.v1
esi-universe.read_structures.v1
```

---

## Estrutura do Projeto

```
eve_industry_tool/
├── app/
│   ├── main.py                    # Entry point NiceGUI (native=True), scheduler, OAuth callback
│   ├── config.py                  # Configurações e variáveis de ambiente
│   ├── ui/                        # Páginas e componentes NiceGUI
│   │   ├── auth_page.py           # Login EVE SSO
│   │   ├── dashboard_page.py      # Dashboard inicial
│   │   ├── items_page.py          # Browser de itens
│   │   ├── industry_page.py       # Calculadora de produção + BOM recursivo
│   │   ├── reprocessing_page.py   # Calculadora de reprocessamento
│   │   ├── queue_page.py          # Fila de produção + lista de compras
│   │   ├── ranking_page.py        # Ranking de importação + comparador de lista
│   │   ├── ranking_item_page.py   # Projeção de mercado com charts
│   │   ├── settings_page.py       # Configurações + estruturas de manufatura
│   │   └── components/
│   │       ├── bom_tree.py        # Árvore BOM expansível com ME e estação por nó
│   │       ├── cost_breakdown.py  # Painel custo/lucro
│   │       ├── structure_selector.py
│   │       └── price_chart.py     # Charts ECharts
│   ├── services/                  # Lógica de negócio
│   │   ├── esi_client.py          # Wrapper async da ESI API
│   │   ├── market_service.py      # Cache de preços, refresh de mercado
│   │   ├── industry_calculator.py # Fórmulas de custo e lucro
│   │   ├── blueprint_service.py   # BOM recursivo com pré-carregamento em batch
│   │   ├── crawler_service.py     # Crawl de mercados de estruturas (background)
│   │   ├── discovery_service.py   # Descoberta de estruturas via assets
│   │   ├── job_runner.py          # Fila de jobs async com deduplicação
│   │   ├── settings_service.py    # Load/save de configurações do usuário
│   │   ├── character_service.py   # Dados de personagem, skills, token refresh
│   │   ├── sso.py                 # URL de login EVE SSO com PKCE
│   │   └── first_run.py           # Primeiro uso: SDE + preços de Jita automáticos e checklist
│   ├── models/                    # ORM SQLAlchemy (16 tabelas)
│   └── database/
│       └── database.py            # Setup SQLite, migrations no startup
├── scripts/
│   ├── import_sde.py              # Importação do SDE (EVERef ou Fuzzwork)
│   ├── atualizar_estruturas.py    # Descoberta de estruturas via ESI
│   ├── atualizar_precos_mercado.py
│   └── ordens_null.py             # Ordens de estruturas nullsec
├── Iniciar.bat                    # Instala o que faltar e abre o app (Windows)
├── requirements.txt
└── .env                           # Opcional: credenciais próprias (não versionado)
```

---

## Scripts Auxiliares

```bash
# Atualizar estruturas Upwell via ESI
python eve_industry_tool/scripts/atualizar_estruturas.py

# Atualizar preços de mercado manualmente
python eve_industry_tool/scripts/atualizar_precos_mercado.py

# Importar ordens de estruturas nullsec
python eve_industry_tool/scripts/ordens_null.py --listar
python eve_industry_tool/scripts/ordens_null.py --id <structure_id>
```

---

## Fórmulas

### Custo de Produção
```
Material Cost = Σ(quantidade × preço_unitário)
Job Cost      = item_value_ajustado × (SCI + facility_tax + SCC)
Total         = Material Cost + Job Cost
```

### Lucro
```
Gross Profit = sell_price - total_cost
Net Profit   = sell_price × (1 - broker_fee - sales_tax) - total_cost
```

### Material Efficiency
```
qty = ceil(qty_base × (1 - blueprint_ME/100) × (1 - estrutura_ME/100))
```

Aplica-se por nó do BOM — cada sub-componente pode ter estrutura e ME independentes.

### Margem de Importação
```
Margem = preço_local × (1 - sales_tax - broker_fee) - preço_fonte - frete/un.
```

---

## Observações

- O banco (`database.db`) é criado automaticamente na primeira execução — não é versionado
- Migrations de schema rodam no startup sem destruir dados existentes
- Todos os dados ficam locais — nada é enviado além da ESI oficial da CCP
- A ESI não expõe rigs de estruturas; o cadastro de bônus ME é manual em Configurações
- Não afiliado à CCP Games
