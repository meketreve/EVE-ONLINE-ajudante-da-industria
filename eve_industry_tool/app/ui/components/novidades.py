"""
"O que há de novo": aviso mostrado uma vez depois de uma atualização.

Fonte das notas, em ordem:
  1. `.novidades.json` gravado pelo atualizar.py (v1.1.0+) logo após instalar a release.
  2. Se o arquivo não existe mas a versão mudou numa instalação atualizada (updater antigo,
     v1.0.0, não gravava o arquivo), `prepare_news()` busca as notas da release desta versão
     no GitHub na abertura do app e grava o mesmo arquivo.

`last_seen_version` (storage.general) guarda até qual versão o usuário já viu as notas.
Ao fechar o aviso o arquivo é apagado e a versão é marcada como vista.
"""

import asyncio
import json
import logging
import re

import httpx
from nicegui import app as nicegui_app
from nicegui import ui

from app.config import APP_VERSION, INSTALL_ROOT, RELEASES_API

logger = logging.getLogger(__name__)

NEWS_FILE = INSTALL_ROOT / ".novidades.json"
MANIFEST_FILE = INSTALL_ROOT / ".arquivos-instalados"   # só existe em instalação atualizada
SEEN_KEY = "last_seen_version"

# A busca no GitHub roda no startup; a página pode carregar antes de ela terminar
_state = {"pending": False}


def _mark_seen() -> None:
    nicegui_app.storage.general[SEEN_KEY] = APP_VERSION


def start_news_check() -> None:
    """Chamado no startup. Marca "buscando" antes da tarefa existir, para nenhuma página perder o aviso."""
    _state["pending"] = True
    asyncio.create_task(prepare_news(), name="news_check")


async def prepare_news() -> None:
    """Garante `.novidades.json` quando a versão mudou e o updater não deixou as notas."""
    try:
        await _prepare_news()
    finally:
        _state["pending"] = False


async def _prepare_news() -> None:
    general = nicegui_app.storage.general
    last = general.get(SEEN_KEY)

    if NEWS_FILE.exists() or last == APP_VERSION or APP_VERSION == "?":
        return
    # Instalação nova (sem manifesto do updater e sem versão anterior): nada a anunciar
    if last is None and not MANIFEST_FILE.exists():
        _mark_seen()
        return

    try:
        async with httpx.AsyncClient(timeout=5, headers={"User-Agent": "EVE-Industry-Tool"}) as client:
            resp = await client.get(f"{RELEASES_API}/tags/v{APP_VERSION}")
        if resp.status_code == 404:
            _mark_seen()  # versão sem release (ex.: desenvolvimento)
            return
        resp.raise_for_status()
        release = resp.json()
        NEWS_FILE.write_text(json.dumps({
            "tag": release.get("tag_name") or f"v{APP_VERSION}",
            "from": last or "",
            "body": release.get("body") or "",
            "url": release.get("html_url") or "",
        }, ensure_ascii=False), encoding="utf-8")
        logger.info("Notas da v%s obtidas do GitHub para o aviso de novidades.", APP_VERSION)
    except Exception as exc:  # offline etc.: tenta de novo na próxima abertura
        logger.info("Notas da versão não obtidas (%s); tenta na próxima abertura.", exc.__class__.__name__)


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
    if news:
        _open_dialog(news)
        return
    if not _state["pending"]:
        return

    # Busca no GitHub ainda em andamento: espera um pouco pelo arquivo
    tries = {"n": 0}

    def wait_for_news():
        tries["n"] += 1
        found = _load_news()
        if found or (not _state["pending"]) or tries["n"] > 15:
            timer.deactivate()
            if found:
                _open_dialog(found)

    timer = ui.timer(1.0, wait_for_news)


def _open_dialog(news: dict) -> None:
    def dismiss():
        NEWS_FILE.unlink(missing_ok=True)
        _mark_seen()
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
                else:
                    ui.label("Seus dados foram mantidos.").classes("text-caption text-grey-5")
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
