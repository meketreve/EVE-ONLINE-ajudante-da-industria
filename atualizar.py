#!/usr/bin/env python3
"""
Atualização automática do EVE Industry Tool pela última GitHub Release.

Chamado pelos launchers (Iniciar.bat / iniciar.sh) antes de abrir o app. Usa só a
biblioteca padrão, então roda antes do ambiente virtual existir.

Códigos de saída:
  0   nada a fazer (já atualizado, offline, desativado, clone git...)
  10  atualizou: o launcher deve se reiniciar para rodar a versão nova de si mesmo
  1   erro inesperado (o launcher segue com a versão atual)

Nunca bloqueia o uso: qualquer falha de rede ou de download mantém a versão atual.

Desativar: criar o arquivo `.sem-autoupdate` na pasta do programa ou definir
EVE_TOOL_NO_UPDATE=1.
"""

import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

REPO = "meketreve/EVE-ONLINE-ajudante-da-industria"
API_URL = os.environ.get("EVE_TOOL_UPDATE_API", f"https://api.github.com/repos/{REPO}/releases/latest")
TIMEOUT = 5          # consulta da versão: rápida, não pode travar a abertura
DOWNLOAD_TIMEOUT = 60

# Uma release sem estes arquivos está quebrada: não instala nada
REQUIRED_FILES = ("VERSION", "atualizar.py", "eve_industry_tool/app/main.py")
# Se a versão nova "apagar" mais que isso da instalação atual, algo está errado: não apaga nada
MAX_REMOVED_FRACTION = 0.3

ROOT = Path(__file__).resolve().parent
VERSION_FILE = ROOT / "VERSION"
MANIFEST_FILE = ROOT / ".arquivos-instalados"

# Nunca sobrescrever nem apagar: dados do usuário, ambientes e caches
PROTECTED_NAMES = {
    ".env", ".secret_key", ".nicegui", ".venv", ".venv-linux", "__pycache__",
    ".git", ".sem-autoupdate", ".arquivos-instalados",
}
PROTECTED_PREFIXES = ("database.db", "everef_cache", "fuzzwork_")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")


def log(msg: str) -> None:
    print(f"[atualizar] {msg}", flush=True)


def parse_version(text: str) -> tuple[int, ...]:
    text = text.strip().lstrip("vV")
    parts = []
    for p in text.split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def is_protected(rel: Path) -> bool:
    return any(
        part in PROTECTED_NAMES or part.startswith(PROTECTED_PREFIXES)
        for part in rel.parts
    )


def http_get(url: str, timeout: int) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": "EVE-Industry-Tool-updater",
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def local_version() -> tuple[int, ...]:
    try:
        return parse_version(VERSION_FILE.read_text(encoding="utf-8"))
    except OSError:
        return (0,)


def install(zip_path: Path, tag: str) -> list[str]:
    """Copia os arquivos da release para ROOT. Devolve a lista de arquivos instalados."""
    installed: list[str] = []
    with zipfile.ZipFile(zip_path) as zf:
        members = [m for m in zf.infolist() if not m.is_dir()]
        # O zip do GitHub tem uma pasta raiz: <repo>-<tag>/
        tops = {m.filename.split("/", 1)[0] for m in members}
        strip = len(tops) == 1 and all("/" in m.filename for m in members)

        entries = {}
        for m in members:
            name = m.filename.split("/", 1)[1] if strip else m.filename
            rel = Path(name)
            # Zip malformado não pode escrever fora da pasta do programa
            if name and not rel.is_absolute() and ".." not in rel.parts:
                entries[rel.as_posix()] = m

        # Valida antes de tocar em qualquer arquivo
        missing = [f for f in REQUIRED_FILES if f not in entries]
        if missing:
            raise ValueError(f"release incompleta, faltam: {', '.join(missing)}")
        zip_version = parse_version(zf.read(entries["VERSION"]).decode("utf-8", "replace"))
        if zip_version != parse_version(tag):
            raise ValueError(f"VERSION da release ({'.'.join(map(str, zip_version))}) não bate com a tag {tag}")

        for name, m in entries.items():
            rel = Path(name)
            if is_protected(rel):
                continue
            dest = ROOT / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(m) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
            # zipfile não restaura permissões: devolve o bit de execução (iniciar.sh)
            mode = (m.external_attr >> 16) & 0o777
            if mode & 0o111:
                dest.chmod(dest.stat().st_mode | 0o755)
            installed.append(rel.as_posix())

    # Remove o que existia na versão anterior e saiu da nova
    try:
        previous = set(MANIFEST_FILE.read_text(encoding="utf-8").splitlines())
    except OSError:
        previous = set()
    removed = sorted(r for r in previous - set(installed) if r and not is_protected(Path(r)))
    if previous and len(removed) > MAX_REMOVED_FRACTION * len(previous):
        log(f"a versão nova removeria {len(removed)} de {len(previous)} arquivos; "
            "nada foi apagado por segurança.")
        removed = []
    for rel in removed:
        path = ROOT / rel
        if path.is_file():
            path.unlink()
            log(f"removido: {rel}")

    MANIFEST_FILE.write_text("\n".join(installed) + "\n", encoding="utf-8")
    return installed


def main() -> int:
    if os.environ.get("EVE_TOOL_NO_UPDATE") == "1" or (ROOT / ".sem-autoupdate").exists():
        log("atualização automática desativada.")
        return 0
    if (ROOT / ".git").exists():
        log("pasta é um clone git: use 'git pull' para atualizar.")
        return 0

    try:
        release = json.loads(http_get(API_URL, TIMEOUT))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            log("nenhuma release publicada ainda; seguindo com a versão atual.")
        else:
            log(f"não foi possível verificar atualizações (HTTP {exc.code}); seguindo com a versão atual.")
        return 0
    except Exception as exc:  # offline, GitHub fora, limite da API...
        log(f"não foi possível verificar atualizações ({exc.__class__.__name__}); seguindo com a versão atual.")
        return 0

    tag = release.get("tag_name") or ""
    zip_url = release.get("zipball_url")
    current = local_version()
    if not tag or not zip_url or parse_version(tag) <= current:
        log(f"versão atual: {'.'.join(map(str, current))} (em dia).")
        return 0

    log(f"nova versão {tag} disponível (instalada: {'.'.join(map(str, current))}). Baixando...")
    try:
        with tempfile.TemporaryDirectory(prefix="eve-tool-dl-") as tmp:
            zip_path = Path(tmp) / "release.zip"
            zip_path.write_bytes(http_get(zip_url, DOWNLOAD_TIMEOUT))
            files = install(zip_path, tag)
    except Exception as exc:
        log(f"falha ao baixar/instalar {tag} ({exc}); seguindo com a versão atual.")
        return 0

    log(f"atualizado para {tag} ({len(files)} arquivos). Seus dados foram mantidos.")
    return 10


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # nunca impedir o app de abrir
        log(f"erro inesperado: {exc}")
        sys.exit(1)
