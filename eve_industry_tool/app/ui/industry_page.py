"""
Industry calculation page — /industry
Calculate production cost, profit and BOM for EVE items.
"""

import asyncio
import json
import logging
from datetime import datetime

from nicegui import ui, app as nicegui_app
from sqlalchemy import select

from app.database.database import AsyncSessionLocal
from app.models.item import Item
from app.models.manufacturing_structure import ManufacturingStructure
from app.models.production_queue import ProductionQueue
from app.services.blueprint_service import (
    get_blueprint_by_product,
    get_blueprint_materials,
    get_recursive_bom,
    aggregate_bom_leaves,
    enrich_bom_costs,
)
from app.services.market_service import (
    get_prices_cache_only,
    get_volumes_cache_only,
    refresh_prices_for_types,
    refresh_region_market_prices,
)
from app.services.industry_calculator import Material, calculate_production_cost, calculate_profit
from app.services.character_service import get_character, get_fresh_token, get_market_options
from app.services.esi_client import esi_client, ESIError
from app.services.settings_service import load_settings
from app.ui.layout import page_layout

logger = logging.getLogger(__name__)


@ui.page("/industry")
async def industry_page(type_id: int = 0, queue_id: int = 0):
    """Página de cálculo de indústria."""
    # Carrega entrada da fila se queue_id fornecido
    queue_entry = None
    queue_item_name = ""
    if queue_id:
        try:
            async with AsyncSessionLocal() as db:
                res = await db.execute(
                    select(ProductionQueue).where(ProductionQueue.id == queue_id)
                )
                queue_entry = res.scalar_one_or_none()
                if queue_entry:
                    type_id = queue_entry.item_type_id
                    item_res = await db.execute(
                        select(Item).where(Item.type_id == type_id)
                    )
                    item_obj = item_res.scalar_one_or_none()
                    if item_obj:
                        queue_item_name = item_obj.type_name
        except Exception as exc:
            logger.error("Load queue entry error: %s", exc)

    # Estado da página
    state = {
        "type_id":                  type_id,
        "runs":                     1,
        "me_level":                 0,
        "structure_me_bonus":       0.0,
        "market_source":            "region:10000002",
        "price_source":             "sell",
        "recursive":                False,
        "manufacturing_struct_id":  0,
        "system_cost_index":        0.05,
        "facility_tax":             0.0,
        "scc_surcharge":            0.015,
        "broker_fee_pct":           0.03,
        "sales_tax_pct":            0.08,
        "me_overrides":             {},
        "station_overrides":        {},
    }

    # Estado persistente da sessão
    buy_as_is_ids: set[int] = set()
    # Inicializado com type_id já resolvido para não disparar reset ao carregar da fila
    last_item_type_id: list[int] = [type_id]

    result_container = None
    mfg_structs: list = []
    default_market = "region:10000002"
    market_options: dict[str, str] = {}

    try:
        async with AsyncSessionLocal() as db:
            s = await load_settings(db)
            state["me_level"]           = s.get("default_me_level", 0)
            state["market_source"]      = s.get("default_market_source", "region:10000002")
            state["price_source"]       = s.get("default_price_source", "sell")
            state["system_cost_index"]  = s.get("default_system_cost_index", 0.05)
            state["facility_tax"]       = s.get("default_facility_tax", 0.0)
            state["scc_surcharge"]      = s.get("default_scc_surcharge", 0.015)
            state["broker_fee_pct"]     = s.get("default_broker_fee_pct", 0.03)
            state["sales_tax_pct"]      = s.get("default_sales_tax_pct", 0.08)
            state["structure_me_bonus"] = s.get("default_structure_me_bonus", 0.0)
            default_market = state["market_source"]

            res = await db.execute(
                select(ManufacturingStructure).order_by(ManufacturingStructure.name)
            )
            mfg_structs = res.scalars().all()

            opts = await get_market_options(0, db)
            for group in opts["groups"]:
                for m in group["markets"]:
                    market_options[m["value"]] = m["label"]
            for m in opts.get("private", []):
                market_options[m["value"]] = m["label"]
    except Exception as exc:
        logger.error("Industry page load error: %s", exc)

    # Restaura configuração da fila (sobrepõe defaults)
    if queue_entry:
        state["runs"]                   = queue_entry.quantity or 1
        state["me_level"]               = queue_entry.me_level or 0
        state["structure_me_bonus"]     = queue_entry.structure_me_bonus or 0.0
        state["manufacturing_struct_id"]= queue_entry.manufacturing_struct_id or 0
        state["me_overrides"]           = queue_entry.get_me_overrides()
        state["station_overrides"]      = queue_entry.get_station_overrides()
        buy_as_is_ids                   = set(queue_entry.get_buy_as_is())
        if queue_entry.market_source and queue_entry.market_source in market_options:
            state["market_source"] = queue_entry.market_source
        # Modo recursivo sempre ativo ao restaurar (BOM overrides só fazem sentido no modo recursivo)
        state["recursive"] = True

    # Mapa de estruturas para o select
    struct_options = {0: "Nenhuma (usar bônus global)"}
    for s in mfg_structs:
        struct_options[s.id] = f"{s.name} (ME {s.me_bonus:.1f}%)"

    # Garante que default_market é uma opção válida (evita ValueError no ui.select)
    if default_market not in market_options:
        default_market = "region:10000002"

    with page_layout("Calculadora de Indústria"):
        ui.label("Calculadora de Indústria").classes("text-h5 text-white q-mb-md")

        # type_id resolvido pelo campo de texto (usado para priorizar fila)
        _item_found = {"type_id": type_id}

        with ui.row().classes("gap-4 w-full items-start flex-nowrap"):

            # ── Formulário (sticky) ───────────────────────────────────────────
            with ui.element("div").style(
                "position: sticky; top: 16px; flex: 0 0 320px; min-width: 280px;"
                "max-height: calc(100vh - 100px); overflow-y: auto;"
            ):
                with ui.card().classes("q-pa-md bg-grey-9 w-full"):
                    ui.label("Parâmetros").classes("text-subtitle1 text-white q-mb-sm font-bold")

                    # ── Campo de item ─────────────────────────────────────────
                    item_input = ui.input(
                        label="Item (nome ou type_id)",
                        placeholder="ex: Tritanium ou 34",
                        value=queue_item_name if queue_item_name else (str(type_id) if type_id else ""),
                    ).classes("w-full")
                    item_input.props("outlined dense dark clearable")
                    item_input.on_value_change(lambda _: _item_found.update({"type_id": 0}))

                    # ── Runs + ME Level ───────────────────────────────────────
                    with ui.grid(columns=2).classes("gap-2 w-full q-mt-sm"):
                        runs_input = ui.number(
                            label="Runs", value=state["runs"], min=1, max=100000,
                        ).classes("w-full")
                        runs_input.props("outlined dense dark")

                        me_input = ui.number(
                            label="ME Level (0-10)",
                            value=state["me_level"],
                            min=0, max=10, step=1,
                        ).classes("w-full")
                        me_input.props("outlined dense dark")

                    # ── Estrutura + Mercado ───────────────────────────────────
                    with ui.grid(columns=2).classes("gap-2 w-full"):
                        struct_select = ui.select(
                            options=struct_options,
                            value=state["manufacturing_struct_id"],
                            label="Estrutura",
                        ).classes("w-full")
                        struct_select.props("outlined dense dark")

                        market_select = ui.select(
                            options=market_options,
                            value=state["market_source"] if state["market_source"] in market_options else default_market,
                            label="Mercado",
                        ).classes("w-full")
                        market_select.props("outlined dense dark")

                    # ── Fonte de preço + BOM mode ─────────────────────────────
                    with ui.grid(columns=2).classes("gap-2 w-full"):
                        price_source_select = ui.select(
                            options={"sell": "Menor Venda", "buy": "Maior Compra"},
                            value=state["price_source"],
                            label="Fonte de Preço",
                        ).classes("w-full")
                        price_source_select.props("outlined dense dark")

                        recursive_select = ui.select(
                            options={"false": "BOM Simples", "true": "BOM Recursivo"},
                            value="true" if state["recursive"] else "false",
                            label="Modo BOM",
                        ).classes("w-full")
                        recursive_select.props("outlined dense dark")

                    # ── Taxas e Índices (expansão) ────────────────────────────
                    with ui.expansion("Taxas e Índices", icon="tune").classes(
                        "w-full text-grey-4 q-mt-xs"
                    ):
                        with ui.grid(columns=2).classes("gap-2 w-full"):
                            sci_input = ui.number(
                                label="Custo Sistema (%)",
                                value=state["system_cost_index"] * 100,
                                min=0, max=100, step=0.01,
                            ).classes("w-full")
                            sci_input.props("outlined dense dark")

                            ft_input = ui.number(
                                label="Taxa Instalação (%)",
                                value=state["facility_tax"] * 100,
                                min=0, max=100, step=0.01,
                            ).classes("w-full")
                            ft_input.props("outlined dense dark")

                            scc_input = ui.number(
                                label="SCC Surcharge (%)",
                                value=state["scc_surcharge"] * 100,
                                min=0, max=100, step=0.01,
                            ).classes("w-full")
                            scc_input.props("outlined dense dark")

                            bf_input = ui.number(
                                label="Broker Fee (%)",
                                value=state["broker_fee_pct"] * 100,
                                min=0, max=100, step=0.01,
                            ).classes("w-full")
                            bf_input.props("outlined dense dark")

                            st_input = ui.number(
                                label="Sales Tax (%)",
                                value=state["sales_tax_pct"] * 100,
                                min=0, max=100, step=0.01,
                            ).classes("w-full")
                            st_input.props("outlined dense dark")

                    inventory_toggle = ui.checkbox(
                        "Descontar inventário do personagem",
                    ).classes("q-mt-sm text-grey-4")

                    with ui.row().classes("gap-2 q-mt-md"):
                        calc_btn = ui.button(
                            "Calcular",
                            icon="calculate",
                            on_click=lambda: do_calculate(),
                        ).props("unelevated color=primary")

                        ui.button(
                            "Atualizar Preços",
                            icon="refresh",
                            on_click=lambda: do_calculate(force_refresh=True),
                        ).props("flat color=grey-5")

            # ── Resultado ─────────────────────────────────────────────────────
            result_container = ui.column().classes("gap-3").style("flex: 1; min-width: 0;")
            with result_container:
                ui.label("Preencha o formulário e clique em Calcular.").classes("text-grey-6 q-pa-md")

        async def do_calculate(force_refresh: bool = False):
            result_container.clear()
            await asyncio.sleep(0)  # yield: deixa o drawer sincronizar via JS

            # Coleta valores do formulário
            raw_item = (item_input.value or "").strip()
            if not raw_item:
                ui.notify("Informe o nome ou type_id do item.", type="warning")
                return

            def _n(v, default):
                return float(v) if v is not None else float(default)

            try:
                runs = max(1, int(runs_input.value or 1))
                me   = max(0, min(10, int(me_input.value if me_input.value is not None else 0)))
                sci  = max(0.0, _n(sci_input.value, 5)) / 100.0
                ft   = max(0.0, _n(ft_input.value, 0)) / 100.0
                scc  = max(0.0, _n(scc_input.value, 1.5)) / 100.0
                bf   = max(0.0, _n(bf_input.value, 3)) / 100.0
                st   = max(0.0, _n(st_input.value, 8)) / 100.0
                market_src = market_select.value or "region:10000002"
                price_src  = price_source_select.value or "sell"
                is_recursive = recursive_select.value == "true"
                mfg_struct_id = int(struct_select.value or 0)
                use_inventory = inventory_toggle.value
            except (ValueError, TypeError) as exc:
                ui.notify(f"Valor inválido: {exc}", type="negative")
                return

            with result_container:
                spinner = ui.spinner("dots", size="xl", color="primary").classes("q-ma-auto")

            try:
                src_type, src_id_str = market_src.split(":", 1)
                market_id = int(src_id_str)
            except (ValueError, AttributeError):
                src_type, market_id = "region", 10000002

            try:
                async with AsyncSessionLocal() as db:
                    # Busca item (prioriza seleção do autocomplete)
                    if _item_found["type_id"]:
                        item_res = await db.execute(
                            select(Item).where(Item.type_id == _item_found["type_id"])
                        )
                    elif raw_item.isdigit():
                        item_res = await db.execute(
                            select(Item).where(Item.type_id == int(raw_item))
                        )
                    else:
                        item_res = await db.execute(
                            select(Item).where(Item.type_name.ilike(f"%{raw_item}%"))
                        )
                    item = item_res.scalars().first()
                    if item is None:
                        result_container.clear()
                        with result_container:
                            ui.notify(f"Item '{raw_item}' não encontrado.", type="negative")
                        return

                    # Token para estruturas privadas
                    char_token = None
                    if src_type == "structure":
                        char_id = nicegui_app.storage.general.get("character_id")
                        if char_id:
                            char = await get_character(int(char_id), db)
                            if char:
                                char_token = await get_fresh_token(char, db)

                    # Bônus de estrutura de manufatura
                    structure_me_bonus = 0.0
                    active_struct = None
                    if mfg_struct_id:
                        sr = await db.execute(
                            select(ManufacturingStructure).where(
                                ManufacturingStructure.id == mfg_struct_id
                            )
                        )
                        active_struct = sr.scalar_one_or_none()
                        if active_struct:
                            structure_me_bonus = active_struct.me_bonus

                    # Blueprint
                    bp = await get_blueprint_by_product(item.type_id, db)
                    if bp is None:
                        result_container.clear()
                        with result_container:
                            ui.label(f"Nenhum blueprint encontrado para {item.type_name}.").classes(
                                "text-orange-5 q-pa-md"
                            )
                        return

                    # Reseta overrides quando o usuário troca de item
                    if item.type_id != last_item_type_id[0]:
                        buy_as_is_ids.clear()
                        state["me_overrides"].clear()
                        state["station_overrides"].clear()
                        last_item_type_id[0] = item.type_id

                    # BOM
                    if is_recursive:
                        # Inclui a estação do item raiz no station_overrides para
                        # exibição correta no seletor do nó raiz da árvore BOM
                        effective_station_overrides = dict(state["station_overrides"])
                        if mfg_struct_id:
                            effective_station_overrides[item.type_id] = mfg_struct_id
                        bom_tree = await get_recursive_bom(
                            item.type_id, db, runs=runs, me_level=me,
                            me_overrides=state["me_overrides"],
                            structure_me_bonus=structure_me_bonus,
                            buy_as_is_ids=frozenset(buy_as_is_ids),
                            station_overrides=effective_station_overrides,
                        )
                        leaf_map = aggregate_bom_leaves(bom_tree)
                        mat_ids = list(leaf_map.keys())
                    else:
                        raw_mats = await get_blueprint_materials(
                            bp.blueprint_type_id, db, me_level=me,
                            structure_me_bonus=structure_me_bonus,
                        )
                        mat_ids = [m["type_id"] for m in raw_mats]
                        leaf_map = {m["type_id"]: m["quantity"] * runs for m in raw_mats}

                    # Preços: lê sempre do banco.
                    # "Atualizar Preços":
                    #   - Região: bulk download em background (não bloqueia cálculo).
                    #     O cálculo roda com cache atual; quando o download terminar,
                    #     recalcula automaticamente com dados frescos.
                    #   - Estrutura: atualiza apenas os type_ids necessários (rápido, síncrono).
                    if force_refresh:
                        if src_type == "region":
                            import asyncio as _asyncio

                            _region_id_bg = market_id

                            async def _bg_region_refresh():
                                try:
                                    async with AsyncSessionLocal() as refresh_db:
                                        await refresh_region_market_prices(_region_id_bg, refresh_db)
                                        await refresh_db.commit()
                                    ui.notify(
                                        "Preços atualizados! Recalculando...",
                                        type="positive",
                                        timeout=4000,
                                    )
                                except Exception as _exc:
                                    logger.error("Background price refresh error: %s", _exc)
                                    ui.notify(f"Erro ao atualizar preços: {_exc}", type="negative")
                                finally:
                                    await do_calculate(force_refresh=False)

                            _asyncio.create_task(_bg_region_refresh())
                            ui.notify(
                                "Atualizando preços em segundo plano — calculando com cache atual.",
                                type="info",
                                timeout=6000,
                            )
                        else:
                            try:
                                await refresh_prices_for_types(
                                    mat_ids + [item.type_id], src_type, market_id, price_src, db,
                                    token=char_token,
                                )
                            except Exception as _refresh_exc:
                                logger.warning("Falha ao atualizar preços da estrutura: %s", _refresh_exc)
                                ui.notify(
                                    f"Aviso: falha ao atualizar preços — usando cache atual.",
                                    type="warning",
                                )

                    mat_prices, mat_age = await get_prices_cache_only(
                        mat_ids, src_type, market_id, price_src, db
                    )
                    sell_map, sell_age = await get_prices_cache_only(
                        [item.type_id], src_type, market_id, "sell", db
                    )

                    sell_price = sell_map.get(item.type_id)

                    # Volumes disponíveis no cache (para verificar suficiência)
                    vol_map = await get_volumes_cache_only(
                        mat_ids, src_type, market_id, price_src, db
                    )

                    # Inventário do personagem
                    inventory: dict[int, int] = {}
                    if use_inventory:
                        char_id = nicegui_app.storage.general.get("character_id")
                        if char_id:
                            char = await get_character(int(char_id), db)
                            if char:
                                token_for_assets = await get_fresh_token(char, db)
                                if token_for_assets:
                                    try:
                                        assets = await esi_client.get_character_assets(
                                            int(char_id), token_for_assets
                                        )
                                        for asset in assets:
                                            tid = asset.get("type_id")
                                            qty = asset.get("quantity", 0)
                                            if tid:
                                                inventory[tid] = inventory.get(tid, 0) + qty
                                    except ESIError as exc:
                                        logger.warning("Falha ao buscar assets: %s", exc)
                                        ui.notify(
                                            "Não foi possível buscar inventário (verifique o escopo esi-assets.read_assets.v1).",
                                            type="warning",
                                        )

                    # Cálculo
                    materials_obj = [
                        Material(
                            type_id=tid,
                            quantity=qty,
                            unit_price=mat_prices.get(tid) or 0.0,
                        )
                        for tid, qty in leaf_map.items()
                    ]
                    estimated_value = (sell_price or 0.0) * bp.product_quantity * runs
                    cost_bd = calculate_production_cost(
                        materials_obj, estimated_value,
                        system_cost_index=sci, facility_tax=ft, scc_surcharge=scc,
                    )
                    profit_bd = calculate_profit(
                        (sell_price or 0.0) * bp.product_quantity * runs,
                        cost_bd.total_cost,
                        broker_fee_pct=bf, sales_tax_pct=st,
                    )

                    # Nomes dos materiais
                    name_res = await db.execute(
                        select(Item.type_id, Item.type_name).where(Item.type_id.in_(mat_ids))
                    )
                    name_map = {r.type_id: r.type_name for r in name_res.all()}

                    enriched_mats = []
                    for m in materials_obj:
                        avail_vol = vol_map.get(m.type_id)
                        in_stock = inventory.get(m.type_id, 0)
                        to_buy = max(0, m.quantity - in_stock)
                        enriched_mats.append({
                            "type_id":       m.type_id,
                            "name":          name_map.get(m.type_id, f"Type {m.type_id}"),
                            "quantity":      m.quantity,
                            "unit_price":    m.unit_price,
                            "total_cost":    m.unit_price * to_buy,
                            "avail_volume":  avail_vol,
                            "in_stock":      in_stock,
                            "to_buy":        to_buy,
                            "vol_warning":   (avail_vol is not None and avail_vol < to_buy),
                        })

                    # Enriquece custos no BOM tree (bottom-up)
                    if is_recursive:
                        enrich_bom_costs(bom_tree, mat_prices)

            except Exception as exc:
                logger.error("Calculation error: %s", exc, exc_info=True)
                result_container.clear()
                with result_container:
                    ui.notify(f"Erro no cálculo: {exc}", type="negative")
                return

            # Formata idade do cache
            prices_age = min(filter(None, [mat_age, sell_age]), default=None)
            if prices_age:
                secs = (datetime.utcnow() - prices_age).total_seconds()
                if secs < 60:
                    age_str = "agora mesmo"
                elif secs < 3600:
                    age_str = f"{int(secs/60)} min atrás"
                else:
                    age_str = f"{int(secs/3600)}h atrás"
            else:
                age_str = "sem dados"

            result_container.clear()
            # Yield para que requests JS pendentes do drawer possam concluir
            # antes de iniciarmos o render pesado (evita TimeoutError do left_drawer).
            await asyncio.sleep(0)

            with result_container:
                from app.ui.components.cost_breakdown import render_cost_breakdown
                render_cost_breakdown(
                    item=item,
                    blueprint=bp,
                    runs=runs,
                    sell_price=sell_price,
                    cost_bd=cost_bd,
                    profit_bd=profit_bd,
                    prices_age_str=age_str,
                    active_structure=active_struct,
                )

                # Tabela de materiais
                _render_materials_table(enriched_mats)

                # BOM tree (se recursivo)
                if is_recursive:
                    from app.ui.components.bom_tree import render_bom_tree

                    # Referências lazy para o indicador de alterações pendentes
                    _pending_ui: dict = {"label": None, "btn": None}

                    def _mark_pending():
                        if _pending_ui["label"]:
                            _pending_ui["label"].set_visibility(True)
                        if _pending_ui["btn"]:
                            _pending_ui["btn"].set_visibility(True)

                    async def handle_bom_toggle(toggled_type_id: int):
                        if toggled_type_id in buy_as_is_ids:
                            buy_as_is_ids.discard(toggled_type_id)
                        else:
                            buy_as_is_ids.add(toggled_type_id)
                        _mark_pending()

                    async def handle_me_change(tid: int, new_me: int):
                        state["me_overrides"][tid] = new_me
                        _mark_pending()

                    async def handle_station_change(tid: int, sid: int | None):
                        if tid == item.type_id:
                            # Raiz: atualiza o seletor de estrutura do formulário
                            new_sid = sid or 0
                            struct_select.value = new_sid
                            state["manufacturing_struct_id"] = new_sid
                        else:
                            if sid is None:
                                state["station_overrides"].pop(tid, None)
                            else:
                                state["station_overrides"][tid] = sid
                        _mark_pending()

                    render_bom_tree(
                        bom_tree,
                        on_toggle=handle_bom_toggle,
                        on_me_change=handle_me_change,
                        on_station_change=handle_station_change,
                        available_stations=mfg_structs,
                    )

                    # Indicador de alterações pendentes + botão Recalcular
                    with ui.row().classes("items-center gap-3 q-mt-sm q-px-sm"):
                        _pending_label = ui.label(
                            "Alterações pendentes — clique em Recalcular para atualizar os custos."
                        ).classes("text-yellow-5 text-caption")
                        _pending_label.set_visibility(False)
                        _pending_ui["label"] = _pending_label

                        _recalc_btn = ui.button(
                            "Recalcular BOM",
                            icon="refresh",
                            on_click=lambda: do_calculate(),
                        ).props("unelevated color=amber-8 dense")
                        _recalc_btn.set_visibility(False)
                        _pending_ui["btn"] = _recalc_btn

                # ── Botão: Salvar na Fila ─────────────────────────────────────
                _save_item_snapshot = {
                    "type_id":              item.type_id,
                    "type_name":            item.type_name,
                    "runs":                 runs,
                    "me_level":             me,
                    "me_overrides":         dict(state["me_overrides"]),
                    "buy_as_is_ids":        set(buy_as_is_ids),
                    "structure_me_bonus":   structure_me_bonus,
                    "manufacturing_struct_id": mfg_struct_id,
                    "market_source":        market_src,
                    "station_overrides":    dict(state["station_overrides"]),
                }

                async def save_to_queue(snap=_save_item_snapshot):
                    char_id = nicegui_app.storage.general.get("character_id")
                    if not char_id:
                        ui.notify("Faça login para usar a fila de produção.", type="warning")
                        return

                    with ui.dialog() as dlg, ui.card().classes("q-pa-md bg-grey-9 min-w-80"):
                        ui.label("Salvar na Fila de Produção").classes(
                            "text-subtitle1 text-white font-bold q-mb-sm"
                        )
                        with ui.row().classes("gap-2 items-center q-mb-xs"):
                            ui.icon("precision_manufacturing").classes("text-blue-grey-4")
                            ui.label(snap["type_name"]).classes("text-white")
                        ui.label(
                            f"{snap['runs']} run(s)  ·  ME {snap['me_level']}"
                            + (f"  ·  {len(snap['me_overrides'])} ME override(s)" if snap["me_overrides"] else "")
                            + (f"  ·  {len(snap['buy_as_is_ids'])} comprar pronto(s)" if snap["buy_as_is_ids"] else "")
                        ).classes("text-caption text-grey-5 q-mb-sm")

                        note_input = ui.input(
                            label="Nota (opcional)",
                            placeholder="ex: para Caracal Tech II",
                        ).classes("w-full")
                        note_input.props("outlined dense dark")

                        async def confirm_save():
                            try:
                                async with AsyncSessionLocal() as db:
                                    entry = ProductionQueue(
                                        character_id             = int(char_id),
                                        item_type_id             = snap["type_id"],
                                        quantity                 = snap["runs"],
                                        status                   = "pending",
                                        me_level                 = snap["me_level"],
                                        structure_me_bonus       = snap["structure_me_bonus"],
                                        manufacturing_struct_id  = snap["manufacturing_struct_id"] or None,
                                        market_source            = snap["market_source"],
                                        note                     = (note_input.value or "").strip() or None,
                                    )
                                    entry.set_me_overrides(snap["me_overrides"])
                                    entry.set_buy_as_is(snap["buy_as_is_ids"])
                                    entry.set_station_overrides(snap["station_overrides"])
                                    db.add(entry)
                                    await db.commit()
                                ui.notify(
                                    f"'{snap['type_name']}' salvo na fila!",
                                    type="positive",
                                )
                                dlg.close()
                            except Exception as exc:
                                logger.error("Save to queue error: %s", exc)
                                ui.notify(f"Erro ao salvar: {exc}", type="negative")

                        with ui.row().classes("gap-2 q-mt-md justify-end"):
                            ui.button("Cancelar", on_click=dlg.close).props("flat color=grey-5")
                            ui.button("Salvar", icon="save", on_click=confirm_save).props(
                                "unelevated color=positive"
                            )

                    dlg.open()

                with ui.row().classes("q-mt-sm"):
                    ui.button(
                        "Salvar na Fila de Produção",
                        icon="playlist_add",
                        on_click=save_to_queue,
                    ).props("unelevated color=blue-grey-7")

        # Auto-calcular ao restaurar de uma entrada da fila
        if queue_entry:
            ui.timer(0.15, do_calculate, once=True)


def _render_materials_table(materials: list[dict]):
    """Renderiza a tabela de materiais ordenada por custo, com % do total e alertas de volume."""
    has_inventory   = any(m.get("in_stock", 0) > 0 for m in materials)
    has_vol_warning = any(m.get("vol_warning", False) for m in materials)

    # Ordena por custo total descendente
    materials = sorted(materials, key=lambda m: m.get("total_cost", 0), reverse=True)

    total_cost_all = sum(m.get("total_cost", 0) for m in materials) or 1.0

    with ui.card().classes("q-pa-md bg-grey-9 w-full"):
        with ui.row().classes("items-center justify-between q-mb-sm"):
            ui.label("Materiais Necessários").classes("text-subtitle1 text-white font-bold")

            has_inventory_local = any(m.get("in_stock", 0) > 0 for m in materials)
            lines = []
            csv_rows = ["Material,Quantidade,Preco Unitario (ISK),Total (ISK)"]
            for m in materials:
                qty = m.get("to_buy", m["quantity"]) if has_inventory_local else m["quantity"]
                lines.append(f"{m['name']} {qty:,}")
                unit  = m.get("unit_price") or 0.0
                total = m.get("total_cost") or 0.0
                name_esc = m["name"].replace('"', '""')
                csv_rows.append(f'"{name_esc}",{qty},{unit:.2f},{total:.2f}')
            clipboard_text = "\\n".join(lines).replace("'", "\\'")
            csv_text = "\n".join(csv_rows)

            async def _copy_to_clipboard():
                await ui.run_javascript(
                    f"navigator.clipboard.writeText('{clipboard_text}')"
                )
                ui.notify("Lista copiada!", type="positive", position="top-right", timeout=2000)

            async def _copy_csv_to_clipboard(csv=csv_text):
                await ui.run_javascript(
                    f"navigator.clipboard.writeText({json.dumps(csv)})"
                )
                ui.notify("CSV copiado!", type="positive", position="top-right", timeout=2000)

            ui.button("Copiar lista", icon="content_copy", on_click=_copy_to_clipboard).props(
                "flat dense color=grey-5 size=sm"
            )
            ui.button("Copiar CSV", icon="table_view", on_click=_copy_csv_to_clipboard).props(
                "flat dense color=teal-5 size=sm"
            ).tooltip("Copia a lista em formato CSV para Excel / Google Sheets")

        columns = [
            {"name": "name",       "label": "Material",   "field": "name",       "align": "left",  "sortable": True},
            {"name": "quantity",   "label": "Necessário", "field": "quantity",   "align": "right"},
        ]
        if has_inventory:
            columns += [
                {"name": "in_stock", "label": "Em estoque", "field": "in_stock", "align": "right"},
                {"name": "to_buy",   "label": "A comprar",  "field": "to_buy",   "align": "right"},
            ]
        columns += [
            {"name": "unit_price",  "label": "Preço Unit.", "field": "unit_price",  "align": "right"},
            {"name": "total_cost",  "label": "Total",       "field": "total_cost",  "align": "right", "sortable": True},
            {"name": "pct_cost",    "label": "% Custo",     "field": "pct_cost",    "align": "right", "sortable": True},
        ]
        if has_vol_warning:
            columns.append(
                {"name": "vol_info", "label": "Vol. Disp.", "field": "vol_info", "align": "right"}
            )

        rows = []
        for m in materials:
            pct = (m.get("total_cost", 0) / total_cost_all) * 100
            no_price = not m["unit_price"]
            row = {
                "name":       m["name"],
                "quantity":   f"{m['quantity']:,}",
                "unit_price": "—" if no_price else f"{m['unit_price']:,.2f} ISK",
                "total_cost": "—" if no_price else f"{m['total_cost']:,.2f} ISK",
                "total_cost_raw": m.get("total_cost", 0),
                "pct_cost":   f"{pct:.1f}%",
                "pct_raw":    pct,
                "no_price":   no_price,
                "vol_warning": m.get("vol_warning", False),
            }
            if has_inventory:
                row["in_stock"] = f"{m.get('in_stock', 0):,}"
                row["to_buy"]   = f"{m.get('to_buy', m['quantity']):,}"
            if has_vol_warning:
                av = m.get("avail_volume")
                row["vol_info"] = f"{av:,}" if av is not None else "—"
            rows.append(row)

        table = ui.table(columns=columns, rows=rows, row_key="name").props(
            "dark flat bordered dense"
        ).classes("w-full text-grey-3")

        # Coluna % custo: barra visual colorida
        table.add_slot("body-cell-pct_cost", """
            <q-td :props="props">
                <div class="row items-center gap-1 justify-end">
                    <q-linear-progress
                        :value="props.row.pct_raw / 100"
                        size="6px"
                        :color="props.row.pct_raw > 30 ? 'orange-7'
                               : props.row.pct_raw > 10 ? 'yellow-7'
                               : 'blue-grey-5'"
                        track-color="grey-8"
                        style="width: 48px"
                    />
                    <span style="min-width: 40px; text-align: right">{{ props.row.pct_cost }}</span>
                </div>
            </q-td>
        """)

        # Células sem preço ficam em âmbar
        table.add_slot("body-cell-unit_price", """
            <q-td :props="props">
                <span :class="props.row.no_price ? 'text-amber-5' : 'text-grey-3'">
                    {{ props.row.unit_price }}
                    <q-icon v-if="props.row.no_price" name="warning" size="xs"
                            title="Preço não disponível no cache" />
                </span>
            </q-td>
        """)

        if has_vol_warning:
            table.add_slot("body-cell-vol_info", """
                <q-td :props="props">
                    <span :class="props.row.vol_warning ? 'text-red-4' : 'text-grey-4'">
                        {{ props.row.vol_info }}
                        <q-icon v-if="props.row.vol_warning" name="warning" size="xs"
                                title="Volume insuficiente para cobrir a quantidade necessária"/>
                    </span>
                </q-td>
            """)
