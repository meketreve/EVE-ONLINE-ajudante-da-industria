#!/usr/bin/env python3
"""
CI: monta uma "release falsa" para testar o autoupdate dos launchers sem rede.

Uso: python .github/scripts/fake_release.py WORKDIR   (na raiz do checkout)

Gera em WORKDIR:
  inst/         instalação "antiga" (git archive do HEAD, sem .git, VERSION 0.0.1)
  release.zip   release v9.9.9 no formato do GitHub (pasta raiz <repo>-v9.9.9/), com uma
                linha extra nos launchers que prova que a versão NOVA deles rodou após o reinício
  latest.json   resposta da API /releases/latest apontando para o zip (URLs file://)

Se rodar no GitHub Actions, exporta EVE_TOOL_UPDATE_API para os próximos passos.
"""

import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

TAG = "v9.9.9"
MARKER = "LAUNCHER-NOVO-9.9.9"
# Linha do banner depois da qual o marcador entra em cada launcher
BANNERS = {
    "Iniciar.bat": ("echo  EVE Industry Tool\r\n", f"echo {MARKER}\r\n"),
    "iniciar.sh": ('echo " EVE Industry Tool"\n', f'echo "{MARKER}"\n'),
}


def main() -> int:
    work = Path(sys.argv[1]).resolve()
    work.mkdir(parents=True, exist_ok=True)
    base = subprocess.run(["git", "archive", "--format=zip", "HEAD"], check=True, capture_output=True).stdout

    # Instalação antiga
    inst = work / "inst"
    with zipfile.ZipFile(io.BytesIO(base)) as zf:
        for m in zf.infolist():
            if m.is_dir():
                continue
            dest = inst / m.filename
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(m))
            if (m.external_attr >> 16) & 0o111:
                dest.chmod(0o755)
    (inst / "VERSION").write_text("0.0.1\n", encoding="utf-8")

    # Release nova
    release = work / "release.zip"
    prefix = f"EVE-ONLINE-ajudante-da-industria-{TAG}/"
    with zipfile.ZipFile(io.BytesIO(base)) as src, zipfile.ZipFile(release, "w", zipfile.ZIP_DEFLATED) as out:
        for m in src.infolist():
            data = src.read(m)
            if m.filename == "VERSION":
                data = TAG.lstrip("v").encode() + b"\n"
            elif m.filename in BANNERS:
                anchor, extra = BANNERS[m.filename]
                text = data.decode("ascii" if m.filename.endswith(".bat") else "utf-8")
                assert anchor in text, f"banner não encontrado em {m.filename}"
                data = text.replace(anchor, anchor + extra, 1).encode("utf-8")
            info = zipfile.ZipInfo(prefix + m.filename, date_time=m.date_time)
            info.external_attr = m.external_attr
            info.compress_type = zipfile.ZIP_DEFLATED
            out.writestr(info, data)

    latest = work / "latest.json"
    latest.write_text(json.dumps({
        "tag_name": TAG,
        "zipball_url": release.as_uri(),
        "html_url": "",
        "body": "## Novidades\n- Release falsa do CI.",
    }), encoding="utf-8")

    api = latest.as_uri()
    print(f"instalação: {inst}\nrelease:    {release}\nAPI:        {api}")
    if os.environ.get("GITHUB_ENV"):
        with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as env:
            env.write(f"EVE_TOOL_UPDATE_API={api}\nINST_DIR={inst}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
