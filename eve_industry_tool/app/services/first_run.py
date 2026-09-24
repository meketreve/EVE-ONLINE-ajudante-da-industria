"""
Configuração automática do primeiro uso + checklist de preparação.

Na inicialização, em background:
  1. Dados do jogo (SDE): importa se faltar itens ou reprocessamento.
  2. Preços de Jita: baixa as ordens da região se o cache estiver vazio.

`tasks` guarda o andamento de cada etapa para a UI (banner e checklist).
`get_checklist()` diz o que já está pronto e o que falta o usuário fazer.
"""

import asyncio
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select

from app.database.database import AsyncSessionLocal
from app.models.cache import MarketPriceCache
from app.models.character import Character
from app.models.item import Item
from app.models.manufacturing_structure import ManufacturingStructure
from app.models.reprocessing import ReprocessingMaterial
from app.models.structure import Structure
from app.models.user_settings import UserSettings

logger = logging.getLogger(__name__)

_APP_DIR = Path(__file__).resolve().parent.parent.parent
_SDE_SCRIPT = _APP_DIR / "scripts" / "import_sde.py"
_PCT_RE = re.compile(r"(\d{1,3})%")

JITA_REGION_ID = 10000002

# state: idle | running | done | error
tasks: dict[str, dict] = {
    "sde":    {"state": "idle", "message": "", "progress": None},
    "prices": {"state": "idle", "message": "", "progress": None},
}


def _set(task: str, state: str, message: str = "", progress: float | None = None) -> None:
    tasks[task].update(state=state, message=message, progress=progress)


def is_running(task: str | None = None) -> bool:
    if task:
        return tasks[task]["state"] == "running"
    return any(t["state"] == "running" for t in tasks.values())


async def _count(model, *where) -> int:
    async with AsyncSessionLocal() as db:
        stmt = select(func.count()).select_from(model)
        if where:
            stmt = stmt.where(*where)
        return (await db.execute(stmt)).scalar_one() or 0


# ── Etapa 1: dados do jogo (SDE) ─────────────────────────────────────────────

async def sde_missing() -> bool:
    """True se faltar itens ou dados de reprocessamento."""
    return not await _count(Item) or not await _count(ReprocessingMaterial)


async def ensure_sde(force: bool = False) -> None:
    if is_running("sde"):
        return
    try:
        if not force and not await sde_missing():
            return
    except Exception:
        logger.exception("SDE: falha ao verificar o banco")
        return

    _set("sde", "running", "Preparando download dos dados do jogo…")
    logger.info("SDE incompleto — iniciando importação automática.")
    args = ["--force-download"] if force else []
    rc = await _run_sde_import(args)
    # EVERef falhou por completo → tenta Fuzzwork (maior, mas independente)
    if rc != 0:
        _set("sde", "running", "Tentando fonte alternativa (Fuzzwork, ~150 MB)…")
        rc = await _run_sde_import(["--source", "fuzzwork"])

    if rc == 0:
        _set("sde", "done", "Dados do jogo importados.", 1.0)
        logger.info("SDE importado com sucesso.")
    else:
        _set("sde", "error", "Não foi possível baixar os dados do jogo. Verifique a internet "
                             "e clique em Tentar de novo.")
        logger.error("SDE: importação terminou com código %s", rc)


async def _run_sde_import(args: list[str]) -> int:
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-X", "utf8", str(_SDE_SCRIPT), *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(_APP_DIR),
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        buf = ""
        while chunk := await proc.stdout.read(1024):
            buf += chunk.decode("utf-8", errors="replace")
            # O script usa \r para a barra de download; trata como quebra de linha
            *lines, buf = re.split(r"[\r\n]", buf)
            for line in filter(None, (ln.strip() for ln in lines)):
                _sde_progress(line)
        return await proc.wait()
    except Exception:
        logger.exception("SDE: erro ao executar importação")
        return -1


def _sde_progress(line: str) -> None:
    t = tasks["sde"]
    m = _PCT_RE.match(line)
    if not m:
        logger.info("[import_sde] %s", line)
    if m:
        t["progress"] = min(int(m.group(1)), 100) / 100
        t["message"] = f"Baixando dados do jogo… {line}"
    elif line.startswith("[↓] Descomprimindo"):
        t["progress"], t["message"] = None, "Descomprimindo dados do jogo…"
    elif line.startswith("[↓]"):
        t["progress"], t["message"] = None, "Baixando dados do jogo…"
    elif line.startswith("[→]"):
        t["progress"], t["message"] = None, "Importando itens, blueprints e reprocessamento…"


# ── Etapa 2: preços de Jita ──────────────────────────────────────────────────

async def _jita_price_info() -> tuple[int, datetime | None]:
    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(func.count(), func.max(MarketPriceCache.fetched_at)).where(
                MarketPriceCache.market_type == "region",
                MarketPriceCache.market_id == JITA_REGION_ID,
            )
        )).one()
    return row[0] or 0, row[1]


async def ensure_hub_prices(force: bool = False) -> None:
    if is_running("prices"):
        return
    try:
        if not force and (await _jita_price_info())[0]:
            return
    except Exception:
        logger.exception("Preços: falha ao verificar cache")
        return

    from app.services.market_service import refresh_region_market_prices

    _set("prices", "running", "Baixando preços de Jita (todas as ordens da região)…")
    logger.info("Cache de preços de Jita vazio — baixando ordens da região.")
    try:
        async with AsyncSessionLocal() as db:
            count = await refresh_region_market_prices(JITA_REGION_ID, db)
            await db.commit()
    except Exception:
        logger.exception("Preços: falha ao baixar ordens de Jita")
        count = 0

    if count:
        _set("prices", "done", f"Preços de {count:,} itens carregados.", 1.0)
        logger.info("Preços de Jita carregados: %d itens.", count)
    else:
        _set("prices", "error", "Não foi possível baixar os preços de Jita. Tente de novo mais tarde.")


# ── Orquestração ─────────────────────────────────────────────────────────────

async def run_first_run() -> None:
    """Executado no startup: prepara tudo o que dá para preparar sozinho."""
    await ensure_sde()
    await ensure_hub_prices()


# ── Checklist ────────────────────────────────────────────────────────────────

async def get_checklist(character_id: int | None) -> list[dict]:
    """
    Itens de preparação. Cada item:
      key, title, detail, done, optional, action (None | "sde" | "prices" | caminho da página)
    """
    items: list[dict] = []

    n_items = await _count(Item)
    n_reproc = await _count(ReprocessingMaterial)
    sde_ok = bool(n_items and n_reproc)
    items.append({
        "key": "sde", "title": "Dados do jogo",
        "detail": (f"{n_items:,} itens e {n_reproc:,} receitas de reprocessamento."
                   if sde_ok else "Itens, blueprints e reprocessamento — baixados automaticamente."),
        "done": sde_ok, "optional": False, "action": "sde",
    })

    async with AsyncSessionLocal() as db:
        chars = (await db.execute(
            select(Character.character_name, Character.refresh_token.isnot(None))
            .order_by(Character.character_name)
        )).all()
    active = [name for name, ok in chars if ok]
    expired = [name for name, ok in chars if not ok]
    if active:
        detail = f"Conectado: {', '.join(active)}."
    else:
        detail = "Entre com sua conta EVE."
    if expired:
        detail += f" Login expirado: {', '.join(expired)} — entre de novo em Configurações."
    items.append({
        "key": "login", "title": "Login com personagem",
        "detail": detail,
        "done": bool(active), "optional": False,
        "action": "/settings" if expired else "/login",
        "warning": bool(expired),
    })

    n_prices, last = await _jita_price_info()
    age = ""
    if last:
        mins = int((datetime.utcnow() - last).total_seconds() // 60)
        age = f" (atualizado há {mins} min)" if mins < 120 else f" (atualizado há {mins // 60} h)"
    items.append({
        "key": "prices", "title": "Preços de Jita",
        "detail": f"{n_prices:,} preços em cache{age}." if n_prices
                  else "Baixados automaticamente após os dados do jogo.",
        "done": bool(n_prices), "optional": False, "action": "prices",
    })

    has_settings = bool(await _count(UserSettings))
    items.append({
        "key": "settings", "title": "Revisar mercado e taxas",
        "detail": "Configurações salvas." if has_settings
                  else "Confira o mercado local, taxas e ME padrão e clique em Salvar.",
        "done": has_settings, "optional": False, "action": "/settings",
    })

    n_struct = await _count(Structure, Structure.status == "market_accessible")
    items.append({
        "key": "structures", "title": "Mercados de estruturas (citadelas)",
        "detail": f"{n_struct} mercado(s) de estrutura acessível(is)." if n_struct
                  else "Procurados automaticamente nos seus assets após o login.",
        "done": bool(n_struct), "optional": True, "action": "/settings",
    })

    n_mfg = await _count(ManufacturingStructure)
    items.append({
        "key": "manufacturing", "title": "Estrutura de produção",
        "detail": f"{n_mfg} estrutura(s) cadastrada(s)." if n_mfg
                  else "Cadastre sua Raitaru/Azbel/Sotiyo para aplicar o bônus de ME.",
        "done": bool(n_mfg), "optional": True, "action": "/settings",
    })

    return items
