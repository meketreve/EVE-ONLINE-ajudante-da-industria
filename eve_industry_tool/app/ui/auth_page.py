"""
Authentication pages for NiceGUI.
/ and /login — show login button if not authenticated.
Handles OAuth2 callback via /auth/callback route.
"""

import logging
import webbrowser
from datetime import datetime

from nicegui import ui, app as nicegui_app

from app.config import settings
from app.services.sso import start_login
from app.ui.components.setup_panel import first_run_banner

logger = logging.getLogger(__name__)


@ui.page("/")
@ui.page("/login")
async def login_page():
    """Página de login / splash screen."""
    character_name = nicegui_app.storage.general.get("character_name")
    if character_name:
        ui.navigate.to("/dashboard")
        return

    with ui.column().classes("items-center justify-center w-full min-h-screen gap-6 bg-grey-10"):
        with ui.element("div").style("width: min(560px, 92vw)"):
            first_run_banner()
        with ui.card().classes("q-pa-xl text-center bg-grey-9 shadow-8 rounded-lg"):
            ui.icon("rocket_launch").classes("text-6xl text-blue-grey-3 q-mb-md")
            ui.label("EVE Industry Tool").classes("text-h4 text-white font-bold q-mb-xs")
            ui.label("Ferramenta de análise de indústria para EVE Online").classes(
                "text-subtitle2 text-grey-5 q-mb-xl"
            )

            if not settings.EVE_CLIENT_ID:
                ui.label(
                    "Login indisponível: defina DEFAULT_EVE_CLIENT_ID em app/config.py "
                    "ou EVE_CLIENT_ID no arquivo .env."
                ).classes("text-caption text-orange-5 q-mb-md")

            waiting = {"active": False}

            async def do_login():
                webbrowser.open(start_login())
                status_label.set_text("Aguardando callback do EVE SSO...")
                spinner.set_visibility(True)
                waiting["active"] = True

            ui.button(
                "Entrar com EVE Online",
                on_click=do_login,
                icon="login",
            ).props("unelevated size=lg color=blue-grey-7").classes("q-mb-md")

            status_label = ui.label("").classes("text-caption text-grey-5")
            spinner = ui.spinner("dots", size="md", color="blue-grey").classes("q-mt-sm")
            spinner.set_visibility(False)

            # Verifica a cada segundo se o callback completou e redireciona
            def check_auth():
                if waiting["active"] and nicegui_app.storage.general.get("character_name"):
                    ui.navigate.to("/dashboard")

            ui.timer(1.0, check_auth)

        with ui.row().classes("items-center gap-2 text-grey-6 text-caption"):
            ui.icon("info").classes("text-xs")
            ui.label("Seus dados ficam armazenados localmente. Nenhuma informação é enviada a terceiros.")
