#!/usr/bin/env bash
# EVE Industry Tool — iniciar no Linux
#
# Uso:
#   ./iniciar.sh              abre no navegador, usando o .env como está
#   ./iniciar.sh --sem-secret ignora EVE_CLIENT_SECRET do .env (testa o login PKCE,
#                             como um usuário novo sem .env)
#   ./iniciar.sh --nativo     tenta abrir em janela nativa (precisa de GTK ou Qt)
set -euo pipefail

SCRIPT="$(readlink -f "$0")"
cd "$(dirname "$SCRIPT")/eve_industry_tool"

VENV=".venv-linux"
SEM_SECRET=0
NATIVO=0
for arg in "$@"; do
    case "$arg" in
        --sem-secret) SEM_SECRET=1 ;;
        --nativo)     NATIVO=1 ;;
        -h|--help)    sed -n '2,8p' "$SCRIPT" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "[!] Opção desconhecida: $arg (use --help)"; exit 1 ;;
    esac
done

echo "============================================"
echo " EVE Industry Tool"
echo "============================================"

# ── 0. Atualização automática (última GitHub Release) ───────────────────────
# Atualizar e reiniciar ficam no mesmo bloco: o bash lê o script enquanto executa,
# então a versão nova do iniciar.sh precisa começar do zero (exec).
UPD_PY="$VENV/bin/python"
[ -x "$UPD_PY" ] || UPD_PY="$(command -v python3 || true)"
if [ -n "$UPD_PY" ] && [ -z "${EVE_TOOL_UPDATED:-}" ]; then
    rc=0
    "$UPD_PY" "$(dirname "$SCRIPT")/atualizar.py" || rc=$?
    if [ "$rc" = 10 ]; then
        export EVE_TOOL_UPDATED=1
        exec bash "$SCRIPT" "$@"
    fi
fi

# ── 1. Python 3.11+ ──────────────────────────────────────────────────────────
if [ ! -x "$VENV/bin/python" ]; then
    PY=""
    for cand in python3.13 python3.12 python3.11 python3; do
        if command -v "$cand" >/dev/null 2>&1 &&
           "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
            PY="$cand"; break
        fi
    done
    if [ -z "$PY" ]; then
        echo "[!] Python 3.11 ou superior não encontrado."
        echo "    Ubuntu/Debian: sudo apt install python3 python3-venv"
        exit 1
    fi

    echo "[..] Criando ambiente em eve_industry_tool/$VENV (só na primeira vez)..."
    if ! "$PY" -m venv "$VENV"; then
        echo "[!] Falha ao criar o venv. Ubuntu/Debian: sudo apt install python3-venv"
        exit 1
    fi
fi

# ── 2. Dependências (reinstala quando requirements.txt muda) ────────────────
if ! cmp -s requirements.txt "$VENV/requirements.installed"; then
    echo "[..] Instalando dependências..."
    "$VENV/bin/python" -m pip install --upgrade pip --quiet --disable-pip-version-check
    "$VENV/bin/python" -m pip install -r requirements.txt --quiet --disable-pip-version-check
    cp requirements.txt "$VENV/requirements.installed"
    echo "[OK] Dependências instaladas."
fi

# ── 3. Modo de login ─────────────────────────────────────────────────────────
if [ "$SEM_SECRET" = 1 ]; then
    # Variável vazia no ambiente tem precedência sobre o .env (load_dotenv não sobrescreve)
    export EVE_CLIENT_SECRET=""
    echo "[i] Teste PKCE: EVE_CLIENT_SECRET ignorado — login como usuário novo."
elif [ -f .env ] && grep -q '^EVE_CLIENT_SECRET=.\+' .env; then
    echo "[i] Login com Client Secret do .env (use --sem-secret para testar PKCE)."
else
    echo "[i] Login via PKCE (sem Client Secret)."
fi

# ── 4. Inicia ────────────────────────────────────────────────────────────────
if [ "$NATIVO" = 1 ]; then
    export EVE_TOOL_NATIVE=1
else
    export EVE_TOOL_NATIVE=0
    echo "[i] Abrindo no navegador: http://localhost:8765"
fi
echo "    Ctrl+C para encerrar."
echo "============================================"

export PYTHONIOENCODING=utf-8
exec "$VENV/bin/python" -m app.main
