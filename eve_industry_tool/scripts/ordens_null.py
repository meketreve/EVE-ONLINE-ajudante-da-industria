#!/usr/bin/env python3
"""
Busca e exibe ordens de compra/venda de estruturas privadas null-sec.

Funcionalidades:
  - Lista estruturas já salvas no banco
  - Adiciona uma estrutura por ID (mesmo que não tenha sido descoberta antes)
  - Busca ordens e salva no market_price_cache
  - Exibe resumo de buy/sell por item

Uso:
    python scripts/ordens_null.py                    # lista estruturas + atualiza cache
    python scripts/ordens_null.py --add 1234567890   # adiciona estrutura por ID e busca ordens
    python scripts/ordens_null.py --id  1234567890   # atualiza apenas uma estrutura específica
    python scripts/ordens_null.py --listar           # só lista estruturas, não busca ordens
    python scripts/ordens_null.py --character "Nome" # usa apenas esse personagem
"""

import asyncio
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

os.chdir(Path(__file__).parent.parent)
sys.path.insert(0, str(Path.cwd()))

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings, sso_token_auth
from app.models.character import Character
from app.models.market_structure import MarketStructure
from app.database.database import Base

ESI_BASE      = settings.ESI_BASE_URL
SSO_TOKEN_URL = f"{settings.SSO_BASE_URL}/v2/oauth/token"


# ---------------------------------------------------------------------------
# Cliente HTTP
# ---------------------------------------------------------------------------

class Client:
    def __init__(self):
        self.http = httpx.Client(
            timeout=60,
            headers={"User-Agent": "EVE Industry Tool / ordens_null.py"},
        )

    def close(self):
        self.http.close()

    def refresh_token(self, refresh_token: str) -> dict:
        headers, auth_data = sso_token_auth()
        r = self.http.post(
            SSO_TOKEN_URL,
            headers=headers,
            data={"grant_type": "refresh_token", "refresh_token": refresh_token, **auth_data},
        )
        r.raise_for_status()
        return r.json()

    def get_structure_info(self, structure_id: int, token: str) -> dict | None:
        """Retorna info da estrutura ou None se 403/404."""
        try:
            r = self.http.get(
                f"{ESI_BASE}/universe/structures/{structure_id}/",
                headers={"Authorization": f"Bearer {token}"},
            )
            if r.status_code in (403, 404):
                return None
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError:
            return None

    def get_system_name(self, system_id: int) -> str:
        try:
            r = self.http.get(f"{ESI_BASE}/universe/systems/{system_id}/")
            r.raise_for_status()
            return r.json().get("name", str(system_id))
        except Exception:
            return str(system_id)

    def fetch_orders(
        self, structure_id: int, token: str
    ) -> list[dict] | None:
        """
        Busca todas as páginas de ordens.
        Retorna None se 403 (sem acesso com esse token).
        Retorna [] se 404 ou sem ordens.
        """
        all_orders: list[dict] = []
        page = 1
        MAX_RETRIES = 3

        while True:
            last_err = None
            for attempt in range(MAX_RETRIES):
                if attempt:
                    import time
                    delay = 2 ** attempt
                    print(f"      [retry {attempt+1}/{MAX_RETRIES}] aguardando {delay}s...", flush=True)
                    time.sleep(delay)
                try:
                    r = self.http.get(
                        f"{ESI_BASE}/markets/structures/{structure_id}/",
                        headers={"Authorization": f"Bearer {token}"},
                        params={"page": page},
                    )
                    if r.status_code == 403:
                        return None
                    if r.status_code == 404:
                        return []
                    if r.status_code in (502, 503, 504):
                        last_err = r.status_code
                        continue
                    r.raise_for_status()
                    data = r.json()
                    total_pages = int(r.headers.get("X-Pages", "1"))
                    all_orders.extend(data)
                    sys.stdout.write(
                        f"\r      página {page}/{total_pages} — {len(all_orders)} ordens   "
                    )
                    sys.stdout.flush()
                    if page >= total_pages:
                        print()
                        return all_orders
                    page += 1
                    last_err = None
                    break
                except httpx.HTTPStatusError as exc:
                    last_err = exc.response.status_code
                    continue

            if last_err is not None:
                print(f"\n      [!] ESI {last_err} após {MAX_RETRIES} tentativas — abortando.")
                return []

        return all_orders  # unreachable


# ---------------------------------------------------------------------------
# Helpers de DB
# ---------------------------------------------------------------------------

async def load_tokens(
    session: AsyncSession, client: Client, name_filter: str | None
) -> list[tuple[int, str, str]]:
    """Retorna [(char_id, char_name, token)] de todos os personagens válidos."""
    q = select(Character).where(Character.refresh_token.isnot(None))
    if name_filter:
        q = q.where(Character.character_name.ilike(f"%{name_filter}%"))
    result = await session.execute(q)
    chars = result.scalars().all()

    tokens = []
    for char in chars:
        need_refresh = (
            char.access_token is None
            or char.token_expiry is None
            or char.token_expiry < datetime.utcnow() + timedelta(seconds=60)
        )
        if need_refresh:
            try:
                data = client.refresh_token(char.refresh_token)
                char.access_token = data["access_token"]
                char.refresh_token = data.get("refresh_token", char.refresh_token)
                from app.services.esi_client import esi_client as app_esi
                char.token_expiry = app_esi.compute_expiry(data.get("expires_in", 1200))
                char.updated_at = datetime.utcnow()
                await session.flush()
            except Exception as exc:
                print(f"  [!] Falha ao renovar token de {char.character_name}: {exc} — ignorado.")
                continue
        tokens.append((char.character_id, char.character_name, char.access_token))

    return tokens


async def upsert_structure(
    session: AsyncSession,
    structure_id: int,
    name: str,
    system_id: int | None,
    system_name: str,
    character_id: int,
    character_name: str,
) -> None:
    result = await session.execute(
        select(MarketStructure).where(MarketStructure.structure_id == structure_id)
    )
    row = result.scalar_one_or_none()
    now = datetime.utcnow()
    if row is None:
        session.add(MarketStructure(
            structure_id=structure_id, name=name,
            system_id=system_id, system_name=system_name,
            character_id=character_id, character_name=character_name,
            last_updated=now,
        ))
        print(f"  [+] Estrutura adicionada ao banco: {name} ({system_name})")
    else:
        row.name = name
        row.system_id = system_id
        row.system_name = system_name
        row.last_updated = now
        print(f"  [↺] Estrutura atualizada no banco: {name} ({system_name})")


async def save_prices(
    session: AsyncSession, structure_id: int, prices: dict[tuple, float]
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
            {"type_id": type_id, "market_id": structure_id,
             "order_type": order_type, "price": price, "fetched_at": now},
        )
    return len(prices)


def calc_best_prices(orders: list[dict]) -> dict[tuple, float]:
    sell: dict[int, list[float]] = defaultdict(list)
    buy:  dict[int, list[float]] = defaultdict(list)
    for o in orders:
        if o["is_buy_order"]:
            buy[o["type_id"]].append(o["price"])
        else:
            sell[o["type_id"]].append(o["price"])
    result: dict[tuple, float] = {}
    for tid, p in sell.items():
        result[(tid, "sell")] = min(p)
    for tid, p in buy.items():
        result[(tid, "buy")] = max(p)
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run(
    add_id: int | None,
    target_id: int | None,
    only_list: bool,
    name_filter: str | None,
):
    engine = create_async_engine(settings.DATABASE_URL, echo=False,
                                  connect_args={"check_same_thread": False, "timeout": 30})
    async with engine.begin() as conn:
        import app.models.user, app.models.character, app.models.item
        import app.models.blueprint, app.models.production_queue
        import app.models.cache, app.models.market_structure
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    client = Client()

    try:
        async with Session() as session:

            # 1. Lista estruturas no banco
            result = await session.execute(
                select(MarketStructure).order_by(
                    MarketStructure.system_name, MarketStructure.name
                )
            )
            structs = result.scalars().all()

            print(f"\n{'='*60}")
            print(f"  Estruturas no banco: {len(structs)}")
            print(f"{'='*60}")
            if structs:
                for s in structs:
                    marker = "  ← alvo" if (target_id and s.structure_id == target_id) else ""
                    print(f"  {s.system_name:20s}  {s.name}{marker}")
            else:
                print("  (nenhuma — execute atualizar_estruturas.bat primeiro,")
                print("   ou use --add <ID> para adicionar manualmente)")
            print()

            if only_list:
                return

            # 2. Carrega tokens
            tokens = await load_tokens(session, client, name_filter)
            if not tokens:
                print("[✗] Nenhum personagem com token válido. Faça login no servidor.")
                return
            print(f"[→] {len(tokens)} personagem(ns) disponível(is): "
                  f"{', '.join(n for _, n, _ in tokens)}\n")

            # 3. Adiciona estrutura nova se --add
            if add_id:
                print(f"[→] Adicionando estrutura {add_id}...")
                info = None
                for char_id, char_name, token in tokens:
                    info = client.get_structure_info(add_id, token)
                    if info:
                        system_id = info.get("solar_system_id")
                        system_name = client.get_system_name(system_id) if system_id else "?"
                        await upsert_structure(
                            session, add_id,
                            name=info.get("name", f"Structure {add_id}"),
                            system_id=system_id, system_name=system_name,
                            character_id=char_id, character_name=char_name,
                        )
                        await session.commit()
                        break
                if not info:
                    print(f"  [!] Nenhum personagem conseguiu resolver a estrutura {add_id}.")
                    print("      Verifique se o ID está correto e se o personagem tem docking rights.")
                    return
                # Recarrega lista
                result = await session.execute(select(MarketStructure))
                structs = result.scalars().all()

            # 4. Determina quais estruturas buscar
            if target_id:
                targets = [s for s in structs if s.structure_id == target_id]
                if not targets:
                    print(f"[!] Estrutura {target_id} não está no banco.")
                    print("    Use --add {target_id} para adicioná-la primeiro.")
                    return
            elif add_id:
                targets = [s for s in structs if s.structure_id == add_id]
            else:
                targets = list(structs)

            if not targets:
                print("[!] Nenhuma estrutura para buscar.")
                return

            print(f"[→] Buscando ordens de {len(targets)} estrutura(s)...\n")
            print("-" * 60)

            total_ok = 0
            sem_acesso = []

            for struct in targets:
                print(f"\nEstrutura : {struct.name}")
                print(f"Sistema   : {struct.system_name}  (ID: {struct.structure_id})")

                orders = None
                used = None
                for char_id, char_name, token in tokens:
                    print(f"  → [{char_name}] ", end="", flush=True)
                    resultado = client.fetch_orders(struct.structure_id, token)
                    if resultado is None:
                        print("403 — sem acesso.")
                        continue
                    orders = resultado
                    used = char_name
                    print(f"OK — {len(orders)} ordens")
                    break

                if orders is None:
                    print("  [✗] Nenhum personagem tem acesso a esta estrutura.")
                    sem_acesso.append(struct.name)
                    continue

                if not orders:
                    print("  Mercado sem ordens ativas.")
                    continue

                prices = calc_best_prices(orders)
                n_items = len(set(tid for (tid, _) in prices))
                n_sell  = sum(1 for (_, t) in prices if t == "sell")
                n_buy   = sum(1 for (_, t) in prices if t == "buy")

                print(f"  {n_items} itens únicos  |  {n_sell} sell  |  {n_buy} buy  (token: {used})")

                saved = await save_prices(session, struct.structure_id, prices)
                await session.flush()
                print(f"  [✓] {saved} entradas salvas no cache.")
                total_ok += 1

            await session.commit()

            # 5. Resumo
            print(f"\n{'='*60}")
            print(f"  Estruturas atualizadas : {total_ok}")
            if sem_acesso:
                print(f"  Sem acesso             : {len(sem_acesso)}")
                for n in sem_acesso:
                    print(f"    • {n}")
                print()
                print("  Dica: faça login com um personagem que tenha")
                print("  docking rights nessas estruturas.")
            print(f"{'='*60}")
            print("[✓] Concluído. Calcule um item no servidor para ver os preços.")

    finally:
        client.close()
        await engine.dispose()


if __name__ == "__main__":
    args = sys.argv[1:]

    add_id     = None
    target_id  = None
    only_list  = "--listar" in args
    name_filter = None

    if "--add" in args:
        idx = args.index("--add")
        try:
            add_id = int(args[idx + 1])
        except (IndexError, ValueError):
            print("[!] --add requer um ID numérico de estrutura.")
            sys.exit(1)

    if "--id" in args:
        idx = args.index("--id")
        try:
            target_id = int(args[idx + 1])
        except (IndexError, ValueError):
            print("[!] --id requer um ID numérico de estrutura.")
            sys.exit(1)

    if "--character" in args:
        idx = args.index("--character")
        name_filter = args[idx + 1] if idx + 1 < len(args) else None

    asyncio.run(run(
        add_id=add_id,
        target_id=target_id,
        only_list=only_list,
        name_filter=name_filter,
    ))
