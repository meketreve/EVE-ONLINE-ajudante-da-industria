"""
Shared NiceGUI layout with left navigation drawer and status bar.
"""

from contextlib import contextmanager
from datetime import datetime

from nicegui import ui, app as nicegui_app

from app.ui.components.setup_panel import first_run_banner


NAV_ITEMS = [
    ("/dashboard",    "home",                    "Dashboard"),
    ("/industry",     "precision_manufacturing", "Calculadora"),
    ("/reprocessing", "recycling",               "Reprocessamento"),
    ("/queue",        "queue",                   "Fila de Produção"),
    ("/ranking",      "leaderboard",             "Importação"),
    ("/settings",     "settings",                "Configurações"),
]


@contextmanager
def page_layout(title: str = "EVE Industry Tool"):
    """
    Context manager que renderiza o layout completo (drawer + status bar).
    Uso:
        with page_layout("Título"):
            # conteúdo da página aqui
    """
    # Header
    with ui.header(elevated=True).classes("items-center justify-between bg-blue-grey-9 text-white"):
        with ui.row().classes("items-center gap-2"):
            ui.button(icon="menu", on_click=lambda: left_drawer.toggle()).props("flat round dense")
            ui.label(title).classes("text-h6 font-bold")

        with ui.row().classes("items-center gap-2"):
            character_name = nicegui_app.storage.general.get("character_name")
            if character_name:
                ui.icon("person").classes("text-green-4")
                ui.label(character_name).classes("text-caption text-green-4")
            else:
                ui.label("Não autenticado").classes("text-caption text-grey-5")

    # Left drawer
    left_drawer = ui.left_drawer(bordered=True).classes("bg-grey-9")
    with left_drawer:
        ui.label("EVE Industry Tool").classes("text-h6 text-white q-pa-md font-bold")
        ui.separator()

        current_path = "/"
        try:
            from nicegui import context
            current_path = context.client.page.path
        except Exception:
            pass

        for path, icon, label in NAV_ITEMS:
            is_active = current_path == path
            btn_classes = "w-full text-left text-white"
            if is_active:
                btn_classes += " bg-blue-grey-7"
            with ui.row().classes("w-full items-center q-px-sm q-py-xs cursor-pointer hover:bg-blue-grey-8 rounded") as row:
                row.on("click", lambda p=path: ui.navigate.to(p))
                ui.icon(icon).classes("text-grey-4")
                ui.label(label).classes("text-grey-3 text-body2 q-ml-sm")

        ui.separator()

        # Status
        with ui.column().classes("q-pa-sm gap-1"):
            ui.label("Status").classes("text-caption text-grey-5 font-bold")
            last_crawl = nicegui_app.storage.general.get("last_crawl_time")
            if last_crawl:
                ui.label(f"Último crawl: {last_crawl}").classes("text-caption text-grey-5")
            else:
                ui.label("Aguardando crawl...").classes("text-caption text-grey-6")

    # Main content area
    with ui.column().classes("w-full p-4"):
        first_run_banner()
        yield

    # Footer / status bar
    with ui.footer().classes("bg-grey-9 text-grey-5 text-caption q-px-md q-py-xs"):
        with ui.row().classes("items-center gap-4 w-full"):
            char_name = nicegui_app.storage.general.get("character_name", "")
            if char_name:
                ui.label(f"Personagem: {char_name}")
                ui.label("|").classes("text-grey-7")
            ui.label("EVE Industry Tool")
            ui.space()
            ui.label(f"v1.0 — {datetime.now().strftime('%H:%M')}").classes("text-grey-6")
