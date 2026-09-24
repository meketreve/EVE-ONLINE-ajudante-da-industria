#!/usr/bin/env python3
"""
Busca todas as estruturas privadas com mercado acessíveis aos personagens
autenticados e salva no banco de dados (tabela market_structures).

Usa duas fontes da ESI combinadas para máxima cobertura:

  Fonte 1 — Corporação  (GET /corporations/{id}/structures/)
    Lista estruturas que a corporação do personagem POSSUI com serviço de
    mercado ativo. Requer esi-corporations.read_structures.v1.
    Não exige que o personagem tenha dockado — cobre citadelas próprias mesmo
    recém-lançadas.

  Fonte 2 — Universo  (GET /universe/structures/?filter=market)
    Lista estruturas de TERCEIROS onde o personagem tem acesso de mercado
    (já dockou ou tem docking rights). Requer esi-universe.read_structures.v1.

Uso:
    python scripts/atualizar_estruturas.py
    python scripts/atualizar_estruturas.py --character "Nome do Personagem"
    python scripts/atualizar_estruturas.py --limpar   # remove estruturas antes de re-importar
    python scripts/atualizar_estruturas.py --fonte corp      # apenas fonte 1
    python scripts/atualizar_estruturas.py --fonte universo  # apenas fonte 2
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Garante que imports da app funcionem
os.chdir(Path(__file__).parent.parent)
sys.path.insert(0, str(Path.cwd()))

import httpx
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, delete

from app.config import settings, sso_token_auth
from app.models.character import Character
from app.models.market_structure import MarketStructure
from app.database.database import Base

# ---------------------------------------------------------------------------
# Configurações
# ---------------------------------------------------------------------------

TOKEN_REFRESH_MARGIN = timedelta(seconds=60)
ESI_BASE = settings.ESI_BASE_URL
SSO_TOKEN_URL = f"{settings.SSO_BASE_URL}/v2/oauth/token"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

class ScriptESIClient:
    def __init__(self):
        self.http = httpx.Client(
            timeout=30,
            headers={"User-Agent": "EVE Industry Tool / atualizar_estruturas.py"},
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

    def get_corp_structures_with_market(self, corp_id: int, token: str) -> list[dict]:
        """
        GET /corporations/{corp_id}/structures/ (paginado)
        Requer esi-corporations.read_structures.v1.

        Retorna apenas estruturas com serviço "Market" no estado "online".
        Cada item já contém: structure_id, name, system_id, services.
        """
        all_structs = []
        page = 1
        while True:
            r = self.http.get(
                f"{ESI_BASE}/corporations/{corp_id}/structures/",
                headers={"Authorization": f"Bearer {token}"},
                params={"page": page},
            )
            if r.status_code == 403:
                print("    [!] 403 — personagem não tem esi-corporations.read_structures.v1")
                print("         Faça logout e login novamente no servidor para reautorizar.")
                return []
            if r.status_code == 404:
                print("    [!] 404 — corporação não encontrada na ESI.")
                return []
            r.raise_for_status()

            data = r.json()
            all_structs.extend(data)

            total_pages = int(r.headers.get("X-Pages", "1"))
            if page >= total_pages:
                break
            page += 1

        # Filtra apenas estruturas com mercado ativo
        with_market = [
            s for s in all_structs
            if any(
                svc.get("name") == "Market" and svc.get("state") == "online"
                for svc in s.get("services", [])
            )
        ]
        return with_market

    def get_universe_market_structure_ids(self, token: str) -> list[int]:
        """
        GET /universe/structures/?filter=market
        Requer esi-universe.read_structures.v1.

        Retorna IDs de estruturas de terceiros onde o personagem tem acesso de mercado.
        """
        r = self.http.get(
            f"{ESI_BASE}/universe/structures/",
            headers={"Authorization": f"Bearer {token}"},
            params={"filter": "market"},
        )
        if r.status_code == 403:
            print("    [!] 403 — personagem não tem esi-universe.read_structures.v1")
            print("         Faça logout e login novamente no servidor para reautorizar.")
            return []
        r.raise_for_status()
        return r.json()

    def get_structure_info(self, structure_id: int, token: str) -> dict:
        """GET /universe/structures/{id}/ — nome e sistema de uma estrutura."""
        r = self.http.get(
            f"{ESI_BASE}/universe/structures/{structure_id}/",
            headers={"Authorization": f"Bearer {token}"},
        )
        r.raise_for_status()
        return r.json()

    def get_character_asset_structure_ids(self, character_id: int, token: str) -> list[int]:
        """
        GET /characters/{character_id}/assets/ (paginado)
        Requer esi-assets.read_assets.v1.

        Retorna IDs únicos de estruturas Upwell onde o personagem tem items.
        location_id >= 1_000_000_000_000 → ID de estrutura Upwell.
        """
        UPWELL_MIN = 1_000_000_000_000
        all_assets: list[dict] = []
        page = 1

        while True:
            r = self.http.get(
                f"{ESI_BASE}/characters/{character_id}/assets/",
                headers={"Authorization": f"Bearer {token}"},
                params={"page": page},
            )
            if r.status_code == 403:
                print("    [!] 403 — personagem não tem esi-assets.read_assets.v1")
                print("         Faça logout e login novamente no servidor para reautorizar.")
                return []
            r.raise_for_status()

            data = r.json()
            all_assets.extend(data)

            total_pages = int(r.headers.get("X-Pages", "1"))
            sys.stdout.write(f"\r    [Fonte 3] {len(all_assets)} assets carregados (pág {page}/{total_pages})...")
            sys.stdout.flush()

            if page >= total_pages:
                break
            page += 1

        print()  # quebra linha do progresso

        structure_ids = list({
            a["location_id"]
            for a in all_assets
            if a.get("location_id", 0) >= UPWELL_MIN
        })
        return structure_ids

    def get_system_name(self, system_id: int) -> str:
        r = self.http.get(f"{ESI_BASE}/universe/systems/{system_id}/")
        r.raise_for_status()
        return r.json().get("name", str(system_id))


# ---------------------------------------------------------------------------
# Lógica de DB
# ---------------------------------------------------------------------------

async def get_characters(session: AsyncSession, name_filter: str | None) -> list[Character]:
    q = select(Character).where(Character.refresh_token.isnot(None))
    if name_filter:
        q = q.where(Character.character_name.ilike(f"%{name_filter}%"))
    result = await session.execute(q)
    return result.scalars().all()


async def update_character_token(session: AsyncSession, character: Character, token_data: dict):
    character.access_token = token_data["access_token"]
    character.refresh_token = token_data.get("refresh_token", character.refresh_token)
    from app.services.esi_client import esi_client
    character.token_expiry = esi_client.compute_expiry(token_data.get("expires_in", 1200))
    character.updated_at = datetime.utcnow()
    await session.flush()


async def upsert_structure(
    session: AsyncSession,
    structure_id: int,
    name: str,
    system_id: int | None,
    system_name: str,
    character_id: int,
    character_name: str,
) -> bool:
    """Upsert de uma estrutura. Retorna True se era nova."""
    result = await session.execute(
        select(MarketStructure).where(MarketStructure.structure_id == structure_id)
    )
    row = result.scalar_one_or_none()
    now = datetime.utcnow()
    if row is None:
        session.add(MarketStructure(
            structure_id=structure_id,
            name=name,
            system_id=system_id,
            system_name=system_name,
            character_id=character_id,
            character_name=character_name,
            last_updated=now,
        ))
        return True
    else:
        row.name = name
        row.system_id = system_id
        row.system_name = system_name
        row.character_id = character_id
        row.character_name = character_name
        row.last_updated = now
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run(name_filter: str | None, limpar: bool, fonte: str):
    engine = create_async_engine(settings.DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        import app.models.user, app.models.character, app.models.item
        import app.models.blueprint, app.models.production_queue
        import app.models.cache, app.models.market_structure
        await conn.run_sync(Base.metadata.create_all)

    AsyncSessionFactory = async_sessionmaker(engine, expire_on_commit=False)
    esi = ScriptESIClient()

    usar_corp = fonte in ("corp", "ambos")
    usar_universo = fonte in ("universo", "ambos")
    usar_assets = fonte in ("assets", "ambos")

    try:
        async with AsyncSessionFactory() as session:
            if limpar:
                deleted = (await session.execute(delete(MarketStructure))).rowcount
                await session.flush()
                print(f"[✓] {deleted} estruturas removidas do banco.")

            characters = await get_characters(session, name_filter)
            if not characters:
                print("[✗] Nenhum personagem encontrado com refresh_token no banco.")
                print("    Faça login no servidor ao menos uma vez.")
                return

            fontes_ativas = " + ".join(filter(None, [
                "Corporação" if usar_corp else "",
                "Universo"   if usar_universo else "",
                "Assets"     if usar_assets else "",
            ]))
            print(f"[→] {len(characters)} personagem(ns) encontrado(s).")
            print(f"[→] Fontes ativas: {fontes_ativas}\n")

            total_new = 0
            total_updated = 0

            for char in characters:
                print(f"[→] Personagem: {char.character_name} ({char.character_id})")

                # Renova token se necessário
                if char.is_token_expired() or char.access_token is None:
                    print("    Renovando token...")
                    try:
                        token_data = esi.refresh_token(char.refresh_token)
                        await update_character_token(session, char, token_data)
                        print("    Token renovado.")
                    except Exception as exc:
                        print(f"    [!] Falha ao renovar token: {exc} — pulando.")
                        continue

                token = char.access_token

                # Coleta estruturas de todas as fontes ativas
                # Dicionário {structure_id: {"name": ..., "system_id": ..., "system_name": ...}}
                estruturas: dict[int, dict] = {}

                # --- Fonte 1: Corporação ---
                if usar_corp:
                    corp_id = char.corporation_id
                    if not corp_id:
                        print("    [!] corporation_id não disponível no banco — fonte corp ignorada.")
                        print("         Faça login no servidor novamente para atualizar os dados do personagem.")
                    else:
                        print(f"    [Fonte 1] Buscando estruturas da corporação {corp_id}...")
                        try:
                            corp_structs = esi.get_corp_structures_with_market(corp_id, token)
                            for s in corp_structs:
                                sid = s["structure_id"]
                                system_id = s.get("system_id")
                                system_name = "?"
                                if system_id:
                                    try:
                                        system_name = esi.get_system_name(system_id)
                                    except Exception:
                                        pass
                                estruturas[sid] = {
                                    "name": s.get("name", f"Structure {sid}"),
                                    "system_id": system_id,
                                    "system_name": system_name,
                                }
                            print(f"    [Fonte 1] {len(corp_structs)} estrutura(s) com mercado ativo na corporação.")
                        except httpx.HTTPStatusError as exc:
                            print(f"    [!] Erro {exc.response.status_code} na fonte corp — ignorando.")
                        except Exception as exc:
                            print(f"    [!] Erro inesperado na fonte corp: {exc} — ignorando.")

                # --- Fonte 3: Personal Assets ---
                if usar_assets:
                    print("    [Fonte 3] Buscando estruturas nos assets pessoais...")
                    try:
                        asset_ids = esi.get_character_asset_structure_ids(char.character_id, token)
                        novos_asset_ids = [sid for sid in asset_ids if sid not in estruturas]
                        print(f"    [Fonte 3] {len(asset_ids)} estrutura(s) encontrada(s) nos assets"
                              f" ({len(novos_asset_ids)} novas, não cobertas pelas fontes anteriores).")

                        for i, sid in enumerate(novos_asset_ids, 1):
                            sys.stdout.write(
                                f"\r    [Fonte 3] Resolvendo [{i}/{len(novos_asset_ids)}]: {sid}    "
                            )
                            sys.stdout.flush()
                            try:
                                info = esi.get_structure_info(sid, token)
                                system_id = info.get("solar_system_id")
                                system_name = "?"
                                if system_id:
                                    try:
                                        system_name = esi.get_system_name(system_id)
                                    except Exception:
                                        pass
                                estruturas[sid] = {
                                    "name": info.get("name", f"Structure {sid}"),
                                    "system_id": system_id,
                                    "system_name": system_name,
                                }
                            except httpx.HTTPStatusError as exc:
                                if exc.response.status_code == 403:
                                    pass  # estrutura de outra corp, sem acesso à info
                                elif exc.response.status_code != 404:
                                    print(f"\n    [!] Erro {exc.response.status_code} para {sid} — pulando.")
                            except Exception as exc:
                                print(f"\n    [!] Erro inesperado para {sid}: {exc} — pulando.")

                        if novos_asset_ids:
                            print()
                    except Exception as exc:
                        print(f"    [!] Erro na fonte assets: {exc} — ignorando.")

                # --- Fonte 2: Universo ---
                if usar_universo:
                    print("    [Fonte 2] Buscando estruturas acessíveis via universo...")
                    try:
                        universe_ids = esi.get_universe_market_structure_ids(token)
                        novos_ids = [sid for sid in universe_ids if sid not in estruturas]
                        print(f"    [Fonte 2] {len(universe_ids)} estrutura(s) encontrada(s)"
                              f" ({len(novos_ids)} novas, não cobertas pela fonte corp).")

                        for i, sid in enumerate(novos_ids, 1):
                            sys.stdout.write(
                                f"\r    [Fonte 2] Buscando detalhes [{i}/{len(novos_ids)}]: {sid}    "
                            )
                            sys.stdout.flush()
                            try:
                                info = esi.get_structure_info(sid, token)
                                system_id = info.get("solar_system_id")
                                system_name = "?"
                                if system_id:
                                    try:
                                        system_name = esi.get_system_name(system_id)
                                    except Exception:
                                        pass
                                estruturas[sid] = {
                                    "name": info.get("name", f"Structure {sid}"),
                                    "system_id": system_id,
                                    "system_name": system_name,
                                }
                            except httpx.HTTPStatusError as exc:
                                if exc.response.status_code != 403:
                                    print(f"\n    [!] Erro {exc.response.status_code} para {sid} — pulando.")
                            except Exception as exc:
                                print(f"\n    [!] Erro inesperado para {sid}: {exc} — pulando.")

                        if novos_ids:
                            print()  # quebra linha do progresso
                    except Exception as exc:
                        print(f"    [!] Erro na fonte universo: {exc} — ignorando.")

                if not estruturas:
                    print("    Nenhuma estrutura encontrada neste personagem.\n")
                    continue

                print(f"\n    Total combinado: {len(estruturas)} estrutura(s). Salvando no banco...")

                char_new = 0
                char_updated = 0

                for sid, info in estruturas.items():
                    is_new = await upsert_structure(
                        session=session,
                        structure_id=sid,
                        name=info["name"],
                        system_id=info["system_id"],
                        system_name=info["system_name"],
                        character_id=char.character_id,
                        character_name=char.character_name,
                    )
                    if is_new:
                        char_new += 1
                    else:
                        char_updated += 1

                print(f"    [✓] {char_new} novas, {char_updated} atualizadas.\n")
                total_new += char_new
                total_updated += char_updated

            await session.commit()

            total_result = await session.execute(select(MarketStructure))
            total_in_db = len(total_result.scalars().all())

            print(f"{'='*50}")
            print(f"  Novas:        {total_new}")
            print(f"  Atualizadas:  {total_updated}")
            print(f"  Total no DB:  {total_in_db}")
            print(f"{'='*50}")
            print("[✓] Concluído. O servidor já pode usar esses dados.")

    finally:
        esi.close()
        await engine.dispose()


if __name__ == "__main__":
    args = sys.argv[1:]

    name_filter = None
    if "--character" in args:
        idx = args.index("--character")
        name_filter = args[idx + 1] if idx + 1 < len(args) else None

    limpar = "--limpar" in args

    fonte = "ambos"
    if "--fonte" in args:
        idx = args.index("--fonte")
        valor = args[idx + 1] if idx + 1 < len(args) else "ambos"
        if valor not in ("corp", "universo", "assets", "ambos"):
            print(f"[!] --fonte inválido: '{valor}'. Use: corp | universo | assets | ambos")
            sys.exit(1)
        fonte = valor

    asyncio.run(run(name_filter=name_filter, limpar=limpar, fonte=fonte))
