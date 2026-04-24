"""
Reprocessing calculator page — /reprocessing
Compare sell value vs reprocessing value for EVE items.
"""

import json
import logging
import math
import re

from nicegui import ui, app as nicegui_app
from sqlalchemy import select, func

from app.database.database import AsyncSessionLocal
from app.models.item import Item
from app.models.reprocessing import ReprocessingMaterial
from app.models.cache import MarketPriceCache
from app.services.market_service import get_prices_cache_only, refresh_prices_for_types
from app.services.character_service import get_character, get_fresh_token, get_market_options
from app.services.settings_service import load_settings
from app.ui.layout import page_layout

logger = logging.getLogger(__name__)

_QTY_SUFFIX   = re.compile(r'\s+[xX]\s+[\d,\.]+$')
_QTY_PREFIX   = re.compile(r'^[\d,\.]+\s+[xX]\s+')
_TRAILING_NUM = re.compile(r'\s+\d[\d,\.]*$')


@ui.page("/reprocessing")
async def reprocessing_page():
    """Página de cálculo de reprocessamento."""
    default_market = "region:10000002"
    has_reproc_data = False
    market_options: dict[str, str] = {}

    try:
        async with AsyncSessionLocal() as db:
            s = await load_settings(db)
            default_market = s.get("default_market_source", "region:10000002")

            opts = await get_market_options(0, db)
            for group in opts["groups"]:
                for m in group["markets"]:
                    market_options[m["value"]] = m["label"]
            for m in opts.get("private", []):
                market_options[m["value"]] = m["label"]

            if default_market not in market_options:
                default_market = "region:10000002"

            count_res = await db.execute(
                select(func.count()).select_from(ReprocessingMaterial)
            )
            has_reproc_data = (count_res.scalar() or 0) > 0
    except Exception as exc:
        logger.error("Reprocessing page load error: %s", exc)
        if not market_options:
            market_options = {"region:10000002": "Jita (The Forge)"}

    result_container = None

    with page_layout("Reprocessamento"):
        ui.label("Calculadora de Reprocessamento").classes("text-h5 text-white q-mb-md")

        if not has_reproc_data:
            with ui.row().classes("items-center gap-2 q-pa-sm q-mb-md bg-orange-9 rounded text-white w-full"):
                ui.icon("warning")
                ui.label(
                    "Dados de reprocessamento não importados. "
                    "Execute 1_importar_sde.bat para importar o Static Data Export."
                )

        with ui.row().classes("gap-4 w-full items-start flex-wrap"):
            # Formulário
            with ui.card().classes("q-pa-md bg-grey-9 flex-1 min-w-80"):
                ui.label("Itens para Analisar").classes(
                    "text-subtitle1 text-white q-mb-sm font-bold"
                )
                ui.label(
                    "Cole os itens do inventário do EVE (Tab-separado) ou um por linha."
                ).classes("text-caption text-grey-5 q-mb-sm")

                items_textarea = ui.textarea(
                    label="Lista de Itens",
                    placeholder="Veldspar\nScordite\nPyroxeres...",
                ).classes("w-full")
                items_textarea.props("outlined dark rows=8")

                with ui.row().classes("gap-2 q-mt-sm items-end flex-wrap"):
                    market_select = ui.select(
                        options=market_options,
                        value=default_market,
                        label="Mercado",
                    ).classes("flex-1 min-w-48")
                    market_select.props("outlined dense dark")

                    yield_input = ui.number(
                        label="Rendimento (%)",
                        value=50.0,
                        min=0, max=100, step=0.1,
                    ).classes("min-w-32")
                    yield_input.props("outlined dense dark")

                with ui.row().classes("gap-2 q-mt-md"):
                    ui.button(
                        "Calcular",
                        icon="recycling",
                        on_click=lambda: do_calculate(),
                    ).props("unelevated color=primary")

                    ui.button(
                        "Atualizar Preços",
                        icon="refresh",
                        on_click=lambda: do_calculate(force_refresh=True),
                    ).props("flat color=grey-5")

            # Resultado
            result_container = ui.column().classes("flex-2 min-w-80 gap-3")
            with result_container:
                ui.label("Preencha a lista e clique em Calcular.").classes("text-grey-6 q-pa-md")

        async def do_calculate(force_refresh: bool = False):
            result_container.clear()

            items_text = items_textarea.value or ""
            if not items_text.strip():
                ui.notify("Informe pelo menos um item.", type="warning")
                return

            market_src = market_select.value or "region:10000002"
            yield_pct  = float(yield_input.value or 50.0)

            with result_container:
                ui.spinner("dots", size="xl", color="primary").classes("q-ma-auto")

            try:
                src_type, src_id_str = market_src.split(":", 1)
                market_id = int(src_id_str)
            except (ValueError, AttributeError):
                src_type, market_id = "region", 10000002

            effective_yield = max(0.0, min(1.0, yield_pct / 100.0))

            # Parse da lista de itens
            parsed: list[str] = []
            for raw in items_text.splitlines():
                name = raw.split('\t')[0].strip()
                name = _QTY_SUFFIX.sub('', name).strip()
                name = _QTY_PREFIX.sub('', name).strip()
                name = _TRAILING_NUM.sub('', name).strip()
                if name:
                    parsed.append(name)
            item_names = list(dict.fromkeys(parsed))

            if not item_names:
                result_container.clear()
                with result_container:
                    ui.notify("Nenhum item reconhecido na lista.", type="warning")
                return

            try:
                async with AsyncSessionLocal() as db:
                    # Token para estruturas privadas
                    char_token = None
                    if src_type == "structure":
                        char_id = nicegui_app.storage.general.get("character_id")
                        if char_id:
                            char = await get_character(int(char_id), db)
                            if char:
                                char_token = await get_fresh_token(char, db)

                    # Busca itens
                    item_rows = await db.execute(
                        select(Item).where(
                            func.lower(Item.type_name).in_([n.lower() for n in item_names])
                        )
                    )
                    found_items = {r.type_name.lower(): r for r in item_rows.scalars().all()}
                    not_found = [n for n in item_names if n.lower() not in found_items]
                    found_list = list(found_items.values())

                    if not found_list:
                        result_container.clear()
                        with result_container:
                            ui.notify(
                                f"Nenhum dos {len(item_names)} itens encontrado no banco.",
                                type="negative",
                            )
                        return

                    # Materiais de reprocessamento
                    found_type_ids = [i.type_id for i in found_list]
                    reproc_rows = await db.execute(
                        select(ReprocessingMaterial).where(
                            ReprocessingMaterial.type_id.in_(found_type_ids)
                        )
                    )
                    reproc_by_type: dict[int, list] = {}
                    all_mat_ids: set[int] = set()
                    for row in reproc_rows.scalars().all():
                        reproc_by_type.setdefault(row.type_id, []).append(row)
                        all_mat_ids.add(row.material_type_id)

                    all_price_ids = list(set(found_type_ids) | all_mat_ids)
                    price_map, price_age = await get_prices_cache_only(
                        all_price_ids, src_type, market_id, "sell", db
                    )
                    no_cache = all(p is None for p in price_map.values())

                    if force_refresh or no_cache:
                        await refresh_prices_for_types(
                            all_price_ids, src_type, market_id, "sell", db, token=char_token
                        )
                        price_map, price_age = await get_prices_cache_only(
                            all_price_ids, src_type, market_id, "sell", db
                        )

                    # Nomes dos materiais
                    mat_name_res = await db.execute(
                        select(Item.type_id, Item.type_name).where(
                            Item.type_id.in_(list(all_mat_ids))
                        )
                    )
                    mat_names = {r.type_id: r.type_name for r in mat_name_res.all()}

                    # Calcula e classifica
                    to_reprocess: list[dict] = []
                    to_sell:      list[dict] = []

                    for item in found_list:
                        portion = max(1, item.portion_size or 1)
                        item_price = price_map.get(item.type_id)
                        sell_val = (item_price or 0.0) * portion

                        if item.type_id not in reproc_by_type:
                            to_sell.append({
                                "type_id":    item.type_id,
                                "type_name":  item.type_name,
                                "sell_value": sell_val,
                                "reproc_value": 0.0,
                                "gain":       0.0,
                                "gain_pct":   0.0,
                                "no_reproc":  True,
                                "materials":  [],
                            })
                            continue

                        mat_val = 0.0
                        mat_details: list[dict] = []
                        for mat in reproc_by_type[item.type_id]:
                            mp = price_map.get(mat.material_type_id) or 0.0
                            output = math.floor(mat.quantity * effective_yield)
                            value  = output * mp
                            mat_val += value
                            mat_details.append({
                                "name":        mat_names.get(mat.material_type_id, f"Type {mat.material_type_id}"),
                                "base_qty":    mat.quantity,
                                "output_qty":  output,
                                "unit_price":  mp,
                                "total_value": value,
                            })

                        gain = mat_val - sell_val
                        entry = {
                            "type_id":     item.type_id,
                            "type_name":   item.type_name,
                            "sell_value":  sell_val,
                            "reproc_value": mat_val,
                            "gain":        gain,
                            "gain_pct":    (gain / sell_val * 100) if sell_val else 0.0,
                            "no_reproc":   False,
                            "materials":   mat_details,
                        }
                        if mat_val > sell_val:
                            to_reprocess.append(entry)
                        else:
                            to_sell.append(entry)

                    to_reprocess.sort(key=lambda x: x["gain"], reverse=True)
                    to_sell.sort(key=lambda x: x["gain"])

                    reproc_search = " ".join(
                        f'type:"{e["type_name"]}"' if " " in e["type_name"] else f'type:{e["type_name"]}'
                        for e in to_reprocess
                    )
                    sell_search = " ".join(
                        f'type:"{e["type_name"]}"' if " " in e["type_name"] else f'type:{e["type_name"]}'
                        for e in to_sell
                    )

            except Exception as exc:
                logger.error("Reprocessing calculation error: %s", exc, exc_info=True)
                result_container.clear()
                with result_container:
                    ui.notify(f"Erro no cálculo: {exc}", type="negative")
                return

            # Formata cache age
            from datetime import datetime as _dt
            age_str = "sem dados"
            if price_age:
                secs = (_dt.utcnow() - price_age).total_seconds()
                age_str = (
                    "agora mesmo" if secs < 60
                    else f"{int(secs/60)} min atrás" if secs < 3600
                    else f"{int(secs/3600)}h atrás"
                )

            result_container.clear()
            with result_container:
                # Cabeçalho
                with ui.row().classes("items-center gap-3 q-mb-sm"):
                    ui.label(f"Preços: {age_str}").classes("text-caption text-grey-5")
                    if not_found:
                        ui.label(f"Não encontrados: {', '.join(not_found)}").classes(
                            "text-caption text-orange-5"
                        )

                # Totais
                total_reproc_val = sum(e["reproc_value"] for e in to_reprocess)
                total_sell_val   = sum(e["sell_value"] for e in to_sell + to_reprocess)
                with ui.row().classes("gap-4 q-mb-md flex-wrap"):
                    _val_card("Reprocessar", len(to_reprocess), total_reproc_val, "green-8")
                    _val_card("Vender Direto", len(to_sell), sum(e["sell_value"] for e in to_sell), "blue-8")

                # Tabela "Reprocessar"
                if to_reprocess:
                    with ui.card().classes("q-pa-md bg-grey-9 w-full"):
                        with ui.row().classes("items-center gap-2 q-mb-sm"):
                            ui.icon("recycling").classes("text-green-5")
                            ui.label("Reprocessar").classes("text-subtitle1 text-green-5 font-bold")
                            if reproc_search:
                                async def copy_reproc():
                                    await ui.run_javascript(
                                        f"navigator.clipboard.writeText({json.dumps(reproc_search)})"
                                    )
                                    ui.notify("Busca copiada!", type="positive")
                                ui.button(
                                    "Copiar Busca", icon="content_copy",
                                    on_click=copy_reproc,
                                ).props("flat dense color=grey-5").classes("q-ml-auto")
                        _render_reproc_table(to_reprocess)

                # Tabela "Vender"
                if to_sell:
                    with ui.card().classes("q-pa-md bg-grey-9 w-full"):
                        with ui.row().classes("items-center gap-2 q-mb-sm"):
                            ui.icon("sell").classes("text-blue-5")
                            ui.label("Vender Direto").classes("text-subtitle1 text-blue-5 font-bold")
                            if sell_search:
                                async def copy_sell():
                                    await ui.run_javascript(
                                        f"navigator.clipboard.writeText({json.dumps(sell_search)})"
                                    )
                                    ui.notify("Busca copiada!", type="positive")
                                ui.button(
                                    "Copiar Busca", icon="content_copy",
                                    on_click=copy_sell,
                                ).props("flat dense color=grey-5").classes("q-ml-auto")
                        _render_reproc_table(to_sell, show_gain=False)


def _val_card(label: str, count: int, total_value: float, color: str):
    with ui.card().classes(f"q-pa-md bg-{color} text-white shadow-4 min-w-40"):
        ui.label(label).classes("text-caption opacity-80")
        ui.label(str(count)).classes("text-h5 font-bold")
        ui.label(f"{total_value:,.0f} ISK").classes("text-caption opacity-90")


def _render_reproc_table(entries: list[dict], show_gain: bool = True):
    columns = [
        {"name": "type_name",    "label": "Item",         "field": "type_name",    "align": "left"},
        {"name": "sell_value",   "label": "Venda (ISK)",  "field": "sell_value",   "align": "right"},
        {"name": "reproc_value", "label": "Reproc (ISK)", "field": "reproc_value", "align": "right"},
    ]
    if show_gain:
        columns.append({"name": "gain_pct", "label": "Ganho %", "field": "gain_pct", "align": "right"})

    rows = []
    for e in entries:
        row = {
            "type_name":    e["type_name"],
            "sell_value":   f"{e['sell_value']:,.0f}" if e["sell_value"] else "—",
            "reproc_value": f"{e['reproc_value']:,.0f}" if e.get("reproc_value") else "—",
        }
        if show_gain:
            row["gain_pct"] = f"{e['gain_pct']:+.1f}%"
        rows.append(row)

    ui.table(columns=columns, rows=rows, row_key="type_name").props(
        "dark flat bordered dense"
    ).classes("w-full text-grey-3")


