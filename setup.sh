#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

MISSING_PKGS=()
for pkg in binutils elfutils patchelf; do
    dpkg -s "$pkg" &>/dev/null || MISSING_PKGS+=("$pkg")
done

if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
    echo "[*] Installing system dependencies: ${MISSING_PKGS[*]}..."
    sudo apt update
    sudo apt install -y "${MISSING_PKGS[@]}"
else
    echo "[!] System dependencies already installed, skipping."
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "[*] Creating Python virtual environment at $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
else
    echo "[!] Virtual environment already exists, skipping."
fi

if ! "$VENV_DIR/bin/pip" show pyelftools requests tqdm zstandard &>/dev/null; then
    echo "[*] Installing Python requirements..."
    "$VENV_DIR/bin/pip" install --upgrade pip -q
    "$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"
else
    echo "[!] Python requirements already installed, skipping."
fi

mkdir -p "$HOME/.cache/pwninit"

echo "[*] Appending alias to ~/.bashrc..."

ALIAS_LINE="alias pwninit='\"$VENV_DIR/bin/python3\" \"$SCRIPT_DIR/pwninit.py\" -t default \"\$@\"'"

if grep -qF "alias pwninit=" ~/.bashrc; then
    echo "[!] Alias 'pwninit' already exists in ~/.bashrc, updating if needed."
    sed -i '/alias pwninit=/c\'"$ALIAS_LINE" ~/.bashrc
else
    echo "" >> ~/.bashrc
    echo "# pwninit.py alias" >> ~/.bashrc
    echo "$ALIAS_LINE" >> ~/.bashrc
    echo "[+] Alias added to ~/.bashrc"
fi

echo ""
echo "[+] Setup complete. Reloading shell..."
exec bash