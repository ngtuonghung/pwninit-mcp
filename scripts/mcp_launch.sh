#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."

# System deps needed by the CLI tools (ar, eu-unstrip, patchelf).
MISSING_PKGS=()
command -v ar >/dev/null || MISSING_PKGS+=(binutils)
command -v eu-unstrip >/dev/null || MISSING_PKGS+=(elfutils)
command -v patchelf >/dev/null || MISSING_PKGS+=(patchelf)
if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
    if sudo -n true 2>/dev/null; then
        sudo apt-get update -q
        sudo apt-get install -y -q "${MISSING_PKGS[@]}"
    else
        echo "[!] Missing system packages: ${MISSING_PKGS[*]}" >&2
        echo "[!] Install them once (needs root), then retry: sudo apt install -y ${MISSING_PKGS[*]}" >&2
        exit 1
    fi
fi

if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv || {
        echo "[!] python3 -m venv failed. Install python3-venv and retry." >&2
        exit 1
    }
    .venv/bin/pip install --upgrade pip -q
    .venv/bin/pip install -q -r requirements.txt
fi

exec .venv/bin/python src/mcp_server.py
