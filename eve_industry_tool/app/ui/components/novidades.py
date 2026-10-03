"""
"O que há de novo": aviso mostrado uma vez depois que o atualizar.py instala uma release.

O atualizar.py grava `.novidades.json` (tag, versão anterior, notas da release) na raiz da
instalação; ao fechar o aviso o arquivo é apagado e ele não aparece de novo.
"""

import json
import logging
import re

from nicegui import ui

from app.config import INSTALL_ROOT

logger = logging.getLogger(__name__)

NEWS_FILE = INSTALL_ROOT / ".novidades.json"


def _load_news() -> dict | None:
    try:
        return json.loads(NEWS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        logger.warning("Arquivo de novidades ilegível; descartando.")
        NEWS_FILE.unlink(missing_ok=True)
        return None


def whats_new_dialog() -> None:
    news = _load_news()
    if not news:
        return

    def dismiss():
        NEWS_FILE.unlink(missing_ok=True)
        dialog.close()

    with ui.dialog().props("persistent") as dialog, \
            ui.card().classes("bg-grey-9 text-white q-pa-lg").style("width: min(640px, 92vw)"):
        with ui.row().classes("items-center gap-3 no-wrap"):
            ui.icon("new_releases").classes("text-4xl text-green-5")
            with ui.column().classes("gap-0"):
                ui.label(f"Atualizado para {news.get('tag', '')}").classes("text-h6 font-bold")
                if news.get("from"):
                    ui.label(f"Você estava na versão {news['from']}. Seus dados foram mantidos.") \
                        .classes("text-caption text-grey-5")
        ui.separator().classes("q-my-sm")
        with ui.scroll_area().style("max-height: 55vh"):
            # Títulos das notas (## Novidades) em tamanho de subtítulo, não de página
            body = re.sub(r"^#{1,3} ", "#### ", news.get("body") or "Sem notas para esta versão.", flags=re.M)
            ui.markdown(body).classes("text-body2")
        with ui.row().classes("w-full justify-end gap-2 q-mt-md"):
            if news.get("url"):
                ui.button("Ver no GitHub", icon="open_in_new",
                          on_click=lambda: ui.navigate.to(news["url"], new_tab=True)) \
                    .props("flat color=blue-grey-3")
            ui.button("Entendi", icon="check", on_click=dismiss).props("unelevated color=positive")

    dialog.open()
