#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORTABLE_DIR="$SCRIPT_DIR/portable"
DATA_DIR="$SCRIPT_DIR/data"
VENV_DIR="$PORTABLE_DIR/venv"

# Check if setup has been run
if [ ! -f "$VENV_DIR/bin/python" ]; then
    echo "ERROR: Hermes Portable is not set up yet!"
    echo "Please run: ./setup.sh"
    exit 1
fi

# Set HERMES_HOME to point to our data directory
export HERMES_HOME="$DATA_DIR"
export PATH="$VENV_DIR/bin:$PORTABLE_DIR/python:$PATH"

# Banner
echo ""
echo "  ╦ ╦╔═╗╦═╗╔═╗╔═╗╔═╗╔╦╗╔═╗"
echo "  ╠═╣╠═╣╠╦╝╠═╝║╣ ║   ║ ║ ║"
echo "  ╩ ╩╩ ╩╩╚═╩  ╚═╝╚═╝╩ ╩╚═╝  Portable"
echo ""

# Launch Hermes
cd "$SCRIPT_DIR"
exec "$VENV_DIR/bin/hermes" "$@"
