#!/usr/bin/env python3
"""
Importa dados estáticos do EVE Online para o banco local.

Fontes (tentadas em ordem):
  1. EVERef reference-data  — ~13 MB tar.xz, atualizado diariamente
  2. Fuzzwork SQLite SDE     — ~150 MB gz (~500 MB descomprimido), a cada patch

Uso:
    python scripts/import_sde.py                 # baixa + importa
    python scripts/import_sde.py --force-download  # rebaixa mesmo com cache
    python scripts/import_sde.py --source fuzzwork # força fonte específica
    python scripts/import_sde.py --skip-download   # usa cache existente
"""

import json
import os
import sqlite3
import sys
import tarfile
import gzip
import shutil
import tempfile
from pathlib import Path

# Garante que o terminal Windows aceite UTF-8 nos prints
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx

# ---------------------------------------------------------------------------
# Fontes de dados
# ---------------------------------------------------------------------------

EVEREF_URL = "https://data.everef.net/reference-data/reference-data-latest.tar.xz"
FUZZWORK_URL = "https://www.fuzzwork.co.uk/dump/latest-sqlite.db.gz"

EVEREF_CACHE = Path("everef_cache.tar.xz")
FUZZWORK_CACHE = Path("fuzzwork_cache.sqlite")

DB_PATH = Path("database.db")
ACTIVITY_MANUFACTURING = 1
ACTIVITY_REACTION      = 11
PORTION_SIZE_DEFAULT   = 1


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------

def _download(url: str, dest: Path) -> bool:
    """Baixa `url` para `dest` com barra de progresso. Retorna True se ok."""
    print(f"[↓] {url}")
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=60) as r:
            if r.status_code != 200:
                print(f"    HTTP {r.status_code} — pulando.")
                return False

            total = int(r.headers.get("content-length", 0))
            total_mb = total / 1_048_576 if total else 0
            received = 0

            with open(dest, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=65536):
                    f.write(chunk)
                    received += len(chunk)
                    recv_mb = received / 1_048_576
                    if total:
                        pct = min(int(received * 100 / total), 100)
                        sys.stdout.write(f"\r    {pct:3d}%  {recv_mb:.1f} / {total_mb:.1f} MB")
                    else:
                        sys.stdout.write(f"\r    {recv_mb:.1f} MB")
                    sys.stdout.flush()

        print()
        return True

    except Exception as exc:
        print(f"\n    Erro: {exc}")
        return False


# ---------------------------------------------------------------------------
# Fonte 1 — EVERef reference-data (tar.xz)
# ---------------------------------------------------------------------------

def download_everef(force: bool = False) -> bool:
    if EVEREF_CACHE.exists() and not force:
        print(f"[✓] Cache EVERef encontrado: {EVEREF_CACHE}")
        return True
    return _download(EVEREF_URL, EVEREF_CACHE)


def import_from_everef(db: sqlite3.Connection) -> None:
    """Lê o tar.xz do EVERef e popula items + blueprints + reprocessamento."""
    print(f"\n[→] Lendo {EVEREF_CACHE} ...")

    with tarfile.open(EVEREF_CACHE, "r:xz") as tar:
        names = tar.getnames()

        types_file      = _find_in_tar(names, "types.json")
        blueprints_file = _find_in_tar(names, "blueprints.json")

        if not types_file or not blueprints_file:
            raise RuntimeError(
                f"Estrutura inesperada no tar.xz. Arquivos encontrados:\n  " +
                "\n  ".join(names[:30])
            )

        print(f"    Lendo types...")
        types_data: dict = json.loads(tar.extractfile(tar.getmember(types_file)).read())

        print(f"    Lendo blueprints...")
        blueprints_data: dict = json.loads(tar.extractfile(tar.getmember(blueprints_file)).read())

        # Reprocessamento: o EVERef atual traz em types.json → type_materials;
        # versões antigas traziam num arquivo separado (hoje vem vazio).
        reproc_data: dict | None = {
            tid: t["type_materials"]
            for tid, t in types_data.items()
            if t.get("type_materials")
        } or None
        if reproc_data is None:
            for candidate in ("type_materials.json", "invTypeMaterials.json", "typeMaterials.json"):
                f = _find_in_tar(names, candidate)
                if f:
                    print(f"    Lendo {candidate}...")
                    reproc_data = json.loads(tar.extractfile(tar.getmember(f)).read()) or None
                    break

    _insert_items_everef(db, types_data, {}, blueprints_data)
    _insert_blueprints_everef(db, blueprints_data)
    if reproc_data is not None:
        _insert_reprocessing_everef(db, reproc_data)
    else:
        print("[!] Dados de reprocessamento não encontrados no EVERef — use Fuzzwork para importar.")


def _find_in_tar(names: list[str], filename: str) -> str | None:
    for n in names:
        if n.endswith(f"/{filename}") or n == filename:
            return n
    return None


def _insert_items_everef(
    db: sqlite3.Connection,
    types_data: dict,
    _groups_data: dict,
    blueprints_data: dict,
) -> None:
    print("\n[→] Importando itens (EVERef)...")

    # type_ids que são produto de algum blueprint de manufatura OU reação
    # EVERef: products é um dict {"type_id_str": {"type_id": N, "quantity": N}}
    manufacturable: set[int] = set()
    for bp in blueprints_data.values():
        for activity_key in ("manufacturing", "reaction"):
            act = bp.get("activities", {}).get(activity_key, {})
            products = act.get("products", {})
            if isinstance(products, dict):
                for prod in products.values():
                    manufacturable.add(int(prod["type_id"]))
            else:
                for prod in products:
                    manufacturable.add(int(prod.get("type_id") or prod.get("typeID")))

    rows = []
    for tid, t in types_data.items():
        if not t.get("published", False):
            continue
        type_id = int(tid)
        # EVERef usa snake_case: group_id, category_id, volume
        group_id = t.get("group_id")
        category_id = t.get("category_id")
        name_field = t.get("name", {})
        name = name_field.get("en", str(type_id)) if isinstance(name_field, dict) else str(name_field)
        rows.append((
            type_id,
            name,
            group_id,
            category_id,
            t.get("volume"),
            1 if type_id in manufacturable else 0,
            int(t.get("portion_size") or PORTION_SIZE_DEFAULT),
        ))

    db.execute("DELETE FROM items")
    db.executemany(
        "INSERT INTO items (type_id, type_name, group_id, category_id, volume, is_manufacturable, portion_size) VALUES (?,?,?,?,?,?,?)",
        rows,
    )
    print(f"    {len(rows):,} itens  |  {len(manufacturable):,} fabricáveis")


def _insert_blueprints_everef(db: sqlite3.Connection, blueprints_data: dict) -> None:
    print("[→] Importando blueprints (EVERef) — manufatura + reação...")

    db.execute("DELETE FROM blueprint_materials")
    db.execute("DELETE FROM blueprints")

    bp_rows = []
    mat_rows = []

    for bp_type_id_str, bp in blueprints_data.items():
        bp_type_id = int(bp_type_id_str)

        # Tenta manufatura primeiro, depois reação
        act = bp.get("activities", {})
        activity = act.get("manufacturing") or act.get("reaction")
        if not activity:
            continue

        # EVERef: products e materials são dicts keyed by str type_id
        products = activity.get("products", {})
        if not products:
            continue

        product = next(iter(products.values())) if isinstance(products, dict) else products[0]
        product_type_id = int(product.get("type_id") or product.get("typeID"))
        product_qty = int(product.get("quantity", 1))
        time_seconds = int(activity.get("time", 0))

        raw_mats = activity.get("materials", {})
        mat_iter = raw_mats.values() if isinstance(raw_mats, dict) else raw_mats
        materials = [
            {"type_id": int(m.get("type_id") or m.get("typeID")), "quantity": int(m["quantity"])}
            for m in mat_iter
        ]

        bp_rows.append((bp_type_id, product_type_id, product_qty, time_seconds, json.dumps(materials)))

    db.executemany(
        "INSERT INTO blueprints (blueprint_type_id, product_type_id, product_quantity, time_seconds, materials) VALUES (?,?,?,?,?)",
        bp_rows,
    )

    # Normalized blueprint_materials
    bp_id_map = {r[0]: r[1] for r in db.execute("SELECT blueprint_type_id, id FROM blueprints")}
    for bp_type_id_str, bp in blueprints_data.items():
        bp_type_id = int(bp_type_id_str)
        internal_id = bp_id_map.get(bp_type_id)
        if internal_id is None:
            continue
        act = bp.get("activities", {})
        activity = act.get("manufacturing") or act.get("reaction")
        if not activity:
            continue
        raw_mats = activity.get("materials", {})
        mat_iter = raw_mats.values() if isinstance(raw_mats, dict) else raw_mats
        for m in mat_iter:
            mat_rows.append((internal_id, int(m.get("type_id") or m.get("typeID")), int(m["quantity"])))

    db.executemany(
        "INSERT INTO blueprint_materials (blueprint_id, material_type_id, quantity) VALUES (?,?,?)",
        mat_rows,
    )

    print(f"    {len(bp_rows):,} blueprints  |  {len(mat_rows):,} materiais")


# ---------------------------------------------------------------------------
# Fonte 2 — Fuzzwork SQLite SDE (gz)
# ---------------------------------------------------------------------------

def download_fuzzwork(force: bool = False) -> bool:
    if FUZZWORK_CACHE.exists() and not force:
        print(f"[✓] Cache Fuzzwork encontrado: {FUZZWORK_CACHE}")
        return True

    gz_path = Path("fuzzwork_temp.sqlite.gz")
    if not _download(FUZZWORK_URL, gz_path):
        return False

    print("[↓] Descomprimindo Fuzzwork SDE...")
    try:
        with gzip.open(gz_path, "rb") as f_in, open(FUZZWORK_CACHE, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out, length=1_048_576)
    except (OSError, EOFError) as exc:
        print(f"    Erro ao descomprimir: {exc}")
        FUZZWORK_CACHE.unlink(missing_ok=True)
        return False
    finally:
        gz_path.unlink(missing_ok=True)
    size_mb = FUZZWORK_CACHE.stat().st_size / 1_048_576
    print(f"[✓] Fuzzwork SDE: {FUZZWORK_CACHE} ({size_mb:.0f} MB)")
    return True


def import_from_fuzzwork(db: sqlite3.Connection) -> None:
    print(f"\n[→] Lendo {FUZZWORK_CACHE} ...")
    sde = sqlite3.connect(FUZZWORK_CACHE)
    sde.row_factory = sqlite3.Row

    _insert_items_fuzzwork(sde, db)
    _insert_blueprints_fuzzwork(sde, db)
    _insert_reprocessing_fuzzwork(sde, db)

    sde.close()


def _insert_reprocessing_fuzzwork(sde: sqlite3.Connection, db: sqlite3.Connection) -> None:
    print("[→] Importando materiais de reprocessamento (Fuzzwork)...")
    rows = sde.execute(
        "SELECT typeID, materialTypeID, quantity FROM invTypeMaterials"
    ).fetchall()

    db.execute("DELETE FROM reprocessing_materials")
    db.executemany(
        "INSERT OR IGNORE INTO reprocessing_materials (type_id, material_type_id, quantity) VALUES (?,?,?)",
        [(r["typeID"], r["materialTypeID"], r["quantity"]) for r in rows],
    )
    print(f"    {len(rows):,} entradas de reprocessamento")


def _insert_reprocessing_everef(db: sqlite3.Connection, reproc_data: dict) -> None:
    """
    Importa dados de reprocessamento do EVERef.
    Aceita dois formatos:
      - dict: {type_id_str: [{material_type_id, quantity}, ...]}
      - dict: {type_id_str: {material_id_str: {material_type_id, quantity}}}  (types.json)
      - list:  [{type_id, material_type_id, quantity}, ...]
    """
    print("[→] Importando materiais de reprocessamento (EVERef)...")
    rows = []

    if isinstance(reproc_data, list):
        for entry in reproc_data:
            tid = entry.get("type_id") or entry.get("typeID")
            mat = entry.get("material_type_id") or entry.get("materialTypeID")
            qty = entry.get("quantity")
            if tid and mat and qty:
                rows.append((int(tid), int(mat), int(qty)))
    elif isinstance(reproc_data, dict):
        for tid_str, mats in reproc_data.items():
            # types.json usa {material_id: {material_type_id, quantity}}
            if isinstance(mats, dict):
                mats = list(mats.values())
            if isinstance(mats, list):
                for m in mats:
                    mat = m.get("material_type_id") or m.get("materialTypeID")
                    qty = m.get("quantity")
                    if mat and qty:
                        rows.append((int(tid_str), int(mat), int(qty)))

    db.execute("DELETE FROM reprocessing_materials")
    db.executemany(
        "INSERT OR IGNORE INTO reprocessing_materials (type_id, material_type_id, quantity) VALUES (?,?,?)",
        rows,
    )
    print(f"    {len(rows):,} entradas de reprocessamento")


def _insert_items_fuzzwork(sde: sqlite3.Connection, db: sqlite3.Connection) -> None:
    print("\n[→] Importando itens (Fuzzwork)...")

    rows = sde.execute("""
        SELECT t.typeID, t.typeName, t.groupID, g.categoryID, t.volume,
               COALESCE(t.portionSize, 1) AS portionSize
        FROM invTypes t
        JOIN invGroups g ON t.groupID = g.groupID
        WHERE t.published = 1
    """).fetchall()

    manufacturable: set[int] = {
        r[0] for r in sde.execute(
            "SELECT productTypeID FROM industryActivityProducts WHERE activityID IN (?, ?)",
            (ACTIVITY_MANUFACTURING, ACTIVITY_REACTION)
        )
    }

    db.execute("DELETE FROM items")
    db.executemany(
        "INSERT INTO items (type_id, type_name, group_id, category_id, volume, is_manufacturable, portion_size) VALUES (?,?,?,?,?,?,?)",
        [(r["typeID"], r["typeName"], r["groupID"], r["categoryID"], r["volume"],
          1 if r["typeID"] in manufacturable else 0, r["portionSize"]) for r in rows],
    )
    print(f"    {len(rows):,} itens  |  {len(manufacturable):,} fabricáveis")


def _insert_blueprints_fuzzwork(sde: sqlite3.Connection, db: sqlite3.Connection) -> None:
    print("[→] Importando blueprints (Fuzzwork) — manufatura + reação...")

    products = sde.execute("""
        SELECT p.typeID AS bp_id, p.productTypeID, p.quantity, p.activityID,
               COALESCE(t.time, 0) AS time_seconds
        FROM industryActivityProducts p
        LEFT JOIN industryActivity t ON t.typeID = p.typeID AND t.activityID = p.activityID
        WHERE p.activityID IN (?, ?)
    """, (ACTIVITY_MANUFACTURING, ACTIVITY_REACTION)).fetchall()

    mat_rows_raw = sde.execute("""
        SELECT typeID, materialTypeID, quantity
        FROM industryActivityMaterials WHERE activityID IN (?, ?)
    """, (ACTIVITY_MANUFACTURING, ACTIVITY_REACTION)).fetchall()

    from collections import defaultdict
    mat_map: dict[int, list] = defaultdict(list)
    for r in mat_rows_raw:
        mat_map[r[0]].append({"type_id": r[1], "quantity": r[2]})

    db.execute("DELETE FROM blueprint_materials")
    db.execute("DELETE FROM blueprints")

    bp_rows = [(r["bp_id"], r["productTypeID"], r["quantity"], r["time_seconds"],
                json.dumps(mat_map.get(r["bp_id"], []))) for r in products]
    db.executemany(
        "INSERT INTO blueprints (blueprint_type_id, product_type_id, product_quantity, time_seconds, materials) VALUES (?,?,?,?,?)",
        bp_rows,
    )

    bp_id_map = {r[0]: r[1] for r in db.execute("SELECT blueprint_type_id, id FROM blueprints")}
    mat_inserts = []
    for bp_type_id, mats in mat_map.items():
        internal_id = bp_id_map.get(bp_type_id)
        if internal_id:
            for m in mats:
                mat_inserts.append((internal_id, m["type_id"], m["quantity"]))

    db.executemany(
        "INSERT INTO blueprint_materials (blueprint_id, material_type_id, quantity) VALUES (?,?,?)",
        mat_inserts,
    )
    print(f"    {len(bp_rows):,} blueprints  |  {len(mat_inserts):,} materiais")


# ---------------------------------------------------------------------------
# Orquestração principal
# ---------------------------------------------------------------------------

def run(force: bool, skip_download: bool, source: str | None) -> None:
    if not DB_PATH.exists():
        print(f"[✗] Banco local não encontrado: {DB_PATH}")
        print("    Inicie o servidor ao menos uma vez para criar as tabelas.")
        sys.exit(1)

    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")

    # Migrations: garante colunas e tabelas novas antes de importar.
    _schema_migrations = [
        "ALTER TABLE items ADD COLUMN portion_size INTEGER DEFAULT 1",
        """CREATE TABLE IF NOT EXISTS reprocessing_materials (
            id INTEGER PRIMARY KEY,
            type_id INTEGER NOT NULL,
            material_type_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            UNIQUE(type_id, material_type_id)
        )""",
        "CREATE INDEX IF NOT EXISTS ix_reproc_type_id ON reprocessing_materials (type_id)",
    ]
    for sql in _schema_migrations:
        try:
            db.execute(sql)
        except sqlite3.OperationalError:
            pass  # coluna/tabela já existe
    db.commit()

    try:
        # --- Tenta EVERef (padrão, a menos que --source fuzzwork) ---
        if source != "fuzzwork":
            if skip_download or download_everef(force=force):
                if EVEREF_CACHE.exists():
                    try:
                        import_from_everef(db)
                        db.commit()
                        print("\n[✓] Importação via EVERef concluída!")
                        return
                    except Exception as exc:
                        print(f"\n[!] Falha ao importar EVERef: {exc}")
                        print("    Tentando Fuzzwork como fallback...")

        # --- Fallback: Fuzzwork ---
        if skip_download or download_fuzzwork(force=force):
            if FUZZWORK_CACHE.exists():
                import_from_fuzzwork(db)
                db.commit()
                print("\n[✓] Importação via Fuzzwork concluída!")
                return

        print("\n[✗] Nenhuma fonte disponível. Verifique sua conexão com a internet.")
        sys.exit(1)

    finally:
        db.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    args = sys.argv[1:]
    flags = set(args)

    os.chdir(Path(__file__).parent.parent)

    source = None
    if "--source" in args:
        idx = args.index("--source")
        source = args[idx + 1] if idx + 1 < len(args) else None

    run(
        force="--force-download" in flags,
        skip_download="--skip-download" in flags,
        source=source,
    )
