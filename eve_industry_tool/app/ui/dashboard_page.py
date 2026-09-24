"""
Dashboard page — /dashboard
Welcome screen with quick stats and action buttons.
"""

import logging
from datetime import datetime

from nicegui import ui, app as nicegui_app
from sqlalchemy import select, func

from app.database.database import AsyncSessionLocal
from app.models.production_queue import ProductionQueue
from app.models.structure import Structure
from app.ui.components.setup_panel import setup_checklist
from app.ui.layout import page_layout

logger = logging.getLogger(__name__)


@ui.page("/dashboard")
async def dashboard_page():
    """Dashboard com estatísticas rápidas e ações."""
    character_name = nicegui_app.storage.general.get("character_name")
    character_id   = nicegui_app.storage.general.get("character_id")

    if not character_name:
        ui.navigate.to("/")
        return

    # Busca estatísticas
    queue_count      = 0
    struct_count     = 0
    accessible_count = 0
    last_crawl_str   = "Nunca"

    try:
        async with AsyncSessionLocal() as db:
            if character_id:
                q_res = await db.execute(
                    select(func.count()).select_from(ProductionQueue).where(
                        ProductionQueue.character_id == character_id,
                        ProductionQueue.status != "completed",
                    )
                )
                queue_count = q_res.scalar_one() or 0

            s_res = await db.execute(select(func.count()).select_from(Structure))
            struct_count = s_res.scalar_one() or 0

            sa_res = await db.execute(
                select(func.count()).select_from(Structure).where(
                    Structure.status == "market_accessible"
                )
            )
            accessible_count = sa_res.scalar_one() or 0

            lc_res = await db.execute(
                select(Structure.last_crawled_at)
                .where(Structure.last_crawled_at.isnot(None))
                .order_by(Structure.last_crawled_at.desc())
                .limit(1)
            )
            lc_row = lc_res.scalar_one_or_none()
            if lc_row:
                last_crawl_str = lc_row.strftime("%d/%m %H:%M")
                nicegui_app.storage.general["last_crawl_time"] = last_crawl_str
    except Exception as exc:
        logger.error("Dashboard: erro ao carregar stats: %s", exc)

    with page_layout("Dashboard"):
        # Boas-vindas
        with ui.row().classes("items-center gap-3 q-mb-lg"):
            ui.icon("waving_hand").classes("text-4xl text-yellow-6")
            with ui.column().classes("gap-0"):
                ui.label(f"Olá, {character_name}!").classes("text-h5 text-white font-bold")
                ui.label("Bem-vindo ao EVE Industry Tool").classes("text-caption text-grey-5")

        # Checklist de preparação (recolhe sozinho quando o essencial está pronto)
        await setup_checklist(character_id)

        # Cards de estatísticas
        with ui.row().classes("gap-4 q-mb-xl flex-wrap"):
            _stat_card("Itens na Fila", str(queue_count), "queue", "blue-grey-7")
            _stat_card("Estruturas Conhecidas", str(struct_count), "location_city", "blue-7")
            _stat_card("Mercados Acessíveis", str(accessible_count), "store", "green-7")
            _stat_card("Último Crawl", last_crawl_str, "update", "orange-7")

        # Ações rápidas
        ui.label("Ações Rápidas").classes("text-h6 text-white q-mb-md")
        with ui.row().classes("gap-3 flex-wrap"):
            _action_btn("Calcular Produção", "precision_manufacturing", "/industry", "primary")
            _action_btn("Reprocessamento", "recycling", "/reprocessing", "secondary")
            _action_btn("Ver Ranking", "leaderboard", "/ranking", "positive")
            _action_btn("Configurações", "settings", "/settings", "dark")


def _stat_card(title: str, value: str, icon: str, color: str):
    with ui.card().classes(f"q-pa-md bg-{color} text-white shadow-4 min-w-36"):
        with ui.row().classes("items-center gap-3"):
            ui.icon(icon).classes("text-3xl text-white opacity-80")
            with ui.column().classes("gap-0"):
                ui.label(value).classes("text-h5 font-bold")
                ui.label(title).classes("text-caption opacity-80")


def _action_btn(label: str, icon: str, path: str, color: str):
    ui.button(label, icon=icon, on_click=lambda p=path: ui.navigate.to(p)).props(
        f"unelevated color={color}"
    ).classes("q-px-lg")
