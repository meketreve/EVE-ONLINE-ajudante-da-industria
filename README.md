# EVE Industry Tool

Aplicação **local** para industrialistas do **EVE Online** calcularem custos de produção, margens de lucro e oportunidades de importação. Integra com EVE SSO (OAuth2) e ESI API para dados ao vivo de personagem, mercado e estruturas.

Interface gráfica via **NiceGUI**: no Windows abre como janela desktop; no Linux abre no navegador.

---

## Como usar

### Windows

1. Baixe a versão mais recente em [**Releases**](https://github.com/meketreve/EVE-ONLINE-ajudante-da-industria/releases/latest) (arquivo **Source code (zip)**) e extraia em uma pasta.
2. Dê dois cliques em **`Iniciar.bat`**.
3. Clique em **Entrar com EVE Online** e autorize o personagem no navegador.

Só isso. Na primeira execução o `Iniciar.bat`:

- procura o Python 3.12, 3.13 ou 3.11 e, se não houver, oferece instalar o 3.12 via `winget`;
- cria um ambiente isolado em `eve_industry_tool/.venv` e instala as dependências (reinstala sozinho quando `requirements.txt` muda);
- abre o app. Não feche a janela preta do terminal enquanto usa o programa.

### Linux

```bash
./iniciar.sh
```

Requer Python 3.11+ com `venv` (Ubuntu/Debian: `sudo apt install python3 python3-venv`). O script cria `eve_industry_tool/.venv-linux`, instala as dependências e abre o app em `http://localhost:8765`.

| Opção | O que faz |
|-------|-----------|
| `--sem-secret` | Ignora o `EVE_CLIENT_SECRET` do `.env` e testa o login como um usuário novo (PKCE) |
| `--nativo` | Tenta abrir em janela nativa (precisa de GTK ou Qt no sistema) |
| `--help` | Mostra as opções |

### Primeiro uso

Não é preciso criar conta de desenvolvedor nem arquivo `.env`. Ao abrir, o app prepara tudo sozinho, em segundo plano:

- **Dados do jogo (SDE)**: itens, blueprints e reprocessamento (~14 MB do EVERef; se falhar, usa o Fuzzwork, ~150 MB). Também reimporta se algum desses dados estiver faltando.
- **Preços de Jita**: todas as ordens da região (~35 mil itens, cerca de 1 minuto).
- **Mercados de estruturas**: logo após o login, procura citadelas com mercado nos assets do personagem.

Um aviso no topo das páginas mostra o andamento, com botão **Tentar de novo** se algo falhar. No **Dashboard**, o checklist **Primeiros passos** mostra o que está pronto e o que falta (revisar mercado e taxas, cadastrar estrutura de produção) e vira uma linha "Tudo pronto para usar" quando o essencial está feito.

### Atualização automática

Toda vez que você abre o programa pelo `Iniciar.bat` ou `iniciar.sh`, ele verifica se há uma versão nova publicada em [Releases](https://github.com/meketreve/EVE-ONLINE-ajudante-da-industria/releases) e, se houver, atualiza sozinho antes de abrir.

- Seus dados ficam intactos: banco (`database.db`), personagens, configurações, `.env` e `.secret_key` nunca são sobrescritos.
- Sem internet ou com o GitHub fora do ar, o programa abre na versão atual (a verificação espera no máximo 5 segundos).
- Se a release baixada estiver incompleta ou corrompida, nada é alterado.
- Pasta clonada com `git` não é atualizada sozinha: use `git pull`.
- Para desligar: crie um arquivo vazio chamado `.sem-autoupdate` na pasta do programa, ou defina `EVE_TOOL_NO_UPDATE=1`.

### Personagens

Você pode conectar vários personagens: em **Configurações → Personagens conectados**, use **Adicionar personagem** e escolha o personagem na tela de login do EVE. Todos os personagens conectados são usados para achar citadelas e ler mercados privados.

Se o EVE recusar o login de um personagem (por exemplo, meses sem uso), ele aparece como **Login expirado** no checklist e em Configurações. Clique em **Entrar de novo** e escolha esse personagem. Para parar de usar um personagem, clique no ícone de desconectar.

---

## Funcionalidades

| Módulo | Descrição |
|--------|-----------|
| **Calculadora de Produção** | BOM recursivo, ME por item e por estrutura, bônus de estrutura, job cost (SCI + facility tax + SCC), taxas, lucro bruto e líquido |
| **Comparação de Preços no BOM** | Seleção de estrutura de manufatura por sub-componente: identifica o que vale importar ou fabricar em outra instalação |
| **Fila de Produção** | Jobs planejados com BOM agregado, lista de compras unificada com botão de cópia |
| **Ranking de Importação** | Itens com maior margem entre mercado fonte e local, com cálculo de frete |
| **Comparador de Lista** | Cola uma lista de itens e compara custo de importar vs comprar localmente |
| **Projeção de Mercado** | Histórico ESI com charts de volume e preço, projeção 7/14/30 dias |
| **Reprocessamento** | Calcula se vale reprocessar o item ou vendê-lo diretamente |
| **Estruturas de Manufatura** | Cadastro de Raitaru/Azbel/Sotiyo com bônus ME aplicado no cálculo |
| **Descoberta de Estruturas** | Escaneia assets de todos os personagens para encontrar citadelas acessíveis com mercado |
| **Mercados Privados** | Crawl automático a cada 15 min de ordens de estruturas Upwell |
| **Vários personagens** | Login via EVE SSO (PKCE), status de cada personagem e aviso de login expirado |
| **Primeiro uso automático** | Download de dados do jogo e preços com progresso, checklist de preparação |

---

## Problemas comuns

| Sintoma | O que fazer |
|---------|-------------|
| "Não foi possível baixar os dados do jogo" | Verifique a internet e clique em **Tentar de novo** no aviso, ou **Configurações → Importar SDE** |
| Personagem com **Login expirado** | **Configurações → Personagens conectados → Entrar de novo** |
| `Iniciar.bat` diz que não achou Python, mas você tem o 3.14 | A janela nativa ainda não suporta 3.14. Aceite instalar o 3.12 (fica lado a lado com o outro) |
| Quero voltar para uma versão anterior | Baixe o zip da versão em Releases, extraia por cima e crie `.sem-autoupdate` para ela não ser atualizada |
| Porta 8765 em uso | Feche outra instância do app que esteja aberta |
| Reprocessamento sem dados | Abra o app: ele detecta e reimporta sozinho |

---

## Instalação manual / desenvolvimento

Requer Python 3.11 a 3.13.

```bash
cd eve_industry_tool
pip install -r requirements.txt
python -m app.main                      # janela nativa
EVE_TOOL_NATIVE=0 python -m app.main    # no navegador
```

O SDE é importado automaticamente se o banco estiver vazio ou incompleto. Para reimportar: **Configurações → Importar SDE**, ou `python scripts/import_sde.py` (`--source fuzzwork` força o Fuzzwork, `--force-download` baixa de novo).

**Fim de linha:** o código usa LF; só o `Iniciar.bat` fica em CRLF (o Windows exige, e o `.gitattributes` garante isso). Se o editor converter arquivos para CRLF, volte para LF antes de commitar para não gerar diffs de arquivo inteiro.

**Releases:** usuários só recebem código novo quando uma GitHub Release é publicada (commit na `main` sozinho não chega a ninguém). O `VERSION` do repositório tem que ser igual à tag (`v1.2.0` → `1.2.0`), senão o `atualizar.py` recusa a instalação. Passo a passo em `.claude/skills/release/SKILL.md`.

**Notas de desenvolvimento** ficam em `.claude/context/`: `STATUS.md` (onde o projeto está), `TODO.md`, `MAP.md` (comandos e onde fica cada coisa), `LEARNINGS.md` (pegadinhas e decisões) e `BUGS.md` (bugs resolvidos).

### Usar a sua própria aplicação EVE (opcional)

O app já vem com o Client ID do projeto (`DEFAULT_EVE_CLIENT_ID` em `app/config.py`). Para usar outra aplicação, registre em [developers.eveonline.com](https://developers.eveonline.com) com callback `http://localhost:8765/auth/callback` e os escopos abaixo, e crie `eve_industry_tool/.env`:

```env
EVE_CLIENT_ID=seu_client_id
# Opcional: sem ele o login usa PKCE (recomendado para app desktop)
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

## Stack

| Camada | Tecnologia |
|--------|------------|
| GUI | NiceGUI + pywebview (janela nativa no Windows) |
| Backend | Python 3.11–3.13, SQLAlchemy async (aiosqlite) |
| Banco | SQLite (WAL mode) |
| Auth | EVE SSO (OAuth2 com PKCE) |
| Dados EVE | ESI API + SDE (Static Data Export via EVERef/Fuzzwork) |

## Arquitetura de dados

O app segue o padrão **cache-first com atualizações em background**:

- Todas as consultas leem do banco SQLite local (resposta imediata)
- Chamadas à ESI só ocorrem para atualizar o banco, nunca para responder ao usuário diretamente
- Downloads grandes (SDE, todas as ordens de Jita) rodam em background, sem bloquear a UI
- Scheduler interno: recrawl de estruturas a cada 15 min, limpeza de ordens a cada 1h, rediscovery a cada 6h

---

## Estrutura do Projeto

```
.
├── Iniciar.bat                    # Windows: instala o que faltar e abre o app
├── iniciar.sh                     # Linux: idem, abre no navegador
├── atualizar.py                   # Autoupdate pela última GitHub Release (chamado pelos launchers)
├── VERSION                        # Versão instalada (igual à tag da release)
├── .gitattributes                 # Fim de linha: .bat sempre CRLF, .sh sempre LF
├── .claude/                       # Só desenvolvimento (fora do zip das releases): context/ e skills/release
└── eve_industry_tool/
    ├── app/
    │   ├── main.py                # Entry point NiceGUI, scheduler, OAuth callback
    │   ├── config.py              # Configurações, Client ID padrão, SECRET_KEY automática
    │   ├── ui/                    # Páginas e componentes NiceGUI
    │   │   ├── auth_page.py       # Login EVE SSO
    │   │   ├── dashboard_page.py  # Dashboard + checklist de primeiros passos
    │   │   ├── items_page.py      # Browser de itens
    │   │   ├── industry_page.py   # Calculadora de produção + BOM recursivo
    │   │   ├── reprocessing_page.py
    │   │   ├── queue_page.py      # Fila de produção + lista de compras
    │   │   ├── ranking_page.py    # Ranking de importação + comparador de lista
    │   │   ├── ranking_item_page.py  # Projeção de mercado com charts
    │   │   ├── settings_page.py   # Configurações, personagens, estruturas de manufatura
    │   │   └── components/
    │   │       ├── setup_panel.py # Aviso de progresso + checklist do primeiro uso
    │   │       ├── bom_tree.py    # Árvore BOM expansível com ME e estação por nó
    │   │       ├── cost_breakdown.py
    │   │       ├── structure_selector.py
    │   │       └── price_chart.py # Charts ECharts
    │   ├── services/              # Lógica de negócio
    │   │   ├── esi_client.py      # Wrapper async da ESI API
    │   │   ├── sso.py             # URL de login EVE SSO com PKCE
    │   │   ├── first_run.py       # Primeiro uso: SDE + preços de Jita e checklist
    │   │   ├── market_service.py  # Cache de preços, refresh de mercado
    │   │   ├── industry_calculator.py
    │   │   ├── blueprint_service.py   # BOM recursivo com pré-carregamento em batch
    │   │   ├── crawler_service.py     # Crawl de mercados de estruturas
    │   │   ├── discovery_service.py   # Descoberta de estruturas via assets
    │   │   ├── job_runner.py          # Fila de jobs async com deduplicação
    │   │   ├── settings_service.py
    │   │   └── character_service.py  # Personagens, skills, renovação de token
    │   ├── models/                # ORM SQLAlchemy
    │   └── database/database.py   # Setup SQLite, migrations no startup
    ├── scripts/
    │   ├── import_sde.py          # Importação do SDE (EVERef ou Fuzzwork)
    │   ├── atualizar_estruturas.py
    │   ├── atualizar_precos_mercado.py
    │   └── ordens_null.py         # Ordens de estruturas nullsec
    ├── requirements.txt
    └── .env                       # Opcional: aplicação EVE própria (não versionado)
```

## Scripts Auxiliares

Usam os personagens já conectados no app.

```bash
cd eve_industry_tool
python scripts/atualizar_estruturas.py        # estruturas Upwell via ESI
python scripts/atualizar_precos_mercado.py    # preços de mercado
python scripts/ordens_null.py --listar        # estruturas nullsec
python scripts/ordens_null.py --id <structure_id>
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

Aplica-se por nó do BOM: cada sub-componente pode ter estrutura e ME independentes.

### Margem de Importação
```
Margem = preço_local × (1 - sales_tax - broker_fee) - preço_fonte - frete/un.
```

---

## Observações

- Todos os dados ficam locais: nada é enviado além da ESI e do SSO oficiais da CCP
- O banco (`database.db`) guarda os tokens de login dos personagens. **Não compartilhe nem versione** o banco, o `.env` ou o `.secret_key` (já estão no `.gitignore`)
- O banco é criado na primeira execução e as migrations de schema rodam no startup sem destruir dados
- A ESI não expõe rigs de estruturas; o cadastro de bônus ME é manual em Configurações
- Não afiliado à CCP Games
