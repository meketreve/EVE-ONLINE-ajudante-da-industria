"""
Serviços relacionados ao personagem logado.

- Refresh de token transparente (com lock por personagem para evitar race condition)
- Busca de skills via ESI (com cache DB, TTL 1 h)
- Cálculo de taxas de mercado baseadas nas skills
- Busca de estruturas acessíveis (com cache DB, TTL 24 h)
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.character import Character
from app.models.cache import SkillCache, StructureCache
from app.services.esi_client import esi_client, ESIError

logger = logging.getLogger(__name__)

# Lock por character_id para evitar race condition no token refresh
_token_locks: dict[int, asyncio.Lock] = {}

SKILL_CACHE_TTL = timedelta(hours=1)
STRUCTURE_CACHE_TTL = timedelta(hours=24)

SKILL_ACCOUNTING = 16622
SKILL_BROKER_RELATIONS = 3446

# Grupos de mercados públicos por zona de segurança.
# Cada grupo vira um <optgroup> no dropdown.
PUBLIC_MARKET_GROUPS: list[dict] = [
    {
        "label": "High-sec — Hubs Principais",
        "markets": [
            {"value": "region:10000002", "label": "Jita — The Forge"},
            {"value": "region:10000043", "label": "Amarr — Domain"},
            {"value": "region:10000032", "label": "Dodixie — Sinq Laison"},
            {"value": "region:10000030", "label": "Rens — Heimatar"},
            {"value": "region:10000042", "label": "Hek — Metropolis"},
        ],
    },
    {
        "label": "Low-sec",
        "markets": [
            {"value": "region:10000069", "label": "Black Rise"},
            {"value": "region:10000048", "label": "Placid"},
            {"value": "region:10000023", "label": "Pure Blind"},
            {"value": "region:10000028", "label": "Molden Heath"},
            {"value": "region:10000067", "label": "Genesis"},
        ],
    },
    {
        "label": "Null-sec NPC (aberto)",
        "markets": [
            {"value": "region:10000041", "label": "Syndicate"},
            {"value": "region:10000012", "label": "Curse"},
            {"value": "region:10000011", "label": "Great Wildlands"},
            {"value": "region:10000022", "label": "Stain"},
            {"value": "region:10000064", "label": "Outer Ring"},
        ],
    },
    {
        "label": "Null-sec SOV — Sul / Imperium ⚠ use estrutura privada",
        "markets": [
            {"value": "region:10000060", "label": "Delve (1DQ1-A)"},
            {"value": "region:10000058", "label": "Fountain"},
            {"value": "region:10000050", "label": "Querious"},
            {"value": "region:10000063", "label": "Period Basis"},
        ],
    },
    {
        "label": "Null-sec SOV — Sul / Legacy ⚠ use estrutura privada",
        "markets": [
            {"value": "region:10000014", "label": "Catch (GE-8JV)"},
            {"value": "region:10000061", "label": "Tenerifis"},
            {"value": "region:10000039", "label": "Esoteria"},
            {"value": "region:10000031", "label": "Impass"},
            {"value": "region:10000056", "label": "Feythabolis"},
            {"value": "region:10000062", "label": "Omist"},
        ],
    },
    {
        "label": "Null-sec SOV — Leste ⚠ use estrutura privada",
        "markets": [
            {"value": "region:10000025", "label": "Immensea"},
            {"value": "region:10000009", "label": "Detorid"},
            {"value": "region:10000065", "label": "Wicked Creek"},
            {"value": "region:10000008", "label": "Scalding Pass"},
            {"value": "region:10000036", "label": "Insmother"},
        ],
    },
    {
        "label": "Null-sec SOV — Providence ⚠ use estrutura privada",
        "markets": [
            {"value": "region:10000047", "label": "Providence"},
        ],
    },
    {
        "label": "Null-sec SOV — Norte ⚠ use estrutura privada",
        "markets": [
            {"value": "region:10000003", "label": "Vale of the Silent"},
            {"value": "region:10000033", "label": "The Citadel"},
            {"value": "region:10000035", "label": "Deklein"},
            {"value": "region:10000040", "label": "Oasa"},
            {"value": "region:10000010", "label": "Tribute"},
        ],
    },
]

# Lista plana para compatibilidade com código que itera todos os mercados públicos
PUBLIC_HUBS: list[dict] = [
    m for group in PUBLIC_MARKET_GROUPS for m in group["markets"]
]


# ---------------------------------------------------------------------------
# Personagem e token
# ---------------------------------------------------------------------------

async def get_character(character_id: int, db: AsyncSession) -> Character | None:
    result = await db.execute(select(Character).where(Character.character_id == character_id))
    return result.scalar_one_or_none()


async def get_fresh_token(character: Character, db: AsyncSession) -> str | None:
    if character.access_token is None:
        return None
    if not character.is_token_expired():
        return character.access_token
    if character.refresh_token is None:
        return None

    # Garante que apenas uma corrotina renova o token por vez para este personagem
    lock = _token_locks.setdefault(character.character_id, asyncio.Lock())
    async with lock:
        # Verifica novamente dentro do lock — outra tarefa pode ter renovado
        if not character.is_token_expired():
            return character.access_token
        try:
            token_data = await esi_client.refresh_access_token(character.refresh_token)
            character.access_token = token_data["access_token"]
            character.refresh_token = token_data.get("refresh_token", character.refresh_token)
            character.token_expiry = esi_client.compute_expiry(token_data.get("expires_in", 1200))
            character.updated_at = datetime.utcnow()
            await db.flush()
            return character.access_token
        except ESIError as exc:
            logger.warning("Falha ao renovar token do personagem %s: %s", character.character_id, exc)
            if "invalid_grant" in str(exc):
                # Login revogado/expirado no EVE SSO: marca como desconectado para
                # parar as tentativas em background até o personagem entrar de novo.
                character.access_token = None
                character.refresh_token = None
                character.token_expiry = None
                await db.flush()
                logger.warning("Personagem %s (%s) precisa fazer login de novo.",
                               character.character_name, character.character_id)
            return None


# ---------------------------------------------------------------------------
# Skills com cache DB
# ---------------------------------------------------------------------------

async def get_skill_levels(character_id: int, token: str, db: AsyncSession) -> dict[int, int]:
    """
    Retorna {skill_id: level} do personagem.
    Usa cache do banco (TTL 1 h) antes de chamar a ESI.
    """
    # Verifica cache
    result = await db.execute(select(SkillCache).where(SkillCache.character_id == character_id))
    cached = result.scalar_one_or_none()

    if cached and (datetime.utcnow() - cached.fetched_at) < SKILL_CACHE_TTL:
        return json.loads(cached.skills_json)

    # Busca na ESI
    try:
        data = await esi_client.get_character_skills(character_id, token)
        skills = {s["skill_id"]: s["trained_skill_level"] for s in data.get("skills", [])}
    except ESIError as exc:
        logger.warning("Não foi possível buscar skills do personagem %s: %s", character_id, exc)
        return json.loads(cached.skills_json) if cached else {}

    # Persiste no cache
    now = datetime.utcnow()
    skills_json = json.dumps(skills)
    if cached is None:
        db.add(SkillCache(character_id=character_id, skills_json=skills_json, fetched_at=now))
    else:
        cached.skills_json = skills_json
        cached.fetched_at = now
    await db.flush()

    return skills


# ---------------------------------------------------------------------------
# Taxas de mercado
# ---------------------------------------------------------------------------

def calculate_sales_tax(accounting_level: int) -> float:
    """Base 8%. Accounting reduz 11% por nível. Nível 5 → 3.6%"""
    return round(0.08 * (1.0 - 0.11 * accounting_level), 6)


def calculate_broker_fee(broker_relations_level: int) -> float:
    """Base 3% (NPC). Broker Relations reduz 0.3% por nível. Nível 5 → 1.5%"""
    return round(max(0.001, 0.03 - 0.003 * broker_relations_level), 6)


async def get_trading_fees_for_character(character_id: int, db: AsyncSession) -> dict:
    defaults = {
        "broker_fee_pct": 0.03,
        "sales_tax_pct": 0.08,
        "accounting_level": 0,
        "broker_relations_level": 0,
        "from_skills": False,
    }

    character = await get_character(character_id, db)
    if character is None:
        return defaults

    token = await get_fresh_token(character, db)
    if token is None:
        return defaults

    skills = await get_skill_levels(character_id, token, db)
    if not skills:
        return defaults

    accounting = skills.get(SKILL_ACCOUNTING, 0)
    broker_relations = skills.get(SKILL_BROKER_RELATIONS, 0)

    return {
        "broker_fee_pct": calculate_broker_fee(broker_relations),
        "sales_tax_pct": calculate_sales_tax(accounting),
        "accounting_level": accounting,
        "broker_relations_level": broker_relations,
        "from_skills": True,
    }


# ---------------------------------------------------------------------------
# Estruturas com cache DB
# ---------------------------------------------------------------------------

async def _get_structure_cached(
    structure_id: int,
    token: str,
    db: AsyncSession,
) -> dict:
    """Retorna info da estrutura do cache ou da ESI."""
    result = await db.execute(
        select(StructureCache).where(StructureCache.structure_id == structure_id)
    )
    cached = result.scalar_one_or_none()

    if cached and (datetime.utcnow() - cached.fetched_at) < STRUCTURE_CACHE_TTL:
        return {"name": cached.name, "system": cached.system_name}

    # Busca na ESI
    try:
        info = await esi_client.get_structure_info(structure_id, token)
        system_id = info.get("solar_system_id")
        system_name = await esi_client.get_system_name(system_id) if system_id else "?"
        name = info.get("name", f"Structure {structure_id}")
    except ESIError:
        name = f"Structure {structure_id}"
        system_id = None
        system_name = "?"

    now = datetime.utcnow()
    if cached is None:
        db.add(StructureCache(
            structure_id=structure_id,
            name=name,
            system_id=system_id,
            system_name=system_name,
            fetched_at=now,
        ))
    else:
        cached.name = name
        cached.system_id = system_id
        cached.system_name = system_name
        cached.fetched_at = now
    await db.flush()

    return {"name": name, "system": system_name}


async def get_market_options(character_id: int, db: AsyncSession) -> dict:
    """
    Retorna opções de mercado para o personagem.

    Combina duas fontes de estruturas privadas:
    - `market_structures`: populada pelo script atualizar_estruturas.py
    - `structures`: populada pelo crawler interno do app (status market_accessible)
    """
    from app.models.market_structure import MarketStructure
    from app.models.structure import Structure

    result: dict = {"groups": PUBLIC_MARKET_GROUPS, "private": []}

    # Fonte 1: script atualizar_estruturas.py
    ms_result = await db.execute(
        select(MarketStructure).order_by(MarketStructure.system_name, MarketStructure.name)
    )
    market_structs = ms_result.scalars().all()

    seen_ids: set[int] = set()
    for s in market_structs:
        seen_ids.add(s.structure_id)
        result["private"].append({
            "value": f"structure:{s.structure_id}",
            "label": f"{s.system_name} — {s.name}",
        })

    # Fonte 2: crawler interno (tabela structures, status market_accessible)
    cr_result = await db.execute(
        select(Structure)
        .where(Structure.status == "market_accessible")
        .order_by(Structure.system_name, Structure.name)
    )
    crawler_structs = cr_result.scalars().all()

    for s in crawler_structs:
        if s.structure_id in seen_ids:
            continue
        result["private"].append({
            "value": f"structure:{s.structure_id}",
            "label": f"{s.system_name or '?'} — {s.name or str(s.structure_id)}",
        })

    if not result["private"]:
        result["private_hint"] = "Execute atualizar_estruturas.bat para importar estruturas privadas."

    return result
