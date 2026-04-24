"""
Settings page — /settings
Configure all application settings and manage manufacturing structures.
"""

import asyncio
import logging
import os
import secrets
import sys
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

from nicegui import ui, app as nicegui_app
from sqlalchemy import select, delete, func

_SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
_APP_DIR = Path(__file__).parent.parent.parent

from app.config import settings as app_settings
from app.database.database import AsyncSessionLocal
from app.models.user_settings import UserSettings
from app.models.manufacturing_structure import ManufacturingStructure
from app.models.structure import Structure
from app.models.market_snapshot import MarketSnapshot
from app.models.cache import MarketPriceCache
from app.models.job import DiscoveryJob
from app.services.character_service import get_market_options
from app.services.market_service import THE_FORGE_REGION_ID
from app.ui.layout import page_layout

logger = logging.getLogger(__name__)

SETTINGS_ID = 1

STRUCTURE_TYPES = [
    {"value": "raitaru",  "label": "Raitaru (Medium EC)"},
    {"value": "azbel",    "label": "Azbel (Large EC)"},
    {"value": "sotiyo",   "label": "Sotiyo (XL EC)"},
    {"value": "custom",   "label": "Outra / Personalizado"},
]

STATUS_LABELS = {
    "market_accessible": ("Acessível",     "positive"),
    "market_denied":     ("Acesso Negado", "negative"),
    "discovered":        ("Descoberta",    "warning"),
    "resolved":          ("Resolvida",     "info"),
    "inactive":          ("Inativa",       "dark"),
}


@ui.page("/settings")
async def settings_page():
    """Página de configurações."""
    # Carrega configurações atuais
    current = {
        "default_market_source":        "region:10000002",
        "default_me_level":             0,
        "default_system_cost_index":    0.05,
        "default_facility_tax":         0.0,
        "default_scc_surcharge":        0.015,
        "default_broker_fee_pct":       0.03,
        "default_sales_tax_pct":        0.08,
        "default_price_source":         "sell",
        "default_freight_cost_per_m3":  0.0,
    }

    market_options: dict[str, str] = {}

    try:
        async with AsyncSessionLocal() as db:
            res = await db.execute(select(UserSettings).where(UserSettings.id == SETTINGS_ID))
            row = res.scalar_one_or_none()
            if row:
                current.update({
                    "default_market_source":        row.default_market_source,
                    "default_me_level":             row.default_me_level,
                    "default_system_cost_index":    row.default_system_cost_index,
                    "default_facility_tax":         row.default_facility_tax,
                    "default_scc_surcharge":        row.default_scc_surcharge,
                    "default_broker_fee_pct":       row.default_broker_fee_pct,
                    "default_sales_tax_pct":        row.default_sales_tax_pct,
                    "default_price_source":         row.default_price_source,
                    "default_freight_cost_per_m3":  getattr(row, "default_freight_cost_per_m3", 0.0),
                })

            opts = await get_market_options(0, db)
            for group in opts["groups"]:
                for m in group["markets"]:
                    market_options[m["value"]] = m["label"]
            for m in opts.get("private", []):
                market_options[m["value"]] = m["label"]
    except Exception as exc:
        logger.error("Settings page load error: %s", exc)

    mfg_container = None

    async def save_settings():
        """Salva as configurações no banco."""
        try:
            async with AsyncSessionLocal() as db:
                res = await db.execute(select(UserSettings).where(UserSettings.id == SETTINGS_ID))
                row = res.scalar_one_or_none()

                new_data = {
                    "default_market_source":        market_select.value or "region:10000002",
                    "default_price_source":         price_src_select.value or "sell",
                    "default_me_level":             max(0, min(10, int(me_level_input.value or 0))),
                    "default_system_cost_index":    max(0, float(sci_input.value or 5)) / 100.0,
                    "default_facility_tax":         max(0, float(ft_input.value or 0)) / 100.0,
                    "default_scc_surcharge":        max(0, float(scc_input.value or 1.5)) / 100.0,
                    "default_broker_fee_pct":       max(0, float(broker_input.value or 3)) / 100.0,
                    "default_sales_tax_pct":        max(0, float(sales_tax_input.value or 8)) / 100.0,
                    "default_freight_cost_per_m3":  max(0, float(freight_input.value or 0)),
                    "updated_at":                   datetime.utcnow(),
                }

                if row is None:
                    db.add(UserSettings(id=SETTINGS_ID, **new_data))
                else:
                    for k, v in new_data.items():
                        setattr(row, k, v)

                await db.commit()
            ui.notify("Configurações salvas!", type="positive")
        except Exception as exc:
            logger.error("Save settings error: %s", exc)
            ui.notify(f"Erro ao salvar: {exc}", type="negative")

    with page_layout("Configurações"):
        ui.label("Configurações").classes("text-h5 text-white q-mb-md")

        # ── Seção: Conta do Personagem ────────────────────────────────────────
        with ui.card().classes("q-pa-md bg-grey-9 w-full q-mb-md"):
            with ui.row().classes("items-center gap-2 q-mb-sm"):
                ui.icon("person").classes("text-blue-grey-4")
                ui.label("Conta do Personagem").classes("text-subtitle1 text-white font-bold")

            character_name = nicegui_app.storage.general.get("character_name")

            _login_waiting = {"active": False}

            def _build_sso_url(state: str) -> str:
                params = {
                    "response_type": "code",
                    "redirect_uri":  app_settings.EVE_CALLBACK_URL,
                    "client_id":     app_settings.EVE_CLIENT_ID,
                    "scope":         app_settings.SSO_SCOPES,
                    "state":         state,
                }
                return f"{app_settings.SSO_BASE_URL}/v2/oauth/authorize?{urlencode(params)}"

            if character_name:
                with ui.row().classes("items-center gap-4 q-pa-sm bg-grey-8 rounded q-mb-sm"):
                    ui.icon("check_circle").classes("text-green-4 text-2xl")
                    with ui.column().classes("gap-0 flex-1"):
                        ui.label(character_name).classes("text-white font-bold")
                        ui.label("Autenticado via EVE SSO").classes("text-caption text-grey-5")

                    def do_logout():
                        for key in ("character_name", "character_id", "access_token"):
                            nicegui_app.storage.general.pop(key, None)
                        ui.navigate.to("/login")

                    ui.button("Logout", icon="logout", on_click=do_logout).props(
                        "unelevated color=negative size=sm"
                    )
            else:
                with ui.row().classes("items-center gap-4 q-pa-sm bg-grey-8 rounded q-mb-sm"):
                    ui.icon("cancel").classes("text-red-4 text-2xl")
                    with ui.column().classes("gap-0 flex-1"):
                        ui.label("Não autenticado").classes("text-grey-4 font-bold")
                        ui.label("Faça login com sua conta EVE Online").classes(
                            "text-caption text-grey-6"
                        )

                login_status = ui.label("").classes("text-caption text-yellow-5")
                login_spinner = ui.spinner("dots", size="sm", color="blue-grey")
                login_spinner.set_visibility(False)

                async def do_login_from_settings():
                    state = secrets.token_urlsafe(32)
                    nicegui_app.storage.general["oauth_state"] = state
                    sso_url = _build_sso_url(state)
                    webbrowser.open(sso_url)
                    login_status.set_text("Aguardando callback do EVE SSO...")
                    login_spinner.set_visibility(True)
                    _login_waiting["active"] = True

                def _check_login():
                    if _login_waiting["active"] and nicegui_app.storage.general.get("character_name"):
                        ui.navigate.to("/settings")

                ui.timer(1.0, _check_login)

                if not app_settings.EVE_CLIENT_ID:
                    ui.label(
                        "Configure EVE_CLIENT_ID e EVE_CLIENT_SECRET no .env para habilitar o login."
                    ).classes("text-caption text-orange-5 q-mb-xs")

                ui.button(
                    "Entrar com EVE Online",
                    icon="login",
                    on_click=do_login_from_settings,
                ).props("unelevated color=blue-grey-7")

        # ── Seção: Mercado ────────────────────────────────────────────────────
        with ui.expansion("Mercado", icon="store").classes(
            "w-full bg-grey-9 text-white q-mb-sm"
        ).props("default-opened"):
            with ui.grid(columns=2).classes("gap-3 q-pa-md w-full"):
                market_select = ui.select(
                    options=market_options,
                    value=current["default_market_source"],
                    label="Mercado Padrão",
                ).classes("w-full")
                market_select.props("outlined dense dark")

                price_src_select = ui.select(
                    options={"sell": "Menor Venda", "buy": "Maior Compra"},
                    value=current["default_price_source"],
                    label="Fonte de Preço Padrão",
                ).classes("w-full")
                price_src_select.props("outlined dense dark")

        # ── Seção: Taxas de Negociação ────────────────────────────────────────
        with ui.expansion("Taxas de Negociação", icon="percent").classes(
            "w-full bg-grey-9 text-white q-mb-sm"
        ):
            with ui.grid(columns=2).classes("gap-3 q-pa-md w-full"):
                broker_input = ui.number(
                    label="Broker Fee (%)",
                    value=current["default_broker_fee_pct"] * 100,
                    min=0, max=100, step=0.01,
                ).classes("w-full")
                broker_input.props("outlined dense dark")

                sales_tax_input = ui.number(
                    label="Sales Tax (%)",
                    value=current["default_sales_tax_pct"] * 100,
                    min=0, max=100, step=0.01,
                ).classes("w-full")
                sales_tax_input.props("outlined dense dark")

        # ── Seção: Produção ───────────────────────────────────────────────────
        with ui.expansion("Produção", icon="precision_manufacturing").classes(
            "w-full bg-grey-9 text-white q-mb-sm"
        ):
            with ui.grid(columns=2).classes("gap-3 q-pa-md w-full"):
                me_level_input = ui.number(
                    label="ME Level Padrão (0-10)",
                    value=current["default_me_level"],
                    min=0, max=10, step=1,
                ).classes("w-full")
                me_level_input.props("outlined dense dark")

                sci_input = ui.number(
                    label="Índice de Custo do Sistema (%)",
                    value=current["default_system_cost_index"] * 100,
                    min=0, max=100, step=0.01,
                ).classes("w-full")
                sci_input.props("outlined dense dark")

                ft_input = ui.number(
                    label="Taxa da Instalação (%)",
                    value=current["default_facility_tax"] * 100,
                    min=0, max=100, step=0.01,
                ).classes("w-full")
                ft_input.props("outlined dense dark")

                scc_input = ui.number(
                    label="SCC Surcharge (%)",
                    value=current["default_scc_surcharge"] * 100,
                    min=0, max=100, step=0.01,
                ).classes("w-full")
                scc_input.props("outlined dense dark")

        # ── Seção: Frete ──────────────────────────────────────────────────────
        with ui.expansion("Frete", icon="local_shipping").classes(
            "w-full bg-grey-9 text-white q-mb-sm"
        ):
            with ui.column().classes("q-pa-md gap-2 w-full"):
                freight_input = ui.number(
                    label="Custo de Frete por m³ (ISK)",
                    value=current["default_freight_cost_per_m3"],
                    min=0,
                ).classes("w-full max-w-xs")
                freight_input.props("outlined dense dark")

        # Botão Salvar
        with ui.row().classes("q-mt-md gap-2"):
            ui.button("Salvar Configurações", icon="save", on_click=save_settings).props(
                "unelevated color=positive"
            )

        # ── Seção: Dados e Atualizações ───────────────────────────────────────
        with ui.card().classes("q-pa-md bg-grey-9 w-full q-mt-lg"):
            with ui.row().classes("items-center gap-2 q-mb-sm"):
                ui.icon("storage").classes("text-blue-grey-4")
                ui.label("Dados e Atualizações").classes("text-subtitle1 text-white font-bold")

            # Log de output (user-select permite selecionar e copiar o texto)
            ui.add_css("""
                nicegui-log { user-select: text !important; cursor: text !important; }
                nicegui-log * { user-select: text !important; }
            """)
            script_log = ui.log(max_lines=300).classes(
                "w-full bg-grey-10 text-green-4 text-xs font-mono q-mb-sm"
            ).style("height: 180px; border: 1px solid #444; user-select: text; cursor: text;")

            status_label = ui.label("").classes("text-yellow-5 text-xs q-mb-sm")

            _state = {"running": False}

            async def _run_script(script: str, args: list, label: str, btns: list):
                if _state["running"]:
                    ui.notify("Aguarde a tarefa atual terminar.", type="warning")
                    return
                _state["running"] = True
                for b in btns:
                    b.disable()
                status_label.set_text(f"⏳ Executando: {label}…")
                script_log.clear()
                script_log.push(f">>> {label}")
                script_log.push("─" * 60)
                try:
                    proc = await asyncio.create_subprocess_exec(
                        sys.executable, "-X", "utf8",
                        str(_SCRIPTS_DIR / script),
                        *args,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.STDOUT,
                        cwd=str(_APP_DIR),
                        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                    )
                    async for raw in proc.stdout:
                        script_log.push(raw.decode("utf-8", errors="replace").rstrip())
                    rc = await proc.wait()
                    script_log.push("─" * 60)
                    if rc == 0:
                        script_log.push("✓ Concluído com sucesso.")
                        ui.notify(f"{label} concluído!", type="positive")
                        status_label.set_text("")
                    else:
                        script_log.push(f"✗ Encerrado com código {rc}.")
                        ui.notify(f"Erro em {label} (código {rc}).", type="negative")
                        status_label.set_text(f"✗ Falha: {label}")
                except Exception as exc:
                    script_log.push(f"Erro interno: {exc}")
                    ui.notify(str(exc), type="negative")
                    status_label.set_text("✗ Erro interno.")
                finally:
                    _state["running"] = False
                    for b in btns:
                        b.enable()

            # ── Subseção: Banco de dados (SDE) ────────────────────────────────
            ui.label("Banco de dados (SDE)").classes("text-caption text-grey-4 text-bold q-mt-xs")
            ui.label(
                "Importa itens, blueprints e materiais do jogo. Execute uma vez na instalação "
                "e sempre que houver atualização do EVE."
            ).classes("text-caption text-grey-6 q-mb-xs")
            with ui.row().classes("gap-2 flex-wrap q-mb-md"):
                btn_sde = ui.button("Importar SDE", icon="download_for_offline").props(
                    "unelevated color=primary dense"
                ).tooltip("Baixa EVERef (~13 MB) e importa. Usa cache se já baixado.")
                btn_sde_force = ui.button("Re-baixar SDE", icon="refresh").props(
                    "unelevated color=secondary dense"
                ).tooltip("Força novo download mesmo com cache existente.")
                btn_sde_fuzzwork = ui.button("Usar Fuzzwork", icon="cloud_download").props(
                    "unelevated color=deep-orange dense"
                ).tooltip("Usa Fuzzwork (~130 MB) como fonte — inclui dados de reprocessamento.")

            # ── Subseção: Estruturas e preços ─────────────────────────────────
            ui.label("Estruturas e preços de mercado").classes("text-caption text-grey-4 text-bold")
            ui.label(
                "Descobre mercados privados via ESI. Requer ao menos um personagem logado."
            ).classes("text-caption text-grey-6 q-mb-xs")

            with ui.row().classes("gap-2 items-center q-mb-xs flex-wrap"):
                fonte_select = ui.select(
                    options={
                        "ambos":    "Todas as fontes (Corp + Universo + Assets)",
                        "corp":     "Corporação — estruturas que a corp possui",
                        "universo": "Universo — estruturas onde já usou o mercado",
                        "assets":   "Assets pessoais — bom para null-sec",
                    },
                    value="ambos",
                    label="Fonte de descoberta",
                ).classes("w-72")
                fonte_select.props("outlined dense dark")

            with ui.row().classes("gap-2 flex-wrap"):
                btn_structs = ui.button("Atualizar Estruturas", icon="cell_tower").props(
                    "unelevated color=teal dense"
                ).tooltip("Busca e salva estruturas com mercado acessível.")
                btn_precos = ui.button("Atualizar Preços", icon="price_change").props(
                    "unelevated color=cyan dense"
                ).tooltip("Atualiza apenas o cache de preços das estruturas já conhecidas.")
                btn_structs_limpar = ui.button("Limpar e Reimportar", icon="delete_sweep").props(
                    "unelevated color=negative dense"
                ).tooltip("Remove todas as estruturas do banco e reimporta do zero.")

            all_btns = [btn_sde, btn_sde_force, btn_sde_fuzzwork,
                        btn_structs, btn_precos, btn_structs_limpar]

            btn_sde.on_click(
                lambda: _run_script("import_sde.py", [], "Importar SDE", all_btns)
            )
            btn_sde_force.on_click(
                lambda: _run_script("import_sde.py", ["--force-download"], "Re-baixar SDE", all_btns)
            )
            btn_sde_fuzzwork.on_click(
                lambda: _run_script("import_sde.py", ["--force-download", "--source", "fuzzwork"], "Importar SDE via Fuzzwork", all_btns)
            )
            btn_structs.on_click(
                lambda: _run_script(
                    "atualizar_estruturas.py",
                    ["--so-estruturas", "--fonte", fonte_select.value],
                    f"Atualizar Estruturas ({fonte_select.value})",
                    all_btns,
                )
            )
            btn_precos.on_click(
                lambda: _run_script("atualizar_precos_mercado.py", [], "Atualizar Preços", all_btns)
            )
            btn_structs_limpar.on_click(
                lambda: _run_script(
                    "atualizar_estruturas.py",
                    ["--so-estruturas", "--limpar", "--fonte", fonte_select.value],
                    f"Limpar e Reimportar Estruturas ({fonte_select.value})",
                    all_btns,
                )
            )

        # ── Seção: Estruturas e Mercado ───────────────────────────────────────
        with ui.card().classes("q-pa-md bg-grey-9 w-full q-mt-lg"):
            with ui.row().classes("items-center gap-2 q-mb-sm"):
                ui.icon("location_city").classes("text-blue-grey-4")
                ui.label("Estruturas e Mercado").classes("text-subtitle1 text-white font-bold")

                async def _refresh_market_card():
                    market_stats_row.clear()
                    await _render_market_stats(market_stats_row)
                    market_structs_col.clear()
                    await _render_market_structures(market_structs_col)
                    hist_col.clear()
                    await _render_discovery_history(hist_col)
                    ui.notify("Atualizado.", type="positive")

                ui.button(
                    icon="refresh", on_click=_refresh_market_card
                ).props("flat round dense color=grey-5").classes("q-ml-auto")

            # Stats
            market_stats_row = ui.row().classes("gap-3 q-mb-md flex-wrap")
            await _render_market_stats(market_stats_row)

            # Descoberta via Assets (job interno — não requer scripts externos)
            character_id = nicegui_app.storage.general.get("character_id")
            with ui.row().classes("items-center gap-3 q-mb-md flex-wrap"):
                disc_spinner = ui.spinner("dots", size="sm", color="primary")
                disc_spinner.set_visibility(False)
                disc_status = ui.label("").classes("text-caption text-grey-5")

                async def _start_asset_discovery():
                    cid = nicegui_app.storage.general.get("character_id")
                    if not cid:
                        ui.notify("Faça login antes de usar esta função.", type="warning")
                        return
                    disc_spinner.set_visibility(True)
                    disc_status.set_text("Enfileirando discovery via assets…")
                    try:
                        async with AsyncSessionLocal() as db:
                            from app.services.discovery_service import enqueue_asset_discovery
                            job_id = await enqueue_asset_discovery(int(cid), db)
                            await db.commit()
                        disc_status.set_text(f"Job #{job_id} enfileirado. Aguardando…")
                        ui.notify(f"Discovery enfileirado (job #{job_id}).", type="positive")
                        await asyncio.sleep(2)
                        hist_col.clear()
                        await _render_discovery_history(hist_col)
                    except Exception as exc:
                        logger.error("Discovery error: %s", exc)
                        ui.notify(f"Erro: {exc}", type="negative")
                        disc_status.set_text(f"Erro: {exc}")
                    finally:
                        disc_spinner.set_visibility(False)

                if character_id:
                    ui.button(
                        "Descobrir via Assets", icon="search",
                        on_click=_start_asset_discovery,
                    ).props("unelevated color=primary dense").tooltip(
                        "Analisa assets do personagem para encontrar estruturas Upwell no banco interno."
                    )
                else:
                    ui.label("Faça login para usar Descoberta via Assets.").classes("text-caption text-orange-5")

            # Tabela de estruturas por status
            market_structs_col = ui.column().classes("w-full")
            await _render_market_structures(market_structs_col)

            # Histórico de jobs (expansível)
            with ui.expansion("Histórico de Discovery", icon="history").classes(
                "w-full bg-grey-8 text-white q-mt-sm"
            ):
                hist_col = ui.column().classes("w-full")
                await _render_discovery_history(hist_col)

        # ── Seção: Estruturas de Manufatura ───────────────────────────────────
        with ui.card().classes("q-pa-md bg-grey-9 w-full q-mt-lg"):
            with ui.row().classes("items-center gap-2 q-mb-md"):
                ui.icon("factory").classes("text-blue-grey-4")
                ui.label("Estruturas de Manufatura").classes(
                    "text-subtitle1 text-white font-bold"
                )
                ui.button(
                    "Adicionar",
                    icon="add",
                    on_click=lambda: show_add_struct_dialog(),
                ).props("unelevated color=primary dense").classes("q-ml-auto")

            mfg_container = ui.column().classes("w-full")
            await _render_mfg_structures(mfg_container)

    async def show_add_struct_dialog():
        """Diálogo para adicionar estrutura de manufatura."""
        struct_type_options = {t["value"]: t["label"] for t in STRUCTURE_TYPES}

        with ui.dialog() as dialog, ui.card().classes("q-pa-md bg-grey-9 min-w-80"):
            ui.label("Nova Estrutura de Manufatura").classes("text-h6 text-white q-mb-md")

            name_input = ui.input(label="Nome", placeholder="ex: Minha Raitaru").classes("w-full")
            name_input.props("outlined dense dark")

            stype_select = ui.select(
                options=struct_type_options,
                value="raitaru",
                label="Tipo",
            ).classes("w-full")
            stype_select.props("outlined dense dark")

            me_input = ui.number(label="Bônus ME (%)", value=0.0, min=0, max=100, step=0.1).classes("w-full")
            me_input.props("outlined dense dark")

            async def add_struct():
                name = (name_input.value or "").strip()
                if not name:
                    ui.notify("Nome é obrigatório.", type="warning")
                    return
                try:
                    async with AsyncSessionLocal() as db:
                        db.add(ManufacturingStructure(
                            name=name,
                            structure_type=stype_select.value or "custom",
                            me_bonus=max(0.0, min(100.0, float(me_input.value or 0))),
                            created_at=datetime.utcnow(),
                        ))
                        await db.commit()
                    ui.notify(f"'{name}' adicionada.", type="positive")
                    dialog.close()
                    mfg_container.clear()
                    await _render_mfg_structures(mfg_container)
                except Exception as exc:
                    ui.notify(f"Erro: {exc}", type="negative")

            with ui.row().classes("gap-2 q-mt-md justify-end"):
                ui.button("Cancelar", on_click=dialog.close).props("flat color=grey-5")
                ui.button("Adicionar", on_click=add_struct).props("unelevated color=primary")

        dialog.open()


async def _render_mfg_structures(container: ui.column):
    """Renderiza a tabela de estruturas de manufatura."""
    try:
        async with AsyncSessionLocal() as db:
            res = await db.execute(
                select(ManufacturingStructure).order_by(ManufacturingStructure.name)
            )
            structures = res.scalars().all()
    except Exception as exc:
        logger.error("MFG structures error: %s", exc)
        with container:
            ui.notify(f"Erro: {exc}", type="negative")
        return

    with container:
        if not structures:
            ui.label("Nenhuma estrutura cadastrada.").classes("text-grey-6 q-pa-sm")
            return

        columns = [
            {"name": "name",           "label": "Nome",   "field": "name",           "align": "left"},
            {"name": "structure_type", "label": "Tipo",   "field": "structure_type", "align": "left"},
            {"name": "me_bonus",       "label": "ME %",   "field": "me_bonus",       "align": "right"},
            {"name": "actions",        "label": "",       "field": "actions",        "align": "center"},
        ]

        rows = [
            {
                "id":             s.id,
                "name":           s.name,
                "structure_type": s.structure_type,
                "me_bonus":       f"{s.me_bonus:.1f}%",
                "me_bonus_raw":   s.me_bonus,
            }
            for s in structures
        ]

        table = ui.table(columns=columns, rows=rows, row_key="id").props(
            "dark flat bordered dense"
        ).classes("w-full text-grey-3")

        table.add_slot("body-cell-actions", """
            <q-td :props="props">
                <q-btn flat round dense icon="edit" color="blue-grey-4"
                       @click="$emit('edit_struct', props.row)"
                       title="Editar" />
                <q-btn flat round dense icon="delete" color="red-5"
                       @click="$emit('delete_struct', props.row)"
                       title="Remover" />
            </q-td>
        """)

        struct_type_options = {t["value"]: t["label"] for t in STRUCTURE_TYPES}

        async def edit_struct(e):
            row = e.args
            struct_id   = row.get("id")
            struct_name = row.get("name", "")
            struct_type = row.get("structure_type", "raitaru")
            me_raw      = float(row.get("me_bonus_raw", 0))

            with ui.dialog() as dialog, ui.card().classes("q-pa-md bg-grey-9 min-w-80"):
                ui.label("Editar Estrutura de Manufatura").classes("text-h6 text-white q-mb-md")

                name_input = ui.input(label="Nome", value=struct_name).classes("w-full")
                name_input.props("outlined dense dark")

                stype_select = ui.select(
                    options=struct_type_options,
                    value=struct_type,
                    label="Tipo",
                ).classes("w-full")
                stype_select.props("outlined dense dark")

                me_input = ui.number(
                    label="Bônus ME (%)", value=me_raw, min=0, max=100, step=0.1
                ).classes("w-full")
                me_input.props("outlined dense dark")

                async def save_edit():
                    name = (name_input.value or "").strip()
                    if not name:
                        ui.notify("Nome é obrigatório.", type="warning")
                        return
                    try:
                        async with AsyncSessionLocal() as db:
                            res = await db.execute(
                                select(ManufacturingStructure).where(
                                    ManufacturingStructure.id == struct_id
                                )
                            )
                            s = res.scalar_one_or_none()
                            if s:
                                s.name           = name
                                s.structure_type = stype_select.value or "custom"
                                s.me_bonus       = max(0.0, min(100.0, float(me_input.value or 0)))
                                await db.commit()
                        ui.notify(f"'{name}' atualizada.", type="positive")
                        dialog.close()
                        container.clear()
                        await _render_mfg_structures(container)
                    except Exception as exc:
                        ui.notify(f"Erro: {exc}", type="negative")

                with ui.row().classes("gap-2 q-mt-md justify-end"):
                    ui.button("Cancelar", on_click=dialog.close).props("flat color=grey-5")
                    ui.button("Salvar", on_click=save_edit).props("unelevated color=primary")

            dialog.open()

        async def delete_struct(e):
            struct_id = e.args.get("id")
            if struct_id:
                try:
                    async with AsyncSessionLocal() as db:
                        await db.execute(
                            delete(ManufacturingStructure).where(
                                ManufacturingStructure.id == struct_id
                            )
                        )
                        await db.commit()
                    ui.notify("Estrutura removida.", type="positive")
                    container.clear()
                    await _render_mfg_structures(container)
                except Exception as exc:
                    ui.notify(f"Erro: {exc}", type="negative")

        table.on("edit_struct", edit_struct)
        table.on("delete_struct", delete_struct)


async def _render_market_stats(container):
    """Renderiza cards de estatísticas do mercado."""
    try:
        async with AsyncSessionLocal() as db:
            total_structs = (await db.execute(
                select(func.count()).select_from(Structure)
            )).scalar_one() or 0

            accessible = (await db.execute(
                select(func.count()).select_from(Structure).where(
                    Structure.status == "market_accessible"
                )
            )).scalar_one() or 0

            total_snapshots = (await db.execute(
                select(func.count()).select_from(MarketSnapshot)
            )).scalar_one() or 0

            cache_entries = (await db.execute(
                select(func.count()).select_from(MarketPriceCache).where(
                    MarketPriceCache.market_type == "region",
                    MarketPriceCache.market_id == THE_FORGE_REGION_ID,
                )
            )).scalar_one() or 0
    except Exception as exc:
        logger.error("Market stats error: %s", exc)
        total_structs = accessible = total_snapshots = cache_entries = 0

    def _stat(title, value, icon, color):
        with ui.card().classes(f"q-pa-sm bg-{color} text-white shadow-2 min-w-28"):
            with ui.row().classes("items-center gap-2"):
                ui.icon(icon).classes("text-2xl opacity-80")
                with ui.column().classes("gap-0"):
                    ui.label(str(value)).classes("text-h6 font-bold")
                    ui.label(title).classes("text-caption opacity-80")

    with container:
        _stat("Estruturas",      total_structs,   "location_city", "blue-grey-7")
        _stat("Acessíveis",      accessible,      "store",         "green-7")
        _stat("Snapshots",       total_snapshots, "analytics",     "blue-7")
        _stat("Cache Jita",      cache_entries,   "cached",        "orange-7")


async def _render_market_structures(container):
    """Renderiza estruturas agrupadas por status com botão de force-crawl."""
    try:
        async with AsyncSessionLocal() as db:
            structs_res = await db.execute(
                select(Structure).order_by(Structure.status.asc(), Structure.name.asc())
            )
            all_structures = structs_res.scalars().all()

            snap_counts_res = await db.execute(
                select(
                    MarketSnapshot.structure_id,
                    func.count(MarketSnapshot.type_id).label("n"),
                ).group_by(MarketSnapshot.structure_id)
            )
            snap_counts = {row.structure_id: row.n for row in snap_counts_res.all()}
    except Exception as exc:
        logger.error("Market structures error: %s", exc)
        with container:
            ui.label(f"Erro ao carregar estruturas: {exc}").classes("text-orange-5")
        return

    with container:
        if not all_structures:
            ui.label(
                "Nenhuma estrutura descoberta. Use 'Descobrir via Assets' ou 'Atualizar Estruturas'."
            ).classes("text-grey-5 q-pa-sm")
            return

        by_status: dict[str, list] = {}
        for s in all_structures:
            by_status.setdefault(s.status, []).append(s)

        for status, structs in by_status.items():
            label, color = STATUS_LABELS.get(status, (status, "grey"))
            with ui.expansion(
                f"{label} ({len(structs)})", icon="location_city",
            ).classes(f"w-full bg-grey-8 text-{color}-4 q-mb-xs"):
                columns = [
                    {"name": "name",         "label": "Nome",         "field": "name",         "align": "left"},
                    {"name": "system",       "label": "Sistema",      "field": "system",       "align": "left"},
                    {"name": "last_crawled", "label": "Último Crawl", "field": "last_crawled", "align": "left"},
                    {"name": "snapshots",    "label": "Snapshots",    "field": "snapshots",    "align": "right"},
                    {"name": "actions",      "label": "",             "field": "actions",      "align": "center"},
                ]
                rows = [
                    {
                        "structure_id": s.structure_id,
                        "name":         s.name or f"Structure {s.structure_id}",
                        "system":       s.system_name or "?",
                        "last_crawled": s.last_crawled_at.strftime("%d/%m %H:%M") if s.last_crawled_at else "Nunca",
                        "snapshots":    snap_counts.get(s.structure_id, 0),
                    }
                    for s in structs
                ]
                table = ui.table(
                    columns=columns, rows=rows, row_key="structure_id"
                ).props("dark flat bordered dense").classes("w-full text-grey-3")

                table.add_slot("body-cell-actions", """
                    <q-td :props="props">
                        <q-btn flat round dense icon="refresh" color="blue-grey-5"
                               @click="$emit('crawl', props.row)" title="Forçar Crawl" />
                    </q-td>
                """)

                async def _trigger_crawl(e):
                    struct_id = e.args.get("structure_id")
                    if struct_id:
                        try:
                            from app.services.discovery_service import _crawl_market_job
                            from app.services.job_runner import crawl_runner
                            char_id = nicegui_app.storage.general.get("character_id") or 0
                            await crawl_runner.enqueue(
                                f"crawl:{struct_id}", _crawl_market_job,
                                int(struct_id), int(char_id),
                            )
                            ui.notify(f"Crawl enfileirado para {struct_id}.", type="positive")
                        except Exception as exc:
                            ui.notify(f"Erro: {exc}", type="negative")

                table.on("crawl", _trigger_crawl)


async def _render_discovery_history(container):
    """Renderiza o histórico de jobs de discovery."""
    try:
        async with AsyncSessionLocal() as db:
            res = await db.execute(
                select(DiscoveryJob).order_by(DiscoveryJob.created_at.desc()).limit(20)
            )
            jobs = res.scalars().all()
    except Exception as exc:
        logger.error("Discovery history error: %s", exc)
        with container:
            ui.label(f"Erro: {exc}").classes("text-orange-5")
        return

    with container:
        if not jobs:
            ui.label("Nenhum job executado ainda.").classes("text-grey-6 q-pa-sm")
            return

        columns = [
            {"name": "created_at",       "label": "Data",        "field": "created_at",       "align": "left"},
            {"name": "source",           "label": "Fonte",       "field": "source",           "align": "left"},
            {"name": "status",           "label": "Status",      "field": "status",           "align": "center"},
            {"name": "structures_found", "label": "Encontradas", "field": "structures_found", "align": "right"},
        ]
        rows = [
            {
                "created_at":       j.created_at.strftime("%d/%m %H:%M") if j.created_at else "?",
                "source":           j.source or "?",
                "status":           j.status or "?",
                "structures_found": j.structures_found or 0,
            }
            for j in jobs
        ]
        table = ui.table(columns=columns, rows=rows, row_key="created_at").props(
            "dark flat bordered dense"
        ).classes("w-full text-grey-3")

        table.add_slot("body-cell-status", """
            <q-td :props="props">
                <q-badge
                    :color="props.row.status === 'done'    ? 'positive'
                           : props.row.status === 'failed'  ? 'negative'
                           : props.row.status === 'running' ? 'info'
                           : 'warning'"
                    :label="props.row.status" />
            </q-td>
        """)
