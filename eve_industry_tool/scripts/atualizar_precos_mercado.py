#!/usr/bin/env python3
"""
Atualiza o cache de preços de mercado para todas as estruturas privadas
salvas na tabela market_structures.

Endpoint usado:
    GET /markets/structures/{structure_id}/   (paginado, requer auth)
    Scope: esi-markets.structure_markets.v1

Estratégia de token:
    Para cada estrutura, tenta TODOS os personagens autenticados no banco,
    não apenas o que a descobriu. O primeiro que retornar 200 é usado.
    Isso contorna 403 causados por permissões específicas de personagem.

Uso:
    python scripts/atualizar_precos_mercado.py
    python scripts/atualizar_precos_mercado.py --structure 1234567890
    python scripts/atualizar_precos_mercado.py --character "Nome"
"""

import asyncio
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

os.chdir(Path(__file__).parent.parent)
sys.path.insert(0, str(Path.cwd()))

import httpx
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, text

from app.config import settings, sso_token_auth
from app.models.character import Character
from app.models.market_structure import MarketStructure
from app.database.database import Base

# ---------------------------------------------------------------------------
# Configurações
# ---------------------------------------------------------------------------

ESI_BASE       = settings.ESI_BASE_URL
SSO_TOKEN_URL  = f"{settings.SSO_BASE_URL}/v2/oauth/token"
MARKET_SCOPE   = "esi-markets.structure_markets.v1"


# ---------------------------------------------------------------------------
# Cliente HTTP assíncrono
# ---------------------------------------------------------------------------

class ESIClient:
    """Cliente async para ESI — mesma abordagem do app principal."""

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0),
                headers={"User-Agent": "EVE Industry Tool / atualizar_precos_mercado.py"},
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def refresh_token(self, refresh_token: str) -> dict:
        headers, auth_data = sso_token_auth()
        r = await self.client.post(
            SSO_TOKEN_URL,
            headers=headers,
            data={"grant_type": "refresh_token", "refresh_token": refresh_token, **auth_data},
        )
        r.raise_for_status()
        return r.json()

    async def get_structure_orders(self, structure_id: int, token: str) -> list[dict] | None:
        """
        GET /markets/structures/{structure_id}/   (paginado)

        Retorna lista de ordens ou:
          None  — 403 (sem acesso), sinal para tentar próximo token
          []    — 404 ou sem ordens
        Levanta httpx.HTTPStatusError para outros erros HTTP.
        """
        all_orders: list[dict] = []
        page = 1

        while True:
            r = await self.client.get(
                f"{ESI_BASE}/markets/structures/{structure_id}/",
                headers={"Authorization": f"Bearer {token}"},
                params={"page": page},
            )

            if r.status_code == 403:
                return None   # sem acesso — tenta outro personagem

            if r.status_code == 404:
                return []     # estrutura inexistente ou sem mercado ativo

            r.raise_for_status()

            data = r.json()
            if not data:
                break

            all_orders.extend(data)

            total_pages = int(r.headers.get("X-Pages", "1"))
            sys.stdout.write(
                f"\r    página {page}/{total_pages} — {len(all_orders)} ordens...   "
            )
            sys.stdout.flush()

            if page >= total_pages:
                break
            page += 1

        print()  # nova linha após progresso
        return all_orders


# ---------------------------------------------------------------------------
# Gerenciamento de tokens
# ---------------------------------------------------------------------------

async def carregar_tokens(
    session: AsyncSession,
    esi: ESIClient,
    name_filter: str | None,
) -> list[tuple[int, str, str]]:
    """
    Busca todos os personagens com refresh_token no banco,
    renova access_token se expirado e retorna lista de
    (character_id, character_name, access_token).
    """
    q = select(Character).where(Character.refresh_token.isnot(None))
    if name_filter:
        q = q.where(Character.character_name.ilike(f"%{name_filter}%"))

    result   = await session.execute(q)
    chars    = result.scalars().all()
    tokens   = []

    print(f"[→] {len(chars)} personagem(ns) com token no banco.\n")

    for char in chars:
        print(f"  [{char.character_name}] ", end="", flush=True)

        if char.is_token_expired() or char.access_token is None:
            print("renovando token...", end=" ", flush=True)
            try:
                data = await esi.refresh_token(char.refresh_token)
                char.access_token  = data["access_token"]
                char.refresh_token = data.get("refresh_token", char.refresh_token)
                from app.services.esi_client import esi_client as app_esi
                char.token_expiry  = app_esi.compute_expiry(data.get("expires_in", 1200))
                char.updated_at    = datetime.utcnow()
                await session.flush()
                print("ok")
            except Exception as exc:
                print(f"FALHA ({exc}) — ignorado.")
                continue
        else:
            print("token válido")

        tokens.append((char.character_id, char.character_name, char.access_token))

    return tokens


# ---------------------------------------------------------------------------
# Processamento de ordens
# ---------------------------------------------------------------------------

def calcular_melhores_precos(orders: list[dict]) -> dict[tuple, float]:
    """
    sell → menor preço (quem vende mais barato)
    buy  → maior preço (quem paga mais)
    Retorna {(type_id, "sell"|"buy"): melhor_preco}
    """
    sell: dict[int, list[float]] = defaultdict(list)
    buy:  dict[int, list[float]] = defaultdict(list)

    for o in orders:
        if o["is_buy_order"]:
            buy[o["type_id"]].append(o["price"])
        else:
            sell[o["type_id"]].append(o["price"])

    result: dict[tuple, float] = {}
    for tid, prices in sell.items():
        result[(tid, "sell")] = min(prices)
    for tid, prices in buy.items():
        result[(tid, "buy")] = max(prices)

    return result


# ---------------------------------------------------------------------------
# Persistência
# ---------------------------------------------------------------------------

async def upsert_prices(
    session: AsyncSession,
    structure_id: int,
    prices: dict[tuple, float],
) -> int:
    now = datetime.utcnow()
    for (type_id, order_type), price in prices.items():
        await session.execute(
            text("""
                INSERT OR REPLACE INTO market_price_cache
                    (type_id, market_type, market_id, order_type, price, fetched_at)
                VALUES
                    (:type_id, 'structure', :market_id, :order_type, :price, :fetched_at)
            """),
            {
                "type_id":    type_id,
                "market_id":  structure_id,
                "order_type": order_type,
                "price":      price,
                "fetched_at": now,
            },
        )
    return len(prices)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run(structure_filter: int | None, name_filter: str | None):
    engine = create_async_engine(settings.DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        import app.models.user, app.models.character, app.models.item
        import app.models.blueprint, app.models.production_queue
        import app.models.cache, app.models.market_structure
        await conn.run_sync(Base.metadata.create_all)

    AsyncSessionFactory = async_sessionmaker(engine, expire_on_commit=False)
    esi = ESIClient()

    try:
        async with AsyncSessionFactory() as session:

            # 1. Carrega e renova todos os tokens disponíveis
            tokens = await carregar_tokens(session, esi, name_filter)

            if not tokens:
                print("\n[✗] Nenhum personagem com token válido encontrado.")
                print("    Faça login no servidor ao menos uma vez.")
                return

            print(f"\n[→] {len(tokens)} token(s) disponível(is) para tentar por estrutura.\n")
            await session.commit()  # persiste tokens renovados

            # 2. Carrega estruturas
            q = select(MarketStructure)
            if structure_filter:
                q = q.where(MarketStructure.structure_id == structure_filter)
            result     = await session.execute(q)
            structures = result.scalars().all()

            if not structures:
                print("[✗] Nenhuma estrutura no banco.")
                print("    Execute atualizar_estruturas.bat --so-estruturas primeiro.")
                return

            print(f"[→] {len(structures)} estrutura(s) para atualizar.\n")
            print("-" * 50)

            total_ok    = 0
            total_itens = 0
            sem_acesso  = []

            for struct in structures:
                print(f"\nEstrutura : {struct.name}")
                print(f"ID        : {struct.structure_id}  |  Sistema: {struct.system_name}")

                orders      = None
                token_usado = None

                # Tenta cada token disponível até um ter acesso (200)
                for char_id, char_name, token in tokens:
                    print(f"  → tentando [{char_name}]...", end=" ", flush=True)
                    try:
                        resultado = await esi.get_structure_orders(struct.structure_id, token)
                    except httpx.HTTPStatusError as exc:
                        print(f"erro HTTP {exc.response.status_code} — próximo.")
                        continue
                    except Exception as exc:
                        print(f"erro: {exc} — próximo.")
                        continue

                    if resultado is None:
                        print("403 sem acesso — próximo.")
                        continue

                    # Sucesso (200) — pode ser lista vazia (sem ordens ativas)
                    orders      = resultado
                    token_usado = char_name
                    print(f"OK  ({len(orders)} ordens)")
                    break

                if orders is None:
                    print(f"  [✗] Nenhum personagem tem acesso a esta estrutura.")
                    sem_acesso.append(struct.name)
                    continue

                if not orders:
                    print("  Mercado sem ordens ativas — cache não atualizado.")
                    continue

                prices      = calcular_melhores_precos(orders)
                itens_unicos = len(set(tid for (tid, _) in prices))
                print(f"  {len(orders)} ordens → {itens_unicos} itens únicos  (usado: {token_usado})")

                gravados = await upsert_prices(session, struct.structure_id, prices)
                await session.flush()

                total_ok    += 1
                total_itens += itens_unicos
                print(f"  [✓] {gravados} entradas gravadas no cache.")

            await session.commit()

            print(f"\n{'='*50}")
            print(f"  Estruturas atualizadas : {total_ok}")
            print(f"  Itens únicos no cache  : {total_itens}")
            if sem_acesso:
                print(f"  Sem acesso ({len(sem_acesso)})       : {', '.join(sem_acesso)}")
                print()
                print("  Para estruturas sem acesso, faça login com um personagem")
                print("  que tenha docking rights e execute novamente.")
            print(f"{'='*50}")
            print("[✓] Concluído.")

    finally:
        await esi.close()
        await engine.dispose()


if __name__ == "__main__":
    args = sys.argv[1:]

    structure_filter = None
    if "--structure" in args:
        idx = args.index("--structure")
        try:
            structure_filter = int(args[idx + 1]) if idx + 1 < len(args) else None
        except (ValueError, IndexError):
            print("[!] --structure requer um ID numérico.")
            sys.exit(1)

    name_filter = None
    if "--character" in args:
        idx = args.index("--character")
        name_filter = args[idx + 1] if idx + 1 < len(args) else None

    asyncio.run(run(structure_filter=structure_filter, name_filter=name_filter))
