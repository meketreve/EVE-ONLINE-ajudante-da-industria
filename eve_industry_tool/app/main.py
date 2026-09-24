"""
EVE Industry Tool — NiceGUI desktop application entry point.

Replaces the previous FastAPI/Jinja2/HTMX stack with a native NiceGUI
desktop app (pywebview window).
"""

import asyncio
import logging
import os
import secrets
from datetime import datetime
from urllib.parse import urlencode, parse_qs, urlparse

from nicegui import ui, app as nicegui_app

from app.config import settings, APP_PORT
from app.database.database import init_db, AsyncSessionLocal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ── Importa todas as páginas (registra as rotas @ui.page) ────────────────────
from app.ui import auth_page         # noqa: F401  /  /login
from app.ui import dashboard_page    # noqa: F401  /dashboard
from app.ui import items_page        # noqa: F401  /items
from app.ui import industry_page     # noqa: F401  /industry
from app.ui import reprocessing_page # noqa: F401  /reprocessing
from app.ui import queue_page        # noqa: F401  /queue
from app.ui import ranking_page      # noqa: F401  /ranking
from app.ui import ranking_item_page # noqa: F401  /ranking_item
from app.ui import settings_page     # noqa: F401  /settings


# ── OAuth2 Callback ───────────────────────────────────────────────────────────

async def handle_oauth_callback(request):
    """
    Processa o retorno do EVE SSO após autenticação.
    Troca o authorization code por tokens e persiste o personagem no banco.
    """
    from starlette.responses import HTMLResponse
    from sqlalchemy import select

    from app.models.character import Character
    from app.models.user import User
    from app.services.esi_client import esi_client, ESIError

    try:
        params = dict(request.query_params)
        code  = params.get("code")
        state = params.get("state")
        error = params.get("error")

        if error:
            logger.warning("EVE SSO retornou erro: %s", error)
            return HTMLResponse(_callback_html("Erro SSO", f"EVE SSO retornou: {error}", success=False))

        if not code:
            return HTMLResponse(_callback_html("Erro", "Código de autorização ausente.", success=False))

        from app.services.sso import pop_verifier
        verifier = pop_verifier(state)
        if not verifier:
            return HTMLResponse(_callback_html(
                "Erro", "Sessão de login expirada ou inválida. Clique em Entrar novamente.", success=False,
            ))

        # Troca o código por tokens (PKCE)
        try:
            token_data = await esi_client.exchange_code_for_token(code, verifier)
        except ESIError as exc:
            logger.error("Falha na troca de token: %s", exc)
            return HTMLResponse(_callback_html("Erro", f"Falha na autenticação: {exc}", success=False))

        access_token  = token_data["access_token"]
        refresh_token = token_data.get("refresh_token", "")
        expires_in    = token_data.get("expires_in", 1200)
        token_expiry  = esi_client.compute_expiry(expires_in)

        # Verifica token e obtém info do personagem
        try:
            verify_data = await esi_client.verify_token(access_token)
        except ESIError as exc:
            logger.error("Falha na verificação do token: %s", exc)
            return HTMLResponse(_callback_html("Erro", f"Falha na verificação: {exc}", success=False))

        character_id   = int(verify_data.get("CharacterID", 0))
        character_name = verify_data.get("CharacterName", "Unknown")

        if not character_id:
            return HTMLResponse(_callback_html("Erro", "ID de personagem inválido.", success=False))

        # Informações adicionais do personagem
        corporation_id: int | None = None
        try:
            char_info = await esi_client.get_character_info(character_id)
            corporation_id = char_info.get("corporation_id")
        except ESIError:
            pass

        # Upsert do personagem no banco
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Character).where(Character.character_id == character_id)
            )
            character = result.scalar_one_or_none()

            if character is None:
                character = Character(
                    character_id=character_id,
                    character_name=character_name,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    token_expiry=token_expiry,
                    corporation_id=corporation_id,
                )
                db.add(character)
            else:
                character.character_name = character_name
                character.access_token   = access_token
                character.refresh_token  = refresh_token
                character.token_expiry   = token_expiry
                character.corporation_id = corporation_id
                character.updated_at     = datetime.utcnow()

            await db.flush()

            # Garante que existe uma linha User vinculada
            user_result = await db.execute(
                select(User).where(User.character_id == character_id)
            )
            if user_result.scalar_one_or_none() is None:
                db.add(User(character_id=character_id))

            await db.commit()

        # Procura mercados de estruturas nos assets do personagem logo após o login
        # (o scheduler só refaz isso a cada 6h)
        try:
            from app.services.discovery_service import enqueue_asset_discovery
            async with AsyncSessionLocal() as db:
                await enqueue_asset_discovery(character_id, db)
                await db.commit()
        except Exception as exc:
            logger.warning("Discovery pós-login não enfileirado: %s", exc)

        # Armazena na sessão NiceGUI (app.storage.general é por-browser)
        # Como é app nativo, existe apenas um "usuário"
        nicegui_app.storage.general["character_id"]   = character_id
        nicegui_app.storage.general["character_name"] = character_name
        nicegui_app.storage.general["access_token"]   = access_token

        logger.info("Login bem-sucedido: %s (%d)", character_name, character_id)

        return HTMLResponse(_callback_html(
            "Login realizado!",
            f"Bem-vindo, {character_name}! Você pode fechar esta janela.",
            success=True,
        ))

    except Exception as exc:
        logger.error("Erro no callback OAuth: %s", exc, exc_info=True)
        return HTMLResponse(_callback_html("Erro Interno", str(exc), success=False))


def _callback_html(title: str, message: str, success: bool) -> str:
    """Gera HTML simples para a janela de callback do OAuth."""
    color = "#4caf50" if success else "#f44336"
    redirect_script = """
        <script>
            setTimeout(function() {
                window.close();
                // tenta redirecionar a janela principal
                try { window.opener.location.href = '/dashboard'; } catch(e) {}
            }, 2000);
        </script>
    """ if success else ""

    return f"""<!DOCTYPE html>
<html>
<head><title>{title}</title>
<style>
  body {{ font-family: sans-serif; background: #1a1a2e; color: #eee;
         display: flex; align-items: center; justify-content: center;
         height: 100vh; margin: 0; }}
  .card {{ background: #16213e; padding: 2rem 3rem; border-radius: 8px;
           text-align: center; border-left: 4px solid {color}; }}
  h2 {{ color: {color}; }}
</style>
</head>
<body>
  <div class="card">
    <h2>{title}</h2>
    <p>{message}</p>
    <small style="color: #888;">Esta janela fechará automaticamente...</small>
  </div>
  {redirect_script}
</body>
</html>"""


# ── Importa User model (necessário para o callback) ───────────────────────────
from app.models.user import User  # noqa: E402


# ── Registra a rota de callback no servidor NiceGUI ───────────────────────────
nicegui_app.add_route("/auth/callback", handle_oauth_callback)


# ── Scheduler periódico ───────────────────────────────────────────────────────

async def _scheduler_loop() -> None:
    """
    Scheduler sem Redis/Celery.
    - A cada 15 min: recrawl de todas as estruturas com mercado acessível
    - A cada 1h:     limpeza de ordens stale antigas
    - A cada 6h:     rediscovery de assets para todos os personagens
    """
    from app.services.crawler_service import schedule_recrawl_all, cleanup_stale_orders
    from app.services.discovery_service import _do_asset_discovery_all

    CRAWL_INTERVAL    = 15 * 60
    CLEANUP_INTERVAL  = 60 * 60
    DISCOVER_INTERVAL = 6 * 60 * 60

    last_crawl    = 0.0
    last_cleanup  = 0.0
    last_discover = 0.0

    while True:
        await asyncio.sleep(60)
        now = asyncio.get_event_loop().time()

        if now - last_crawl >= CRAWL_INTERVAL:
            last_crawl = now
            try:
                await schedule_recrawl_all()
            except Exception as exc:
                logger.error("[scheduler] recrawl falhou: %s", exc)

        if now - last_cleanup >= CLEANUP_INTERVAL:
            last_cleanup = now
            try:
                await cleanup_stale_orders()
            except Exception as exc:
                logger.error("[scheduler] cleanup falhou: %s", exc)

        if now - last_discover >= DISCOVER_INTERVAL:
            last_discover = now
            try:
                await _do_asset_discovery_all()
            except Exception as exc:
                logger.error("[scheduler] discovery geral falhou: %s", exc)


# ── Startup ───────────────────────────────────────────────────────────────────

@nicegui_app.on_startup
async def startup():
    """Startup: inicializa BD, workers e scheduler."""
    logger.info("Startup — inicializando banco de dados...")

    # Importa todos os modelos para popular Base.metadata
    import app.models.user               # noqa: F401
    import app.models.character          # noqa: F401
    import app.models.item               # noqa: F401
    import app.models.blueprint          # noqa: F401
    import app.models.production_queue   # noqa: F401
    import app.models.cache              # noqa: F401
    import app.models.market_structure   # noqa: F401
    import app.models.structure          # noqa: F401
    import app.models.market_order       # noqa: F401
    import app.models.market_snapshot    # noqa: F401
    import app.models.job                # noqa: F401
    import app.models.user_settings      # noqa: F401
    import app.models.reprocessing       # noqa: F401
    import app.models.manufacturing_structure  # noqa: F401

    await init_db()
    logger.info("Banco inicializado.")

    # Login é obrigatório a cada inicialização — limpa sessão anterior
    for _key in ("character_name", "character_id", "access_token"):
        nicegui_app.storage.general.pop(_key, None)
    logger.info("Sessão de autenticação limpa.")

    # Inicia workers de job
    from app.services.job_runner import discovery_runner, crawl_runner
    discovery_runner.start()
    crawl_runner.start()
    logger.info("Workers iniciados.")

    # Primeiro uso: dados do jogo (SDE) e preços de Jita em background, se faltarem
    from app.services.first_run import run_first_run
    asyncio.create_task(run_first_run(), name="first_run")

    # Inicia scheduler
    asyncio.create_task(_scheduler_loop(), name="scheduler")
    logger.info("Scheduler iniciado.")

    logger.info("EVE Industry Tool pronto.")


# ── Shutdown ──────────────────────────────────────────────────────────────────

@nicegui_app.on_shutdown
async def shutdown():
    """Shutdown: para workers e fecha conexões."""
    from app.services.job_runner import discovery_runner, crawl_runner
    await discovery_runner.stop()
    await crawl_runner.stop()

    from app.services.esi_client import esi_client
    await esi_client.close()

    logger.info("Shutdown concluído.")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ in {"__main__", "__mp_main__"}:
    # EVE_TOOL_NATIVE=0 abre no navegador em vez de janela nativa (útil no Linux sem GTK/Qt)
    native = os.getenv("EVE_TOOL_NATIVE", "1") != "0"
    ui.run(
        native=native,
        title="EVE Industry Tool",
        window_size=(1400, 900) if native else None,
        reload=False,
        port=APP_PORT,
        storage_secret=settings.SECRET_KEY,
        dark=True,
    )
